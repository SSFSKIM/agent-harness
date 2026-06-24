---
status: active
last_verified: 2026-06-24
owner: harness
type: exec-plan
description: Build the per-ticket session-event layer — capture the worker turn-stream firehose into a per-ticket JSONL, serve it as a live SSE drill-down + derived telemetry, uniform across codex and claude workers.
base_commit: 3ca406220b31af5d8eec09e79347026e53d65a1c
review_level: full
---
# Per-ticket session-event stream — build

## Goal

A person watching the Director dashboard can **expand any in-flight or recent
ticket row and watch that ticket's worker run step by step, live** — its turn
boundaries, agent messages, tool calls, and token accrual streaming in as they
happen — plus a compact per-ticket telemetry strip (tokens-over-time, tool-call
counts, turn count) derived from that same stream. Concretely, done means: a
daemon run writes `.claude/harness/director-events/<ticket_id>.jsonl` of
normalized records; `GET /api/v1/ticket/<id>/events` returns
`{ticket_id, events, telemetry, count}`; `GET /api/v1/ticket/<id>/stream` pushes
the ticket's events over SSE; the page renders an expandable drill-down; a
traversal-shaped id (`..%2f…`) is rejected with 404; and the whole path works
byte-identically for a codex worker and a `--worker claude` worker. The gate
(`python3 plugin/scripts/check.py`) is GREEN and the off-path (Noop writer)
leaves orchestration byte-identical.

## Context

Build from the spec — it owns the design; this plan owns the build (no
re-derivation):
[per-ticket-session-event-stream](../../product-specs/2026-06-24-per-ticket-session-event-stream.md)
(R1–R7, the four locked decisions: clipped tool *summary* not full I/O,
default-on best-effort, no GC, per-ticket files).

Grounding a novice needs:
- **Event source** — `director/worker/app_server.py`: `AppServerClient` runs one
  worker turn and forwards every JSON-RPC notification to `self.on_event({method,
  params})` (lines 351, 413). Helpers already pin the vocabulary:
  `agent_message_text` (line 87 — `item/completed` agentMessage → `(text, phase)`),
  `extract_usage` (line 147 — `thread/tokenUsage/updated` → `{input,output,total}`),
  `extract_rate_limits`. Turn lifecycle methods: `turn/started`,
  `turn/completed`|`failed`|`cancelled`.
- **The firehose tap** — `director/orchestrator.py`: `_RunState.submit` dispatches
  each ticket with `on_event=lambda ev_: self._enqueue_usage(tid, ev_)` (line 456).
  `_enqueue_usage` (line 410) extracts only usage and drops the rest; `drain_accrual`
  (line 430) marshals usage worker-pool→main-thread into the `StatusWriter`. That
  marshal exists because all tickets share one `StatusWriter` (R13 single-writer).
- **Producer grain to mirror** — `director/status.py` (atomic snapshot;
  `NoopStatusWriter` off-path) and `director/history.py` (append-only JSONL,
  tolerant read with `decode("utf-8","ignore")` + skip-torn-line; best-effort
  `append_run` swallows failures; `_root` with `$ENV` + `.claude/harness/` default).
- **Consumer to extend** — `director/dashboard.py`: `build_view` (pure),
  `_stream_loop` (injectable SSE push with change-detect + heartbeat + fail-soft),
  `_Handler._route` (exact-path `_ROUTES` map), `_DashboardServer` (carries
  `status_dir`/`queue_dir`/`history_dir`), the inline `PAGE` (vanilla-JS, SSE with
  poll fallback, `textContent`-only render).
- **Cross-runtime equivalence** — `worker-runtime/app-server/src/translator.ts`
  emits the SAME vocabulary (`item/completed` agentMessage phases,
  `thread/tokenUsage/updated` incl. the new usage-heartbeat, `turn/*`), so one
  normalizer covers both.

## Approach (self-generated alternatives)

