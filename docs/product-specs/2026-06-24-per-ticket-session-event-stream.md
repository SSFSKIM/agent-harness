---
status: draft
last_verified: 2026-06-24
owner: harness
phase: symphony/05-ticket-event-stream
type: product-spec
tags: [observability, telemetry, dashboard, worker, streaming]
description: A durable per-ticket session-event layer — the worker turn-stream firehose (today tapped only for token usage and discarded) is normalized into a per-ticket append-only JSONL, served as a live SSE drill-down and a derived per-ticket telemetry timeseries, uniform across codex and claude workers.
---
# Per-ticket session-event stream (live drill-down + derived telemetry)

Phase 5 **observability** track. Parent:
[Symphony 티켓 오케스트레이션 + 중앙 Director](2026-06-14-symphony-director-orchestration.md)
(line 199 "Phase 5 — observability surface"). This is the next consumer-richness
slice after the read dashboard
([observability-dashboard](2026-06-16-director-observability-dashboard.md)), the
telemetry producer ([worker-telemetry-capture](2026-06-16-worker-telemetry-capture.md)),
the operator console ([operator-console](2026-06-18-director-operator-console.md)),
and the polish slice ([observability-polish](2026-06-18-observability-polish.md),
which added Layer-2 live token accrual + SSE + cross-run history).

## Problem

Today the dashboard answers *"what is the run doing in aggregate, and how did each
ticket end?"* — run-level `codex_totals`/`rate_limits`, in-flight rows with **live
mid-turn token totals**, terminal `recent` rows (final tokens/turns/session_id/
last_message), stuck, pending queue, cross-run history. What it cannot answer is
**"what is *this* ticket's worker doing *right now*, step by step?"** — the
play-by-play of a single in-flight ticket (its tool calls, agent messages, turn
boundaries) and how that ticket's telemetry (tokens, tool count, turns) evolved
*over time* rather than just its latest/final value.

The data already exists and already passes through a single chokepoint, but it is
**observed and thrown away**. Every worker turn — codex *and* the claude adapter —
streams JSON-RPC notifications through `AppServerClient.on_event`
(`director/worker/app_server.py:351,413`): `turn/started`, `item/completed`
(agent messages with `phase` ∈ commentary|final_answer, and tool-call items),
`thread/tokenUsage/updated`, `turn/completed`|`failed`|`cancelled`. The
orchestrator wires that firehose per-ticket at `director/orchestrator.py:456`
**solely to siphon off token usage** (`_enqueue_usage` → `extract_usage` → drop
everything else). The tool-call / message / lifecycle play-by-play is seen on the
worker-pool thread and discarded.

The dashboard is a **separate process that reads the filesystem** (`status.json`,
`queue/`, `runs.jsonl`) — it has no live IPC into the orchestrator (the file-bridge
is the deliberate producer/consumer decoupling, R3 "visibility never gates a run").
So surfacing the per-ticket play-by-play means **capturing it to a file the
dashboard can tail**, exactly as `status.json`/`runs.jsonl` already bridge the two
processes. An in-memory ring in the orchestrator would be unreachable from the
dashboard process.

## Requirements

Each is independently verifiable (a human can check it).

- **R1 — Normalized event taxonomy (pure).** A pure `normalize_event(method,
  params, …)` maps one raw turn-stream notification to a small, runtime-agnostic
  record, or `None` to drop it. Normalized `kind` ∈ {`turn_started`,
  `agent_message`, `tool_call`, `token_usage`, `turn_ended`}, with an unrecognized
  but item-bearing notification falling back to a generic `kind="item"` carrying the
  raw `item.type` (forward-compatible — the version-pinning discipline of
  `agent_message_text`/`extract_usage`). Dropped: `item/started` placeholders,
  `item/agentMessage/delta` streaming deltas (the completed item carries the full
  text), and notifications carrying no recognizable payload. The SAME normalizer
  covers both worker runtimes because the claude adapter
  (`worker-runtime/app-server/src/translator.ts`) emits the identical vocabulary
  (`item/completed` agentMessage phases, `thread/tokenUsage/updated`, `turn/*`).

- **R2 — Durable per-ticket event log (best-effort, single-writer).** A
  `TicketEventWriter.record(ticket_id, event)` appends one normalized record as a
  JSON line to `<events_dir>/<sanitized_ticket_id>.jsonl`. Append-only (a torn final
  line from a crash is tolerated on read — the `history.py` grain, NOT atomic
  replace). Best-effort by contract (R3 posture): any write failure is swallowed and
  recorded in `last_error`, never raised — a session-event write must never gate
  dispatch. A `NoopTicketEventWriter` (records nothing) is the default for library
  calls and tests so orchestration is byte-identical when the layer is off. Records
  are written **directly from the worker-pool thread without a main-thread marshal**,
  because `on_event` for a given `ticket_id` only ever fires on that ticket's own
  dispatch thread and a retry runs only after the prior attempt's future completed —
  so each file has exactly one writer at a time (contrast the token-accrual path,
  which must marshal because all tickets share one `StatusWriter` model). Retries of
  the same ticket append to the same file (a free full-attempt history).

