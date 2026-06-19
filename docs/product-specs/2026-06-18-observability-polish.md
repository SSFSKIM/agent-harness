---
status: stable
last_verified: 2026-06-19
owner: harness
---
# Deferred observability polish — live token accrual · SSE · rate-limit view · cross-run history

> **Built (2026-06-19).** All scoped slices shipped on branch `obs-polish`, each
> gate-GREEN + reviewed: Layer-2 token accrual (R1–R3,
> [layer2-token-accrual](../exec-plans/completed/2026-06-18-layer2-token-accrual.md)),
> SSE + rate-limit (R4–R6,
> [dashboard-sse-rate-limit](../exec-plans/completed/2026-06-19-dashboard-sse-rate-limit.md)),
> and cross-run history (R7–R8,
> [cross-run-history](../exec-plans/completed/2026-06-19-cross-run-history.md)).
> Multi-run aggregate view remains the one deliberate deferral (no producer fan-out yet).

The "deferred observability polish" track the read-dashboard
([director-observability-dashboard](2026-06-16-director-observability-dashboard.md))
and the telemetry slice
([worker-telemetry-capture](2026-06-16-worker-telemetry-capture.md)) named as
non-goals / Layer-2 follow-ups, now that the observability surface is actionable
([operator-console](2026-06-18-director-operator-console.md)). It picks up four of
the deferred items and **defers a fifth** (multi-run aggregate view). This is a
*consumer-richness* track: the producer (`status.py`) and the surface
(`dashboard.py`) already exist; this makes the live picture richer (tokens accrue
mid-turn, rate-limit headroom is legible), pushes it instead of polling it, and —
in a later phase — remembers it across runs.

Parent comparison: [symphony-parity-gap](../design-docs/symphony-parity-gap.md)
(Phase 5 observability track). Grounding rules: **RELIABILITY R12** (instrument
extractors are total), **R13** (status writers are main-thread lock-free
single-writers; *any live mid-turn accrual must marshal to the main thread*),
**R14** (read-API listeners fail soft, never to a dropped connection), **R16**
(cross-thread coordination uses thread-safe primitives) — and the `director/`
host-runtime invariants in `ARCHITECTURE.md` (stdlib-only · explicit `base=` ·
loopback/fixed-route listeners · pure-core / thin-transport).

## Problem (what is unsatisfied today — observable)

1. **Token totals are dead until a turn ends.** `StatusWriter` folds a ticket's
   tokens into the run aggregate **only at `terminal()`** (`status.py:139`), so
   while a worker grinds through a long multi-turn ticket the dashboard's headline
   `codex_totals` and the in-flight rows show **nothing** for that ticket — cost is
   invisible exactly when it matters most (a long, expensive turn). `seconds_running`
   *is* already live (computed at `snapshot()`); tokens are not. Observable: dispatch
   a real worker, watch the dashboard — the run-total token count does not move until
   the ticket reaches terminal, then jumps.
