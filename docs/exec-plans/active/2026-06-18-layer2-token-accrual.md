---
status: active
last_verified: 2026-06-18
owner: harness
base_commit: 17b4b49
review_level: standard
---
# Layer-2 in-flight token accrual — live mid-turn cost in the snapshot

## Goal
The run snapshot reflects token usage **as it accrues mid-turn**, not only at
ticket terminal. Observable definition of done: while a worker is grinding a
long turn, `director.status` (and thus `GET /api/v1/state` / the dashboard)
shows the running ticket's tokens climbing and the run-level
`codex_totals.{input,output,total}` rising to include in-flight usage — and when
that ticket reaches terminal the run total stays continuous (no double-count, no
drop). Concretely: a mock/real run driven with usage events produces a snapshot
whose `in_flight[].tokens` is populated and whose `run.codex_totals.total`
equals `Σ(ended tickets) + Σ(in-flight latest usage)`; the existing dashboard
headline token tag moves during a turn instead of only at its end.

This is the v1 **producer** slice (spec R1–R3). The v1 **dashboard** slice (SSE +
rate-limit, R4–R6) is a separate linked plan; Phase B (cross-run history) a third.

## Context
- **Product-spec (owns the design — do NOT re-derive):**
  `docs/product-specs/2026-06-18-observability-polish.md` (R1–R3 + Design §A +
  D-2/D-3/D-4). This plan owns build order + milestones only.
- **Grounding rules:**
  - **RELIABILITY R13** — the `StatusWriter` is a main-thread lock-free
    single-writer; *any live mid-turn accrual must MARSHAL to the main thread*
    (e.g. drain at a turn/dispatch boundary), never reach into the writer from an
    `on_event` callback on a worker-pool thread.
  - **RELIABILITY R16** — cross-thread coordination uses thread-safe primitives
    (`threading.Event`/`queue.Queue`); the pool's `cancel_event` is today the only
    cross-thread object — the accrual `queue.Queue` becomes the second.
  - **RELIABILITY R12** — telemetry extractors are total (`extract_usage` returns
    None on a bad payload; `accrue` is tolerant — never raises, never gates).
  - `ARCHITECTURE.md` `director/` invariants (stdlib-only · explicit `base=` ·
    single-writer status model).
- **Producer contracts this build extends (verified at base_commit 17b4b49):**
  - `director/status.py` — `StatusWriter`: `claimed`/`dispatched`/`retrying`/
    `terminal`/`wave`/`stuck`/`finished`/`polled` transitions + `snapshot()`
    (already computes `seconds_running` as a LIVE aggregate: ended seconds +
    `Σ(in-flight elapsed)` — the pattern this plan mirrors for tokens);
    `_codex_totals` accumulates ended-ticket tokens at `terminal()`;
    `_in_flight[key]` entries carry `ticket_id/identifier/phase/attempt/wave/
    started_at`. `NoopStatusWriter` must stay byte-identical.
  - `director/worker/app_server.py` — `extract_usage(method, params) -> dict|None`
    (latest absolute totals; total fn) and the `on_event({"method","params"})`
    callback already fired per notification inside `run_turn` (line ~394).
    **This module is NOT modified** (D-2: reuse the existing seam).
  - `director/run.py` — `_prepare(...)` constructs `AppServerClient` (currently
    WITHOUT `on_event`); `drive(...)` / `run_ticket(...)` are the multi/single-turn
    drivers; `drive`'s loop already keeps `usage`/`rate_limits` from each turn's
    result. `dispatch(ticket, **kwargs)` (orchestrator) forwards `**kwargs` to
    `run.drive`, so a per-ticket `on_event` threads through unmodified.
  - `director/orchestrator.py` — `_RunState` (owns `futures`/`cancel_events`/
    `in_flight`; main-thread by contract); `submit()` adds per-attempt
    `cancel_event` (the model the accrual callback follows); `_dispatch_wave`'s
    `wait(FIRST_COMPLETED, timeout=reconcile_interval_s)` loop and `run_forever`'s
    `wait(timeout=poll_interval_s)` loop are the two main-thread tick points where
    the drain runs after `reap`.

## Approach (self-generated alternatives)
- **A — reuse `on_event` + `extract_usage`; marshal via `queue.Queue` drained on
  the main tick** (the spec's design, D-2/D-4). Per-ticket callback (bound in
  `submit`) extracts usage and `put`s `(tid, usage)`; the main loop drains +
  coalesces to `status.accrue`. `app_server.py` untouched.
- **B — add a dedicated `on_usage(usage)` callback to `AppServerClient`** fired
  when `extract_usage` returns non-None inside `run_turn`. Cleaner semantics, but
  touches the producer (`app_server.py`) for no functional gain — `on_event`
  already carries everything and `extract_usage` already exists. Rejected (larger
  blast radius, second extraction site).