- **R3 — Tolerant bounded read.** `read_events(ticket_id, …, limit=N)` returns the
  last `N` normalized records for a ticket, oldest-first; a missing file → `[]`, a
  torn/partial line is skipped (never raises), an unreadable file → `[]` (the
  `read_history` contract). The read is bounded (glance-able tail, not an analytics
  store); per-file growth is bounded by a write soft-cap with a one-time truncation
  sentinel for the pathological case.

- **R4 — Derived per-ticket telemetry timeseries (pure).** A pure
  `derive_timeseries(events)` computes the per-ticket telemetry the user asked for
  *from the event log itself* (no separate producer): cumulative token totals at each
  `token_usage` point (the timeseries), tool-call count by tool name, turn count, and
  per-turn wall-clock derived from `turn_started`/`turn_ended` timestamps. Tolerant:
  an empty/garbage event list yields a well-formed zero record, never raises.

- **R5 — Live per-ticket stream + history routes (dashboard, read-only, fenced).**
  Two new GET routes on the existing dashboard:
  `GET /api/v1/ticket/{id}/events` → `{ticket_id, events, telemetry, count}` (R3+R4),
  and `GET /api/v1/ticket/{id}/stream` → an SSE tail that pushes the ticket's event
  view on change (reusing `_stream_loop` with a poll fallback, the R14 fail-soft
  posture). The `{id}` path segment is **sanitized to `[A-Za-z0-9._-]+`** (reject
  `.`/`..`/empty/separators → 404); `events_dir` comes from the SERVER, never the
  request — so there is no request-derived filesystem path beyond a vetted id segment,
  preserving the dashboard's zero-traversal posture. Reads stay unfenced (no new
  write route, no new exec surface).

- **R6 — Per-ticket drill-down UI.** The single-page dashboard gains a per-ticket
  drill-down: an in-flight or recent row can be expanded to a panel that opens an
  `EventSource` to that ticket's `/stream` and renders its live event timeline plus a
  compact telemetry strip (tokens-over-time, tool counts, turns). Every value is
  written via `textContent` (never `innerHTML`) — producer text can never be parsed
  as markup, matching the existing XSS-safe discipline. Closing the panel closes the
  `EventSource` (bounded open connections).

- **R7 — Uniform across runtimes.** The full path (capture → file → routes → UI)
  works identically for a codex worker and a claude (`--worker claude`) worker, with
  no per-runtime branching, because both emit the same normalized vocabulary (R1).

## Design

Additive throughout. New producer module + one orchestrator wiring point + new
dashboard routes/UI. The worker protocol, the guardrail path, `status.py`,
`history.py`, `queue/`, and `decider.py` are unchanged. The layer obeys the
established R3 invariant: a read-only instrument, never a gate.

### Components & files

- **NEW `director/ticket_events.py`** — the whole producer surface, stdlib-only,
  pure helpers + a best-effort writer, mirroring `status.py`/`history.py`:
  - `normalize_event(method, params, *, seq, now) -> dict | None` (R1). Reuses
    `app_server.agent_message_text` and `app_server.extract_usage` (no `app_server`
    change). Record shape: `{seq, ts, kind, …kind-specific fields}` — e.g.
    `agent_message` → `{phase, text}` (text clipped); `tool_call` → `{tool, summary}`
    (name + a clipped summary, **not** full tool output); `token_usage` →
    `{tokens:{input,output,total}}`; `turn_started`/`turn_ended` →
    `{turn_id, status?}`.
  - `TicketEventWriter` / `NoopTicketEventWriter` (R2). The writer holds a per-ticket
    in-memory `seq` counter, seeded on first touch from the existing line count so
    `seq` stays monotonic across process restarts; `_append` does
    `mkdir(parents,exist_ok)` + `open("a")` + one JSON line, all under a swallow-all
    `try/except` recording `last_error`. Write soft-cap + truncation sentinel.
  - `read_events(ticket_id, base=None, limit=…) -> list[dict]` (R3) — the
    `read_history` tolerance pattern (decode `errors="ignore"`, skip torn lines).
  - `derive_timeseries(events) -> dict` (R4) — pure, tolerant.
  - `_root`/`_events_path`/`_sanitize_id` + `$DIRECTOR_EVENTS_DIR` override and the
    `.claude/harness/director-events` default (sibling of status/queue/history; the
    dir is already covered by the existing `.claude/harness/` gitignore).

- **`director/orchestrator.py`** — construct one `TicketEventWriter` pointed at the
  events dir (sibling of the active status dir; `NoopTicketEventWriter` when the
  status surface is off, so the off-path stays byte-identical). Fan the existing
  per-ticket `on_event` closure (`orchestrator.py:456`) to BOTH the usage marshal
  (unchanged) and `self.events.record(tid, normalize_event(...))`. The normalize +
  record is itself exception-total at the callback boundary (the same R12/R14
  reasoning that guards `_enqueue_usage`): a hiccup drops the event, never gates the
  observed turn. ~1 field + ~2 lines + the constructor wiring.