2. **The view is pulled, not pushed.** The page re-fetches `/api/v1/state` on a
   fixed `setInterval(…, 1000)` (`dashboard.py:308`). Every tab re-polls regardless
   of whether anything changed; the server can't push a fresh snapshot the instant
   one is written. (The read-dashboard left SSE as an explicit "upgrade if 1s feels
   laggy" — D-3; the human has now elected to build it, D-1 below.)
3. **Rate-limit headroom is rendered as raw JSON.** `run.rate_limits` flows all the
   way through `build_view` (pass-through) but the page renders it as
   `"rate " + JSON.stringify(run.rate_limits)` (`dashboard.py:240`) — unreadable;
   an operator can't glance and tell how close the run is to a throttle.
4. **Nothing survives a run.** `recent` is a bounded tail (`RECENT_MAX = 20`) on a
   per-run `StatusWriter` instance; when a run ends the picture is gone. There is no
   way to ask "how many tokens / how long / what success rate across the last N
   runs" — no cross-run trend, by explicit prior non-goal
   (`2026-06-16-director-observability-dashboard.md` Non-goals "cross-run history").

## Requirements

Phased. **v1 = R1–R6** (live accrual + SSE + rate-limit view). **Phase B = R7–R8**
(cross-run history). **R9** (blast radius) binds both. Each Rn is independently
human-verifiable.

### v1 — live accrual

- **R1 — Run-level token total accrues live across in-flight tickets.** The snapshot's
  `run.codex_totals.{input,output,total}` reflects the cumulative tokens of *ended*
  tickets **plus** the latest in-flight usage of *running* tickets, recomputed at
  snapshot time (mirroring `seconds_running`). *Verifiable:* with one ended ticket
  (1000 tok) and one in-flight ticket whose latest usage is 400 tok, the snapshot's
  `run.codex_totals.total == 1400`; advancing the in-flight ticket's usage to 600 →
  `1600`, with no second ended ticket.
- **R2 — In-flight rows carry live per-ticket tokens.** Each `in_flight[]` entry gains
  a `tokens: {input,output,total}|None` field reflecting that ticket's latest absolute
  usage (None until the first usage event). *Verifiable:* a snapshot taken mid-turn
  shows the running ticket's `tokens` populated; the dashboard renders it on the
  in-flight row.
- **R3 — Accrual marshals to the main thread; no double-count at terminal.** Per-event
  usage is observed on the **worker-pool thread** but applied to the `StatusWriter`
  **only on the orchestrator's main thread** (R13) via a thread-safe channel (R16);
  the worker thread never touches the writer's model. When a ticket terminates, its
  tokens move from the live in-flight sum into the ended aggregate **atomically** (same
  `terminal()` call pops the in-flight entry), so the run total is continuous and never
  counts a ticket twice. *Verifiable:* (a) a unit test asserting the pool thread only
  enqueues (never mutates the writer); (b) a test driving accrue→terminal shows the run
  total does not jump/drop at the boundary beyond the final-vs-last-accrued delta;
  (c) the existing `NoopStatusWriter` path and batch summaries stay byte-identical.

### v1 — transport & rate-limit view

- **R4 — Server-pushed updates via SSE.** A new `GET /api/v1/stream` returns
  `text/event-stream` and pushes a `data:`-framed `build_view` payload whenever the
  view changes (server-side change detection on the snapshot), plus a periodic
  heartbeat. The page consumes it via `EventSource` and re-renders on each event,
  **falling back to the existing ~1s poll** if the stream errors or is unsupported.
  *Verifiable:* connecting to `/api/v1/stream` (e.g. `curl -N`) yields an initial
  `data:` event with the current view and a further event after the snapshot changes;
  with SSE disabled/broken the page still updates by poll.
- **R5 — The stream is fail-soft (R14) and stateless-per-connection.** A client that
  disconnects mid-write is a quiet drop (full errno family, not just EPIPE); a handler
  bug never reaches `socketserver.handle_error`/stderr; the stream sets no
  `Content-Length` and never blocks `GET /` or `GET /api/v1/state` (both byte-unchanged).
  The stream holds no cross-run state and is read-only (no queue/status mutation).
  *Verifiable:* killing a streaming client leaves the server serving; `GET /api/v1/state`
  and `GET /` responses are unchanged from today.
- **R6 — Rate-limit headroom is legible, tolerantly.** The page renders `run.rate_limits`
  as a glance-able summary (e.g. "rate: 42% used · resets 3m" with a small bar) when the
  payload exposes recognizable fields, and degrades to a compact summary for an
  unrecognized shape — never a raw `JSON.stringify` dump, never a render crash on a
  missing/odd field (client-side R12 discipline). *Verifiable:* a payload with
  used-percent/reset fields renders the summary+bar; `{"remaining": 9}` (the current
  test shape) and `null` both render without error.

### Phase B — cross-run history

- **R7 — Completed runs are persisted across runs.** At run completion a compact
  run-summary record is appended (append-only) to a history store, and a tolerant
  reader returns the last N records. The record carries
  `{started_at, ended_at, stopped_reason, passes, codex_totals{input,output,total,
  seconds_running}, ticket_count, outcomes:{<status>:count}}`. *Verifiable:* run two
  batch runs to completion; the store has two records with correct token/outcome
  rollups; a torn/absent store reads as `[]` (never raises).
- **R8 — The dashboard shows cross-run history.** A new `GET /api/v1/history` returns
  the last N records as JSON and the page renders a compact history panel (per-run
  tokens, duration, outcome counts). *Verifiable:* with two persisted runs the panel
  lists both with their metrics; with no store the panel shows "no history" and the
  rest of the page is unaffected.

### Both phases

- **R9 — Additive; existing contracts preserved; gate GREEN.** Producer changes to
  `status.py` are additive (new field defaults to None; `NoopStatusWriter` unchanged;
  every existing reader/test still valid). `GET /api/v1/state` JSON stays a superset
  of today's (new keys only). The orchestrator's batch return dict and disposition
  shapes are unchanged. `python3 plugin/scripts/check.py` is GREEN.
  *Verifiable:* diff shows only additive fields/routes/modules; full gate passes.

## Design

### Component map

| File | Phase | Change | Responsibility |
|---|---|---|---|
| `director/status.py` | v1 | extend | `in_flight[].tokens` field; new `accrue(ticket, usage)` transition (main-thread, tolerant); `snapshot()` makes `codex_totals` a LIVE sum (ended + in-flight) like `seconds_running` |
| `director/orchestrator.py` | v1 | extend | a thread-safe `queue.Queue` on `_RunState`; `submit()` wires a per-ticket `on_event` callback; both main loops (`_dispatch_wave`, `run_forever`) **drain** it to `status.accrue` each tick (coalesced, one flush) |
| `director/run.py` | v1 | extend | thread an optional `on_event` param through `drive`/`run_ticket` → `_prepare` → `AppServerClient(on_event=…)` |
| `director/worker/app_server.py` | v1 | **none** (reuse) | `on_event` already fires per notification; `extract_usage` already exists — the orchestrator's callback reuses both (no producer change) |
| `director/dashboard.py` | v1 | extend | `GET /api/v1/stream` (SSE), reusing `build_view`; rate-limit + live-token render in `PAGE`; `EventSource` + poll fallback |
| `director/history.py` | B | **new** | `append_run(summary, base=…)` (append-only JSONL) + `read_history(base=…, limit=N)` (tolerant) — stdlib-only, explicit `base=` |
| `director/orchestrator.py` | B | extend | at run completion build the summary from the final snapshot and call `history.append_run` |
| `director/dashboard.py` | B | extend | `GET /api/v1/history` route + history panel in `PAGE` |
| `tests/test_director_status.py` | v1 | extend | `accrue`, live-sum, no-double-count, additive back-compat |
| `tests/test_director_orchestrator*.py` | v1 | extend | marshal seam: pool thread only enqueues; main-thread drain applies; Noop path byte-identical |
| `tests/test_director_dashboard.py` | v1/B | extend | SSE event framing + fallback assertion; rate-limit render scaffolding; history route |
| `tests/test_director_history.py` | B | **new** | append/read roundtrip, tolerant on torn/absent |
| `docs/DIRECTOR.md` | v1/B | section | live accrual + SSE + history in the dashboard section |

### A. Layer-2 in-flight token accrual (producer + threading) — the heavy slice

**The marshal (R13/R16).** Usage is observed on the worker-pool thread and applied
to the `StatusWriter` only on the main thread:

```
worker-pool thread                         main thread (orchestrator tick)
──────────────────                         ───────────────────────────────
AppServerClient.run_turn                    while state.futures:
  └ on_event({method,params})  ──put──▶       done,_ = wait(futures, timeout=…)   # existing
    cb: u=extract_usage(...)    queue.Queue    state.reap(done)                    # existing
        if u: q.put((tid,u))   (R16-safe)      state.drain_accrual()   ◀── NEW: q.get_nowait()*
                                               # coalesce latest-per-tid → status.accrue → 1 flush
```

- `_RunState` gains `self.accrual = queue.Queue()` (thread-safe — R16; the *only* new
  cross-thread object besides the existing `cancel_event`).
- `submit()` builds a per-ticket callback bound to `tid` + the queue and passes it as
  `on_event=` (added per-submit, exactly like `cancel_event`):
  `cb = lambda ev: self._enqueue_usage(tid, ev)`, where `_enqueue_usage` calls
  `app_server.extract_usage(ev.get("method"), ev.get("params", {}))` and, if non-None,
  `self.accrual.put((tid, usage))`. The callback does **only** a thread-safe `put` —
  it never reaches into the writer (R13).
- `drain_accrual()` (main thread) drains the queue non-blocking, **coalesces to the
  latest usage per `tid`** (so a chatty turn yields one update, not N), and calls
  `self.status.accrue(tid, usage)` per ticket — bounding status.json rewrites to ~one
  per tick regardless of event volume (write-amplification guard). Called after `reap`
  in both `_dispatch_wave` and `run_forever`.
- **Why reuse `on_event` (not a new `app_server.on_usage`):** `on_event` already fires
  per notification and `extract_usage` already exists; reusing them leaves the producer
  (`app_server.py`) **unchanged** — smaller blast radius, single extraction site
  (D-2 below).

**StatusWriter (additive, R13).**
- `claimed()`/`_in_flight` entries gain `"tokens": None`.
- New `accrue(self, ticket, usage)`: tolerant — resolve `tid`; if it is in
  `self._in_flight` and `usage` carries integer `input/output/total`, set
  `entry["tokens"] = {input,output,total}` and `_flush()`. A `tid` not in-flight
  (already terminal) is a no-op (order-independent vs. a late queue drain). Like every
  transition, main-thread only.
- `snapshot()`: `codex_totals` becomes a LIVE aggregate, mirroring `seconds_running`:
  `{k: self._codex_totals[k] + Σ(e["tokens"][k] for in-flight e with tokens) for k in (input,output,total)}`,
  then `seconds_running` as today. `_codex_totals` still accumulates ended tickets at
  `terminal()` (unchanged), and `terminal()` still pops the in-flight entry — so the
  ticket's contribution moves ended↔live atomically with no double-count (R3).

**Threading the callback** through `run.py`: `drive(... on_event=None ...)` and
`run_ticket(... on_event=None ...)` accept it and forward to `_prepare(on_event=…)`
→ `AppServerClient(on_event=…)`; `dispatch(**kwargs)` already forwards to `drive`, so
`submit`'s `on_event=cb` reaches the client unmodified. Default `None` → the existing
no-op `on_event`, so every non-orchestrator caller is byte-unchanged.

### B. SSE transport (`dashboard.py`) — the dashboard slice

- **Route:** `GET /api/v1/stream` added to `_ROUTES` (`{"GET"}`). It does **not** go
  through `_send` (which sets `Content-Length`); a dedicated `_stream()` sends SSE
  headers (`Content-Type: text/event-stream`, `Cache-Control: no-cache`) with no
  Content-Length, then loops:
  - compute `build_view`; if its serialization **differs** from the last pushed, write
    `data: <json>\n\n` and flush; else if a heartbeat interval elapsed, write a comment
    line `: ping\n\n` (keeps the connection alive / detects a dead peer).
  - sleep a short server-side interval (`_STREAM_POLL_S`, ~0.5s) between checks — the
    server now does the polling the client used to, and pushes only on change.
  - break on client disconnect: any write hitting the errno family
    (`BrokenPipeError`/`ConnectionResetError`/`ConnectionAbortedError`/`OSError`) → quiet
    `return` (R14); no second response attempted.
- **Threading:** `ThreadingHTTPServer` already gives each connection its own thread, so
  a long-lived stream occupies one thread for its lifetime — fine for a single local
  operator (1–2 tabs). The loop is bounded only by disconnect; on `KeyboardInterrupt`/
  server shutdown the socket closes and the loop exits via the errno catch.
- **Client (`PAGE`):** add `const es = new EventSource('/api/v1/stream');
  es.onmessage = e => render(JSON.parse(e.data));` plus `es.onerror` → if the stream
  cannot connect, **fall back** to the existing `setInterval(poll, 1000)` (kept intact).
  This is graceful degradation: SSE when it works, poll when it doesn't (older proxies,
  stream death). Values still rendered via `textContent` (no `innerHTML`).