- **A — In-orchestrator capture to a per-ticket file (chosen).** A new
  `director/ticket_events.py` (pure normalizer + best-effort per-ticket JSONL writer,
  `status.py`/`history.py` grain). The orchestrator's per-ticket `on_event` closure
  fans to both the existing usage marshal AND `events.record(tid,
  normalize_event(...))`. The dashboard tails the file over two new GET routes.
  Tradeoff: one new producer module + a wiring point + dashboard routes — but each
  per-ticket file is single-writer (the `on_event` for a tid only fires on that
  ticket's pool thread; a retry runs only after the prior future completed), so the
  writer appends DIRECTLY with no main-thread marshal. Cleanest fit to the file-bridge
  architecture; the dashboard process can read it with zero new IPC.
- **B — Marshal events to the main thread like usage, hold in `StatusWriter`, write
  via `status.json`.** Reuse the existing `accrual` queue + main-thread drain.
  Tradeoff: forces all per-ticket play-by-play through one shared model and one atomic
  snapshot — fattens `status.json` with high-volume event data it was never meant to
  hold (it is rewritten atomically on every transition), couples event volume to
  snapshot-write cost, and needs the marshal the per-ticket-file design avoids.
  Rejected: wrong data shape for an atomic snapshot; reintroduces the marshal for no
  gain.
- **C — In-memory ring in the orchestrator + a new IPC channel (socket) the dashboard
  reads.** Tradeoff: no new files, truly live — but the dashboard is a SEPARATE
  process with NO live channel to the orchestrator today; adding a socket/IPC is a new
  exec surface and breaks the deliberate file-bridge decoupling (and loses durability /
  replay / the cross-restart history the file gives for free). Rejected: largest blast
  radius, contradicts the R3 read-only-file-instrument posture.
- **Chosen: A** — smallest blast radius, matches the established producer grain, gives
  durability + the single-writer simplification, and keeps the dashboard a pure
  file-reader. (Mirrored to Decision log.)

## Assumptions & open questions (self-interrogation)

- **Assumption: `on_event` for a given `tid` is single-threaded over that ticket's
  lifetime** (one dispatch thread per attempt; retries serialized after the prior
  future reaps). If wrong, two threads could append to one file and interleave —
  breaks R2's no-marshal claim. Mitigation: append is one `write()` of one line, and
  the read is torn-line tolerant, so even a worst-case interleave degrades to a
  skipped line, never a crash. (Verified by reading the dispatch/reap path; holds.)
- **Assumption: clipped text/summary + curated kinds keep per-file size glance-able**
  within one ticket's lifetime, so no GC is needed for v1 (spec decision #3). What
  breaks if wrong: a pathological multi-hour ticket grows a large file — bounded by
  the write soft-cap + truncation sentinel (read already returns only the last N).
- **Assumption: the dashboard's SSE `_stream_loop` change-detect generalizes** to a
  per-ticket view (it diffs a stable projection). The ticket view_fn returns the
  bounded event list; growth changes the projection → a frame is pushed. Holds —
  same lever as `build_view`.
- **Open: exact non-agentMessage `item.type` strings for tool calls (codex
  `commandExecution`/`fileChange`; claude broker `item/completed` completed/failed).**
  Resolved autonomously: the normalizer maps the KNOWN kinds (agentMessage, the two
  approval-bearing exec types) and falls back to a generic `kind="item"` carrying the
  raw `item.type` for anything else — forward-compatible, the version-pinning
  discipline already used by `agent_message_text`. Pin the precise strings against the
  live stream in M2 and tighten the map if needed (no escalation — mechanical).
- **Open: default-on vs a config knob.** Resolved per spec (default-on best-effort;
  `Noop` off-path) — no `config.py` change, smaller blast radius. Not a taste fork.

## Milestones

- **M1 — Producer module + unit tests.** Scope: the entire `director/ticket_events.py`
  surface, pure-first and fully unit-tested without a socket or a live worker. At the
  end there newly exists: `normalize_event(method, params, *, seq, now)` (the R1
  taxonomy — `turn_started`/`agent_message`/`tool_call`/`token_usage`/`turn_ended`,
  generic `item` fallback, drops for deltas/placeholders/unrecognized), reusing
  `app_server.agent_message_text`/`extract_usage`; `TicketEventWriter` +
  `NoopTicketEventWriter` (R2 — best-effort append, per-tid `seq` seeded from existing
  line count, write soft-cap + truncation sentinel, `last_error`); `read_events`
  (R3 — bounded, torn-line tolerant); `derive_timeseries` (R4 — pure, tolerant);
  `_root`/`_events_path`/`_sanitize_id`. Run: `python3 -m pytest tests/test_ticket_events.py -q`.
  Acceptance: tests prove the taxonomy maps a recorded codex-shaped AND claude-shaped
  notification identically, drops the right ones, the writer round-trips through a torn
  final line, the soft-cap engages with a sentinel, and `derive_timeseries` yields the
  cumulative token series + tool/turn counts. The gate (`check.py`) is GREEN.
- **M2 — Orchestrator wiring + a live single-ticket capture proof.** Scope: the one
  firehose tap. At the end the orchestrator constructs a `TicketEventWriter` at the
  events dir (sibling of the active status dir; `Noop` when the status surface is off,
  so the off-path is byte-identical) and the per-ticket `on_event` closure
  (`orchestrator.py:456`) ALSO calls `events.record(tid, normalize_event(method,
  params, ...))`, exception-total at the callback boundary (the `_enqueue_usage`
  R12/R14 reasoning). Run: a scratch live probe (reuse the `heartbeat_probe.py`
  pattern — one real claude turn doing a tiny Bash + a reply) pointed at a temp events
  dir. Acceptance: the probe leaves `<events_dir>/<id>.jsonl` containing, in order,
  `turn_started`, ≥1 `agent_message`, ≥1 `tool_call`, ≥1 `token_usage`, `turn_ended`;
  and a unit/wiring test asserts the closure records normalized events while a Noop
  writer changes nothing. Gate GREEN. (Pin the exact tool-call `item.type` here and
  tighten `normalize_event` if the live shape differs from M1's fixtures.)
- **M3 — Dashboard routes + id sanitization + tests.** Scope: the read/stream surface.
  At the end `_DashboardServer` carries `events_dir`; `_route` recognizes the
  `/api/v1/ticket/` prefix, parses + `_sanitize_id`s the segment (reject
  `.`/`..`/empty/separator → 404), and dispatches to `_ticket_events`
  (`read_events`+`derive_timeseries` → `{ticket_id, events, telemetry, count}`) or
  `_ticket_stream` (`_stream_loop` over a ticket view_fn, fail-soft); `main()` gains
  `--events-dir`. Run: `python3 -m pytest tests/test_dashboard*.py -q` + a manual
  `curl` against a temp events dir. Acceptance: tests prove the events route returns
  the derived view, the stream route pushes on growth, and EVERY traversal-shaped id
  (`..%2f..%2fetc`, `a/b`, ``, `.`) → 404 with no path escaping `events_dir`. Gate GREEN.
- **M4 — Drill-down UI + playwright behavioral pass.** Scope: the page. At the end an
  in-flight/recent row is expandable to a panel that opens an `EventSource` to the
  ticket `/stream`, renders the event timeline + telemetry strip via `textContent`
  only, and closes the `EventSource` when collapsed (bounded connections). Run: start
  the dashboard against a temp events dir with a seeded ticket log, drive with the
  `playwright-cli` skill (open `/`, expand the row, observe events render; confirm a
  live-appended line shows up). Acceptance: a captured snapshot/transcript shows the
  ticket's events + telemetry rendered live in the expanded panel; no `innerHTML` of
  producer text. Gate GREEN.
- **M5 — Cross-runtime proof + completion gate.** Scope: parity + review. At the end a
  short live run with a `--worker claude` worker (the live opt-in) is shown to produce
  the same normalized log + UI path as codex (R7), and `docs/DIRECTOR.md` documents the
  routes + drill-down. Run: the completion-gate sequence (gate → behavioral recap →
  self-review of `git diff 3ca4062..HEAD` → always-on spec-compliance then
  code-quality via `/codex:rescue --model gpt-5.5 --effort high`, fallback Claude →
  full risk personas review-arch/review-reliability/review-security). Acceptance: all
  verdicts SATISFIED (P1s fixed + gate re-run; P2s → Feedback + tech-debt-tracker),
  plan moved to `completed/`.

## Progress log
- [x] (2026-06-24) Spec authored + committed (3ca4062). ExecPlan created from template.
- [x] (2026-06-24) M1 producer module + 22 unit tests GREEN, committed.
- [x] (2026-06-24) M2 orchestrator wiring (fan-out `_observe_event`, events threaded
  through run_once/until_drained/forever + main) + 3 wiring tests; DISCOVERED the
  claude adapter dropped tool calls → extended `translator.ts` (+extractToolUses
  +toolCall emit, 3 TS tests, 54 unit GREEN, dist rebuilt). Live probe: all five kinds
  (turn_started/tool_call/agent_message/token_usage/turn_ended) captured from a real
  claude Bash turn, telemetry derives `tools:{Bash:1}`. PASS.
- [x] (2026-06-24) M3 dashboard routes: `/api/v1/ticket/{id}/events` (history+telemetry)
  + `/stream` (SSE tail, reusing `_stream_loop`), `events_dir` on the server + `--events-dir`,
  id sanitized before any path join. +6 dashboard tests (events view+telemetry, unknown→empty,
  SSE initial frame, every traversal id→404, malformed paths→404, POST→405). 50 GREEN.
- [ ] M4 drill-down UI + playwright
- [ ] M5 cross-runtime proof + reviews

## Surprises & discoveries
- 2026-06-24 (M2, live-probed): the **claude adapter never emitted tool calls**.
  `worker-runtime/app-server/src/translator.ts onMessage` only forwarded assistant
  TEXT (`extractAssistantText`); SDK `tool_use` blocks (Bash/Read/Edit — the bulk of a
  ticket's play-by-play) were dropped, so the on_event firehose for a claude worker
  carried only turn-lifecycle + agentMessages + tokenUsage. Confirmed by two live
  probes: `raw item.types seen: ['agentMessage']` only. codex emits
  `commandExecution`/`fileChange` natively (hence `APPROVAL_METHODS`), so the gap was
  claude-only — but the user CHOSE the claude worker, so the spec's Goal ("watch its
  tool calls") + R7 ("uniform across runtimes") require the adapter to emit them.
  Decision: extend the translator to translate `tool_use` → `item/completed` (item.type
  `toolCall`, which `normalize_event` already recognizes) — an in-scope addition, not a
  deferral. The Python capture layer was already correct; the upstream adapter was the
  missing half.

## Decision log
- 2026-06-24: extend `translator.ts` to emit `toolCall` items (built-in SDK tool use) —
  see Surprises. Bounded at capture: the Director clips the arg summary to SUMMARY_CLIP,
  so a large tool INPUT (e.g. a Write body) never bloats the on-disk log.
- 2026-06-24: Chose Approach A (in-orchestrator capture to per-ticket file) over the
  status.json-marshal (B) and in-memory-IPC (C) approaches — smallest blast radius,
  matches the producer grain, single-writer-per-file removes the marshal, keeps the
  dashboard a pure file-reader.
- 2026-06-24: `review_level: full` — the dashboard is the live exec surface and the
  diff adds a request→filesystem-path mapping on a read route, so review-security is in
  budget alongside the always-on QA reviews + arch/reliability.

## Feedback (from completion gate)

## Outcomes & retrospective