- **`director/dashboard.py`** — an `events_dir` field on `_DashboardServer` (set in
  `serve`, like `status_dir`/`queue_dir`/`history_dir`); `_route` recognizes the
  `/api/v1/ticket/` prefix, parses + sanitizes the id, and dispatches to
  `_ticket_events` (R5 history, via `read_events`+`derive_timeseries`) or
  `_ticket_stream` (R5 SSE, via `_stream_loop` over a ticket view_fn); the inline
  `PAGE` gains the R6 drill-down JS + CSS; `main()` gains `--events-dir`. The existing
  routes/streams are untouched (the new ticket stream is a *second*, independent
  `EventSource`).

- **Tests** — `tests/test_ticket_events.py` (normalize taxonomy incl. both-runtime
  shapes + drop cases; writer round-trip incl. torn-line tolerance, soft-cap,
  single-writer/retry-append; `derive_timeseries`) and extensions to the dashboard
  tests (the two routes, id sanitization / traversal rejection → 404, the SSE
  ticket-tail change-detect).

- **Docs** — `docs/DIRECTOR.md` dashboard section (the new routes + drill-down);
  register this spec in `docs/product-specs/index.md`; cross-link the dashboard +
  polish specs.

### Key behaviors & edge cases

- **Capture path is best-effort and off-path-clean.** Failures swallowed (R3);
  `Noop` writer when off → orchestration byte-identical (the `NoopStatusWriter`
  precedent).
- **Concurrency.** Per-file single-writer-at-a-time (R2 rationale) → direct append,
  no marshal. The dashboard reader is tolerant of a torn final line (R3).
- **Traversal.** Request-derived id is sanitized before any path join; `events_dir`
  is server-held — zero traversal surface (R5). This is the one security-relevant
  change (a request→filesystem-path mapping on a read route); the ExecPlan's review
  budget includes **review-security** (the dashboard is the live exec surface).
- **Volume.** Curated taxonomy (deltas/placeholders dropped) + clipped text/summaries
  + bounded read + write soft-cap keep both disk and the streamed payload glance-able.
- **Telemetry is derived, not a second producer (R4)** — the event log is the single
  substrate; DRY with the existing aggregate telemetry in `status.json`.

## Non-goals (YAGNI / scope fence)

- **Full tool I/O / transcript capture.** Persist a clipped *summary* per tool call,
  not full stdout/stdin/file-diff bodies (that is a debugger, not an observability
  glance; and an unbounded disclosure surface).
- **Event-log GC / rotation / retention.** Records are tiny and the read is bounded;
  rotation is deferred exactly as `history.py` defers it (a documented limit, a
  trivial future add if a long-lived daemon needs it).
- **A new write/act route or any change to the worker protocol, decider, merger,
  guardrail, or board ownership.** Capture-and-display only.
- **Cross-ticket / cross-run event aggregation or search.** Per-ticket drill-down
  only; the existing run-aggregate + cross-run history already cover the macro view.
- **A config knob to disable the layer.** Default-on best-effort (cheap, swallowed
  failures); `Noop` covers the library/test off-path. A `.harness.json` knob is a
  trivial later add if a need appears — not now.

## Acceptance criteria

1. A daemon run (`--daemon`) processing one ticket produces
   `.claude/harness/director-events/<id>.jsonl` whose lines are normalized records —
   `turn_started`, `agent_message` (commentary + final_answer), `tool_call`,
   `token_usage`, `turn_ended` — in order. (`cat` / a unit test over a recorded
   stream.)
2. `curl -s http://127.0.0.1:<port>/api/v1/ticket/<id>/events | jq` returns
   `{ticket_id, events:[…], telemetry:{…}, count}` with the derived token timeseries,
   tool-call counts, and turn count.
3. Driving the dashboard with the `playwright-cli` skill: open `/`, expand a ticket
   row, and observe its event timeline + telemetry strip update **live** via the
   ticket SSE while the worker runs.
4. `GET /api/v1/ticket/..%2f..%2fetc%2fpasswd/events` (and any id with a separator /
   `.`/`..`) → `404`, never a file outside `events_dir`.
5. The same flow (1–3) succeeds with a `--worker claude` worker, byte-identical UI
   path (R7).
6. The gate is GREEN (`python3 plugin/scripts/check.py`) with the new producer +
   dashboard unit tests; the off-path (`Noop` writer) leaves orchestration
   byte-identical.

## Hand-off

ExecPlan in `docs/exec-plans/active/2026-06-24-per-ticket-session-event-stream.md`
references this spec and owns the build (milestone order: producer module + tests →
orchestrator wiring + a live single-ticket capture proof → dashboard routes + id
sanitization → drill-down UI + the playwright behavioral pass → cross-runtime
proof). `review_level: full` — the dashboard is the live exec surface and the diff
adds a request→path mapping, so **review-security** is in budget alongside the
always-on spec-compliance + code-quality and the arch/reliability personas.