- **`build_view` is reused verbatim** — SSE is a transport over the same pure core
  (the read-dashboard's testability lever holds: the logic is still unit-tested without
  a socket; only the framing/loop is socket-bound).

### C. Rate-limit representation (`dashboard.py` `PAGE`, client-only)

- A `fmtRateLimits(rl)` JS helper, **tolerant by contract** (client-side R12): if `rl`
  exposes a recognizable used-fraction (`used_percent`/`usedPercent`, or
  `remaining`+`limit`) it renders "rate: NN% used" + a small CSS bar; if it exposes a
  **duration**-style reset hint (`resets_in_seconds`/`reset_in_seconds`/`window_minutes`)
  it appends "· resets ~Xm"; an unrecognized non-null shape (incl. an absolute-timestamp
  reset like `reset_at`, which needs no special-casing — it simply yields no reset suffix)
  degrades to a one-line compact summary (key:value pairs, clipped), and `null`/`undefined`
  renders nothing. No render path throws on a missing field. (The exact codex `rate_limits`
  shape is pinned against a live run — see Open questions; the helper is tolerant by design
  so an unanticipated field degrades, never crashes.)
- **The exact real codex payload shape is pinned in the execplan against a live codex
  run** — today's tests use a placeholder (`{"remaining": 9}`), so the helper is written
  to the *observed* shape and the placeholder/`null` are kept as degradation cases.