- **C — push usage straight into the writer from the worker thread (with a lock).**
  Rejected by R13: a cross-thread write races the snapshot flush; adding a lock
  trades the simple single-writer invariant for a contention surface.
- **Chosen: A.** Smallest blast radius (producer unchanged), R13/R16-correct by
  construction (worker thread only `put`s; the writer is only ever touched on the
  main thread), and the live-sum at `snapshot()` mirrors the trusted
  `seconds_running` pattern.

## Assumptions & open questions (self-interrogation)
- **Assumption:** `extract_usage` reports cumulative ABSOLUTE thread totals (not
  deltas), so the LATEST value per ticket is its current total — verified by the
  telemetry slice's contract (`drive` keeps "latest absolute totals", §13.5). If
  wrong (deltas), the live sum would over/under-count; mitigated because the same
  value is what `terminal()` already folds, so producer and live agree.
- **Assumption:** the two main loops (`_dispatch_wave`, `run_forever`) tick at
  least every `reconcile_interval_s`/`poll_interval_s` even with no completion
  (verified: both `wait(timeout=…)`), so the drain runs on a bounded cadence
  while workers run — live accrual latency ≈ one tick, acceptable for a glance.
- **Assumption:** coalescing latest-usage-per-tid in the drain bounds status.json
  rewrites to ~one per tick regardless of event volume (a chatty turn emits many
  usage notifications) — without it `accrue`→`_flush` could fsync per event.
- **Open:** does a usage event arriving for an already-terminal ticket (drained
  after its in_flight pop) corrupt anything? → resolved: `accrue` is a no-op when
  `tid ∉ _in_flight` (order-independent). Recorded in Decision log.
- **Open (escalate? no):** none of this is a taste/product fork — the one product
  fork (scope/SSE) was settled in the spec.

## Milestones

- **M1 — StatusWriter live token sum + `accrue` (producer model, headless).**
  Extend `director/status.py`: (a) `claimed()` seeds `"tokens": None` on the
  in-flight entry; (b) new transition `accrue(self, ticket, usage)` — tolerant:
  resolve the ticket key, and if it is in `_in_flight` and `usage` carries integer
  `input/output/total`, set `entry["tokens"] = {input,output,total}` and `_flush()`;
  a key not in-flight is a no-op; a bad/partial `usage` is ignored (R12). (c)
  `snapshot()` makes `codex_totals` a LIVE aggregate mirroring `seconds_running`:
  `{k: _codex_totals[k] + Σ(e["tokens"][k] for e in _in_flight.values() if e["tokens"])}`
  for `k in (input,output,total)`, then `seconds_running` as today. `terminal()`
  is UNCHANGED (still folds the ticket's tokens into `_codex_totals` and pops the
  in-flight entry) — so a terminating ticket's contribution moves live→ended
  atomically (no double-count). `NoopStatusWriter` untouched.
  At the end: the producer model accrues live, fully unit-testable without threads.
  Run: `python3 -m unittest discover -s tests -p 'test_director_status.py'`.
  Expect (new tests): an in-flight ticket with `accrue(usage=400)` → snapshot
  `run.codex_totals.total == ended + 400` and `in_flight[0].tokens.total == 400`;
  advancing to 600 → total rises by 200 with no new ended ticket; `accrue` on a
  terminated/unknown tid is a no-op; `terminal()` after `accrue` leaves the run
  total continuous (== final, no double-count); a malformed `usage` leaves the
  aggregate unchanged; an existing no-`accrue` run is byte-identical to today.

- **M2 — Marshal seam: `on_event` thread-through + main-thread drain (threading).**
  (a) `director/run.py`: `drive(...)` and `run_ticket(...)` accept an optional
  `on_event=None` and forward it to `_prepare(on_event=…)` → `AppServerClient(
  on_event=…)`; default `None` → the client's existing no-op (every non-orchestrator
  caller byte-unchanged). (b) `director/orchestrator.py`: `_RunState` gains
  `self.accrual = queue.Queue()`; a helper `_enqueue_usage(tid, ev)` calls
  `app_server.extract_usage(ev.get("method"), ev.get("params", {}))` and, if
  non-None, `self.accrual.put((tid, usage))` — this is the ONLY code the worker
  pool thread runs against shared state, and it only `put`s (R13/R16). `submit()`
  passes `on_event=lambda ev: self._enqueue_usage(tid, ev)` (added per-submit, like
  `cancel_event`). A new `drain_accrual(self)` (main thread) drains the queue
  non-blocking, coalesces to the latest `usage` per `tid`, and calls
  `self.status.accrue(tid, usage)` per ticket. Both `_dispatch_wave` and
  `run_forever` call `state.drain_accrual()` right after `state.reap(done)`.
  At the end: usage observed on the pool thread reaches the writer only on the main
  thread, coalesced.
  Run: `python3 -m unittest discover -s tests -p 'test_director_orchestrator.py'`
  (+ `test_director_run.py` for the thread-through).
  Expect (new tests): the per-ticket callback only enqueues — a spy/fake asserts
  the worker-thread path never calls a `StatusWriter` method; a seeded queue
  drained on the main thread applies `accrue` (and coalesces N queued events for a
  tid into one `accrue`); the `NoopStatusWriter`/no-`on_event` path returns
  byte-identical wave summaries (drain is a pure side-channel); `drive(on_event=cb)`
  wires the callback into the client (asserted via the mock app-server emitting a
  usage notification → the callback fires).