### D. Cross-run history (`director/history.py` + `dashboard.py`) — Phase B

- **`director/history.py`** (new, stdlib-only, explicit `base=` per the `director/`
  invariants):
  - root = explicit `base` → `$DIRECTOR_HISTORY_DIR` → `.claude/harness/director-history`
    (sibling of status/queue, gitignored).
  - `append_run(summary: dict, base=None)`: append one JSON line to `runs.jsonl`
    (open `"a"`, write `json.dumps(summary)+"\n"`). Append-only is crash-safe enough for
    a metrics log (a torn final line is tolerated on read); no temp+replace needed (it is
    not a single-object atomic snapshot like status.json).
  - `read_history(base=None, limit=RECENT_RUNS_MAX)`: read the file, parse line-by-line,
    **skip** any unparseable line (tolerant — R12), return the last `limit` records;
    missing file → `[]`.
- **Who writes:** the orchestrator at run completion (`run_until_drained` end; the daemon
  `run_forever` at graceful shutdown) builds the summary from the **final snapshot**
  (`status.read_status` or the writer's `snapshot()`) — `codex_totals`, `stopped_reason`,
  counts derived from `recent`/results — and calls `history.append_run`. A daemon's whole
  lifetime is one record (coarse but sufficient for v1 trends; finer-grained run identity
  is an Open Question). Best-effort: a history-write failure is swallowed (it is
  instrumentation, never a gate — same posture as `StatusWriter._flush`).
- **Dashboard:** `GET /api/v1/history` → `json.dumps(read_history(...))`; a history panel
  in `PAGE` rendering a compact per-run table (started/ended, total tokens, runtime,
  outcome counts). Additive route + render; no change to `/state`.

### Error handling, edge cases, integration points

- **Late accrual after terminal:** a usage event for a ticket that already terminated
  drains to `accrue(tid, …)` after its in-flight entry was popped → no-op (R3, by the
  in-flight membership check). Order-independent.
- **Coalescing vs. flush amplification:** `drain_accrual` collapses many queued events
  to one `accrue` per `tid` per tick → ~one status.json rewrite per tick (not per
  event). Without coalescing a chatty turn could fsync dozens of times/sec.
- **No run / empty in-flight:** live sum over an empty in-flight set = ended totals
  (today's behavior); `tokens: None` on rows the worker hasn't emitted usage for yet.
- **SSE + an answered pending item:** the stream pushes the new `build_view` on change,
  so an item answered from the operator console clears on the next pushed event just as
  it does on the next poll today (the console POST path is untouched).
- **SSE behind a buffering proxy:** localhost direct connection (D-5, `127.0.0.1`), no
  proxy in the supported topology; `Cache-Control: no-cache` set regardless. The client
  fallback covers any environment where the stream stalls.
- **History store growth:** `runs.jsonl` grows unbounded over a very long horizon; v1
  reads only the tail (`limit`). Rotation/compaction is a non-goal (Open Question) — a
  run record is tiny and the read is bounded.

## Non-goals (scope fence — YAGNI)

- **Multi-run aggregate view** (one dashboard across several concurrent runs). The
  producer writes a **single** `status.json`; there is no multi-status-dir fan-out to
  aggregate yet (parallel sessions *clobber*, they don't fan out). Deferred until a real
  multi-run producer exists — revisit with the parallel-sessions / shared-index work.
  (**human, 2026-06-18.**)
- **SSE auth / non-localhost / multi-client scale.** The stream inherits the dashboard's
  `127.0.0.1`-only, no-auth posture; it is sized for a single local operator, not a
  fan-out broadcast bus.
- **A push bus / event sourcing in the producer.** SSE detects change by re-reading the
  file-backed snapshot server-side; the orchestrator does **not** grow an outbound event
  channel. The snapshot stays the single source of truth.
- **Retry-burn token accounting.** Tokens from a failed-then-retried attempt are still
  excluded from the run aggregate (the existing tracked follow-up); Layer-2 changes
  *when* the final-attempt cost shows (live vs. at-terminal), not *which* attempts count.
- **History rotation / compaction / analytics.** Phase B persists and shows the last N
  runs; trend charts, retention policy, and rollups beyond per-run counts are out.
- **Per-event token deltas / streaming token rate.** Layer-2 shows the latest absolute
  per-ticket total live; a tokens/sec rate or per-event sparkline is out.

## Acceptance criteria

- **R1/R2/R3 (live accrual):** a test seeds one ended ticket + one in-flight ticket with
  a known latest usage and asserts `run.codex_totals.total` = ended + in-flight, that the
  in-flight row carries `tokens`, that advancing in-flight usage moves the run total with
  no second terminal, and that accrue→terminal is continuous (no double-count); a test
  asserts the pool-thread callback only enqueues; the `NoopStatusWriter` path and batch
  summaries are byte-identical.
- **R4/R5 (SSE):** `GET /api/v1/stream` yields an initial `data:` view event and a
  further event after the snapshot changes; a disconnecting client leaves the server up;
  `GET /` and `GET /api/v1/state` are byte-unchanged; with the stream forced to error the
  page still updates by poll.
- **R6 (rate-limit):** a used-percent/reset payload renders the summary + bar;
  `{"remaining": 9}` and `null` render without error (no raw JSON dump, no crash).
- **R7/R8 (Phase B):** two completed runs produce two history records with correct
  rollups; a torn/absent store reads `[]`; `GET /api/v1/history` + the panel list both
  runs; no store → "no history", rest of page unaffected.
- **R9:** diff is additive (new fields/routes/module only); `GET /api/v1/state` is a
  superset of today; `python3 plugin/scripts/check.py` GREEN.
- **(live, behavioral)** a real watched/mock run shows the headline token total climbing
  mid-turn in the browser, the rate-limit tag legible, and (Phase B) a prior run in the
  history panel.

## Decision log

- **D-1 — build SSE now (v1), not deferred.** The read-dashboard gated SSE as a human
  "upgrade if 1s feels laggy"; the human elected to build it. Implemented as server-side
  change-detection over the same `build_view`, with a **poll fallback** so the surface
  never regresses if the stream fails. (**human, 2026-06-18.**)
- **D-2 — Layer-2 reuses `on_event` + `extract_usage`; `app_server.py` unchanged.** The
  per-notification seam and the total extractor already exist; reusing them keeps the
  producer untouched (smallest blast radius, single extraction site) vs. adding a new
  `on_usage` callback. (autonomous.)
- **D-3 — `codex_totals` becomes a LIVE sum at `snapshot()`, mirroring
  `seconds_running`.** Ended tokens accumulate at `terminal()` (unchanged); in-flight
  live tokens are summed at snapshot; `terminal()`'s pop moves a ticket ended↔live
  atomically → no double-count. Chosen over a background ticker or per-event aggregate
  mutation because it reuses a pattern reviewers already trust and keeps the writer
  lock-free. (autonomous.)
- **D-4 — accrual marshals via `queue.Queue` drained on the main thread, coalesced.**
  Mandated by R13/R16 (no cross-thread writer mutation); coalescing latest-per-tid bounds
  status.json rewrites to ~one per tick. (autonomous; R13/R16.)
- **D-5 — multi-run aggregate view deferred; cross-run history is Phase B.** Multi-run has
  no producer scenario yet (defer); cross-run history has real trend value and is built as
  a separate, lower-risk phase after the v1 core. (**human, 2026-06-18.**)
- **D-6 — history is append-only JSONL in a new `director/history.py`, written by the
  orchestrator at run completion.** A metrics log, not an atomic snapshot, so append (not
  temp+replace) is right; a separate module keeps `status.py`'s single-snapshot
  responsibility intact and honors the stdlib-only / explicit-`base=` `director/`
  invariants. Best-effort (never gates a run). (autonomous.)

## Open questions

- **Daemon run identity for history.** A `run_forever` daemon's whole lifetime as one
  history record is coarse; a finer cut (per drain-to-idle cycle, or a rolling daily
  record) may read better once the daemon runs for real. Resolve from real use.
- **History rotation.** `runs.jsonl` grows unbounded over a multi-month horizon; whether
  to cap/rotate (and at what size) is deferred until the file is large enough to matter.
- **Exact codex `rate_limits` shape.** Pinned in the execplan against a live codex run;
  the renderer is written tolerant so an unanticipated shape degrades, not crashes.