- **M3 — Live render + behavioral E2E + docs + gate.** Minimal
  `director/dashboard.py` `PAGE` change: the in-flight row also shows its live
  `tokens` (reusing the existing `fmtTokens` helper) — so R2 is demonstrable
  end-to-end; the headline `codex_totals` already renders, so the live sum (R1)
  shows with no further change. Add a `docs/DIRECTOR.md` line noting tokens now
  accrue live mid-turn. Behavioral check (runnable surface → required): drive a
  `--mock` run (or a seeded StatusWriter + accrue sequence) and capture a snapshot
  showing the in-flight ticket's tokens populated and `codex_totals.total`
  including them mid-run; optionally serve the dashboard and confirm the headline
  moves before terminal (playwright). Capture into the plan.
  Run: `python3 plugin/scripts/check.py` (GREEN, worktree manual gate) + the drive.
  Expect: GREEN gate; the captured snapshot shows live in-flight tokens + a live
  run total; the dashboard headline reflects in-flight cost.

## Progress log
- [x] (2026-06-18) plan created; base_commit 17b4b49; review_level standard
  (arch + reliability — the marshal touches R13/R16 threading + the status model).
- [x] (2026-06-18) **M1 done** — `director/status.py`: `claimed()` seeds
  `in_flight[].tokens = None`; new `accrue(ticket_key, usage)` transition (tolerant —
  no-op on unknown/terminated tid, all-or-nothing `{input,output,total}` fold, main-thread
  only per R13); `snapshot()` `codex_totals` is now a LIVE sum (ended `_codex_totals` +
  `Σ(in-flight tokens)`), mirroring `seconds_running`; `terminal()` UNCHANGED (atomic
  live→ended move). 7 new TDD tests (default-none, live populate+advance, ended+in-flight
  sum, accrue→terminal no-double-count, unknown/terminated no-op, malformed ignored,
  no-accrue back-compat) — RED first (6 errors + KeyError), then GREEN. Full gate GREEN
  (477 tests). `app_server.py` untouched (D-2). `NoopStatusWriter` unchanged.
- [x] (2026-06-18) **M2 done** — marshal seam. `director/run.py`: `_prepare`/`drive`/
  `run_ticket` accept `on_event=None` and forward to `AppServerClient(on_event=…)` (default
  None → existing no-op; non-orchestrator callers byte-unchanged). `director/orchestrator.py`:
  `import queue` + `from director.worker import app_server`; `_RunState.accrual = queue.Queue()`;
  `_enqueue_usage(tid, ev)` (worker-thread: extract_usage → put, ONLY a put — R13);
  `drain_accrual()` (main-thread: drain + coalesce latest-per-tid → `status.accrue`); `submit()`
  binds `on_event=lambda: _enqueue_usage(tid, …)` per-submit (like `cancel_event`); both
  `_dispatch_wave` and `run_forever` call `drain_accrual()` after `reap`. 4 new tests
  (enqueue-only-never-touches-writer, drain coalesces latest-per-tid, live accrual e2e through
  drain w/ real StatusWriter, on_event reaches the client over the mock `usage` scenario).
  Existing `TelemetryPersistenceTest` (run_once over `usage`) still GREEN — proves the on_event
  plumbing end-to-end without breaking the run. Full gate GREEN (481 tests). All dispatch
  monkeypatches already take `**kw`, so the new `on_event` kwarg is absorbed (no test churn).

## Surprises & discoveries

## Decision log
- 2026-06-18: review_level = **standard** — the marshal seam is the one
  architecture/reliability-sensitive change (R13 single-writer, R16 cross-thread
  primitive); arch reviews the seam design, reliability reviews R13/R16/R12
  adherence. No security surface (no `hooks/`/`.harness.json`/listener change).
- 2026-06-18: v1 split into linked plans (PLANS.md scope check) — this
  **producer** plan (R1–R3) and a **dashboard** plan (SSE + rate-limit, R4–R6);
  parent = the observability-polish spec. Build producer first (foundation).
- 2026-06-18: `accrue` is a no-op for a non-in-flight tid — makes the main-thread
  drain order-independent vs. a ticket that terminated between enqueue and drain
  (no double-count, no resurrection of a popped entry).
- 2026-06-18: reuse `on_event`+`extract_usage`; `app_server.py` unchanged (spec
  D-2) — smallest blast radius, single extraction site.

## Feedback (from completion gate)

## Outcomes & retrospective
