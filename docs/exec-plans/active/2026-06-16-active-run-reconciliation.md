---
status: active
last_verified: 2026-06-16
owner: harness
base_commit: 6bb12b81d855f856caff0ac37e76e9add53eb0fd
review_level: standard
---
# Active-run reconciliation + worker cancel (daemon stage 1)

## Goal
While Director workers run, the orchestrator periodically re-reads the tracker state
of every in-flight ticket and **stops** a worker whose ticket a human moved out of the
`started` state — the operator-control lever we lack today. Definition of done
(observable): with a `FakeBoard` that flips ticket A's state to a terminal/other state
while A's worker is mid-drive, the worker is cancelled within ~`reconcile_interval_s`,
`run.drive` returns a `{"kind":"cancelled"}` disposition, the orchestrator records a
`cancelled` summary, **does NOT retry it and does NOT re-transition the board** (the
human owns the new state), and posts one comment; a long mock turn is interruptible
mid-turn (not only at turn boundaries); a `fetch_issue_states_by_ids` error keeps all
workers running and the wave still completes; reconciliation touches the StatusWriter
only from the main wave-loop thread; and a `director.reconcile_interval_s` config knob
(CLI `--reconcile-interval`) changes the cadence. `python3 plugin/scripts/check.py`
GREEN, and the existing mock/orchestrator tests still pass (no behavior change when no
ticket is externally moved).

## Context
- **Spec (owns the design — do not re-derive):**
  `docs/product-specs/2026-06-16-active-run-reconciliation.md` — R1–R7, D-59..D-62.
- **Why / where it sits:** `docs/design-docs/symphony-parity-gap.md` gap #1; the first
  of the daemon stages (stage 2 = continuous tick, stage 3 = backoff — both fenced
  OUT here, but the running-map this builds must let them layer on).
- **Symphony oracle:** `docs/symphony-original/SPEC.md` §8.5 (reconciliation),
  §16.3 (`reconcile_running_issues`), §14.4 (operator intervention), §7.2
  (`CanceledByReconciliation`).
- **Current code (read before touching):**
  - `director/orchestrator.py` `_dispatch_wave` — the wave-barrier: `while futures:
    wait(list(futures), return_when=FIRST_COMPLETED)`. `futures: {future→ticket}` +
    `in_flight: set` already ARE the running-map. `dispatch()` wraps `run.drive` and
    turns any exception into `{kind:"failed"}`. `reconcile()` executes a disposition
    onto the board (branches: terminal/escalate/stuck/failed/unknown).
  - `director/run.py` `drive` — multi-turn loop on one codex thread; between turns the
    injected `decide` runs (watched = blocks in `wait_for_answer` up to
    `turn_review_timeout`). `_prepare` builds the `AppServerClient`.
  - `director/worker/app_server.py` `_read_msg` — frames lines, `select.select([...],
    [], [], read_timeout_s)`; `ReadTimeout`/`AppServerError` already defined.
  - `director/status.py` `StatusWriter` — main-thread lock-free single writer (R13);
    `_in_flight` keyed by ticket_id has `started_at` only (no per-event ts → why stall
    is deferred, D-61). `terminal()` is the existing record-an-outcome path.
  - `director/config.py` `DEFAULTS`/`DirectorConfig`; `orchestrator.resolve_settings`
    (CLI > config > default).
  - `director/board/linear.py` — `_post` (shared GraphQL POST + error handling),
    `list_ready_issues`, `LinearBoard`; MockBoard lives in `orchestrator.py`.

## Approach (self-generated alternatives)
**(a) How the orchestrator reconciles while workers run.**
- A: **`wait(timeout=reconcile_interval_s)` on the existing barrier + a `monotonic()`
  cadence**, reconcile pass on the wave-loop (main) thread. Trade-off: the wave still
  blocks per-wave (stage-2 concern), but reconciliation is woven in with a one-line
  `wait` change and NO new thread.
- B: a dedicated reconciler **thread/timer** polling the board. Trade-off: it would
  write cancel state and (if it recorded outcomes) touch the StatusWriter from a second
  thread — breaking R13's single-writer invariant and forcing a marshal queue.
- **Chosen: A.** The `futures` dict already is the running-map, so a timeout on the
  barrier is the minimal change; keeping the pass on the main thread preserves R13 for
  free (D-60). Stage 2 later removes the per-wave barrier; the pass + cancel plumbing
  carry over unchanged.

**(b) How a running drive is cancelled.**
- A: **cooperative `cancel_event` (`threading.Event`)** checked in `app_server._read_msg`'s
  select loop (mid-turn) and in `drive` between turns; the read loop raises a standalone
  `TurnCancelled`; `drive`'s `with client` tears the subprocess down. Trade-off: mid-turn
  latency bounded by the select poll slice.
- B: orchestrator **hard-kills the app-server subprocess**. Trade-off: needs the
  orchestrator to hold each worker's client (breaks `drive`'s encapsulation), and an
  abrupt kill races the `with client` teardown.
- **Chosen: A** (D-59). `TurnCancelled` is NOT an `AppServerError` subclass so `drive`
  catches it distinctly → `{kind:"cancelled"}` (no retry), separate from `kind:"failed"`
  (retry-once). Lifecycle stays inside `drive`.

## Assumptions & open questions (self-interrogation)
- **Assumption:** a worker's ticket stays in `states["started"]` for the whole drive
  (the orchestrator only reconciles the disposition→board AFTER `drive` returns), so
  "current state ≠ started" reliably means *external* (human) movement. *Breaks if* a
  worker's own tool moves its ticket mid-drive — but workers propose outcomes via
  `report_outcome`, they don't self-transition (board writes are the orchestrator's,
  D-11). Holds.
- **Assumption:** `threading.Event` is the only cross-thread object; the main thread
  sets it, the worker pool thread reads it — `Event` is thread-safe, so no lock. *Breaks
  if* reconciliation ever writes the StatusWriter off-main — it must not (R6/D-60).
- **Open:** cancel responsiveness while a worker is parked in a watched turn-review
  (`decide`→`wait_for_answer`, up to `turn_review_timeout`) → resolved: accept the
  bound (the parked worker burns no compute; `drive` checks `cancel_event` right after
  `decide` returns). Documented in the spec; not widened here.
- **Open:** per-attempt `cancel_event` lifetime across retries → resolved: `submit()`
  creates a FRESH `Event` each attempt and stores it in `cancel_events[tid]` (a retried
  ticket gets a clear event); `_reconcile_in_flight` only sets events for tickets
  currently in `futures`.
- **Open:** default cadence → resolved: `reconcile_interval_s = 15.0` (more responsive
  than Symphony's 30s poll since stopping a runaway worker is time-sensitive; lower =
  faster stop but more Linear calls — operator-tunable, R7).

## Milestones

- **M1 — `board.fetch_issue_states_by_ids` (the read primitive).** Scope: the tracker
  read this slice needs, nothing wired yet. At the end: `director/board/linear.py` has
  a module fn `fetch_issue_states_by_ids(ids, *, api_key, endpoint, http_post)` →
  `{id: {"state_id", "state_name", "state_type"}}` via `issues(filter:{ id:{ in:$ids }
  }){ nodes{ id state{ id name type } } }` (reusing `_post`); a `LinearBoard` method;
  an **empty `ids` → `{}` with NO `http_post` call** (Symphony §17.3); and a MockBoard
  method (derive from `_issues[id].state_id` + `_states`). New tests in
  `tests/test_director_board.py` (or the board test file): normalization of a fake
  GraphQL payload, empty-ids-no-call (assert via an injected `http_post` spy that
  raises if called), MockBoard round-trip. Run: `python3 -m unittest discover -s tests
  -p 'test_director_board*.py' -v`. Acceptance: the fn returns the mapping for given
  ids and makes zero calls for `[]`.

- **M2 — cancellation plumbing (`TurnCancelled` + `cancel_event` → `drive`).** Scope:
  the mechanism to stop a running drive, testable without the orchestrator. At the end:
  `director/worker/app_server.py` defines `class TurnCancelled(Exception)` (standalone,
  NOT an `AppServerError` subclass); `AppServerClient(cancel_event=None)` and `_read_msg`
  polls `select` in short slices (≤ `read_timeout_s`, e.g. 0.5s) checking
  `cancel_event.is_set()` → raises `TurnCancelled` (mid-turn, R4). `director/run.py`
  `drive(..., cancel_event=None)` checks it at the top of each turn iteration and wraps
  the turn loop in `try/except TurnCancelled` → returns `{"kind":"cancelled","reason":
  "reconciliation","turns","turn_id","final_message","thread_id","telemetry":...}`; the
  `with client` block still runs `stop()`. `_prepare` threads `cancel_event` into the
  client. Tests in `tests/test_director_*` : (1) `drive` with a pre-set `cancel_event`
  returns `kind=="cancelled"` having run 0 completed turns; (2) an `AppServerClient`
  over a long-sleeping subprocess fixture (`python3 -c "import time; time.sleep(30)"`)
  with `cancel_event` set mid-`run_turn` raises `TurnCancelled` within ~one poll slice
  (proves mid-turn interrupt, R4); (3) `TurnCancelled` does not match `except
  AppServerError`. Run: `unittest discover`. Acceptance: a cancelled drive yields the
  distinct `cancelled` disposition; mid-turn interrupt observed.

- **M3 — orchestrator reconciliation wiring + config knob.** Scope: weave M1+M2 into the
  wave loop. At the end: `_dispatch_wave` keeps `cancel_events: {tid: Event}` (fresh per
  `submit`), calls `wait(list(futures), timeout=reconcile_interval_s,
  return_when=FIRST_COMPLETED)`, and on a `time.monotonic()` cadence (≥ interval, even
  under steady completions) runs `_reconcile_in_flight(board, futures, cancel_events,
  states)` — fetch the in-flight tids' states, `cancel_events[tid].set()` for any whose
  `state_id != states["started"]`, **fail-soft** (a fetch exception is caught, logged to
  the summary stream, workers kept — R5). `dispatch(ticket, ..., cancel_event=…)` passes
  it to `run.drive`. `reconcile()` gains a `kind=="cancelled"` branch: `comment("🛑 …
  moved out of In Progress externally — worker stopped")`, summary `{status:"cancelled",
  final_state: <observed>}`, NO `set_state`, returns `{"summary":…}` (NOT
  `{"retry":True}`). `config.DEFAULTS["reconcile_interval_s"]=15.0` +
  `DirectorConfig.reconcile_interval_s` + `resolve_settings` + orchestrator
  `--reconcile-interval`; threads through `run_once`/`run_until_drained` →
  `_dispatch_wave`. Tests: a `FakeBoard` whose `fetch_issue_states_by_ids` returns a
  non-`started` state for ticket A, with `dispatch` patched to a fake that
  `cancel_event.wait()`s then returns `cancelled` when set → assert A is cancelled,
  `attempts`==1 (no retry), the board saw NO post-claim `update_issue_state` for A,
  status row `cancelled`; a fetch that raises → both workers complete normally (R5); a
  StatusWriter subclass that records the calling thread proves reconciliation writes
  only from the main thread (R6); a config `reconcile_interval_s` override is picked up
  by `resolve_settings`. Run: `python3 plugin/scripts/check.py`. Acceptance: gate GREEN
  (existing 374 pass unchanged + new tests); the FakeBoard operator-cancel scenario
  passes end-to-end.

## Progress log
- [ ] (2026-06-16) Plan created; base_commit 6bb12b8, review_level standard.
- [x] (2026-06-16) M1 — `board.fetch_issue_states_by_ids` (linear module fn +
  `_ISSUE_STATES` query + LinearBoard method + MockBoard method; empty-ids → no call).
  3 new linear tests (normalize, empty-no-call, omit-unknown). Gate GREEN at 377.
- [x] (2026-06-16) M2 — cancellation plumbing. `app_server.TurnCancelled` (standalone),
  `AppServerClient(cancel_event=)` + `_wait_readable` (slice-polls `select` ≤0.5s,
  checks the event mid-turn → raises; still enforces read_timeout_s). `run.drive(
  cancel_event=)` threads it through `_prepare`, checks between turns, and wraps the
  WHOLE `with client` body in `try/except TurnCancelled` → `{kind:"cancelled"}`. 4 tests
  (drive between-turns cancel; app_server pre-set + mid-wait interrupt + not-AppServerError).
  Gate GREEN at 381.
- [x] (2026-06-16) M3 — orchestrator reconciliation wiring + config knob.
  `_dispatch_wave`: fresh `cancel_event` per `submit` (passed via `dispatch` **kwargs to
  `run.drive`); `wait(timeout=reconcile_interval_s)` + a `time.monotonic()` cadence calls
  `_reconcile_in_flight(board, futures.values(), cancel_events, states["started"])` on the
  MAIN thread (sets cancel for any ticket whose state ≠ started; fail-soft on fetch error).
  `reconcile()` `kind=="cancelled"` branch (comment + `released` summary, no set_state, no
  retry). `reconcile_interval_s` knob (config.DEFAULTS + DirectorConfig + resolve_settings
  + `--reconcile-interval`). 4 tests (operator-cancel no-retry/no-write, fail-soft fetch,
  main-thread-recorded, reconcile_interval resolve). Gate GREEN at 385.

## Surprises & discoveries
- 2026-06-16 (M2): a reconciliation cancel can land during the codex **handshake**
  (`initialize`/`thread_start`), not just mid-turn — both call `_read_msg`→`_wait_readable`.
  First cut wrapped only the turn loop, so a handshake-time `TurnCancelled` escaped →
  `dispatch` would mark it failed→retry. Fix: wrap the ENTIRE `with client` body in
  `try/except TurnCancelled`. (Caught by `test_drive_cancelled_between_turns` with a
  pre-set event, which lands in `initialize`.)

## Decision log
- 2026-06-16: **wait(timeout=) + main-thread reconcile, no reconciler thread** (D-60) —
  futures-dict is already the running-map; preserves StatusWriter single-writer (R13).
- 2026-06-16: **cooperative cancel_event + standalone TurnCancelled** (D-59) — distinct
  from failed (no retry); subprocess teardown stays in drive's `with client`.
- 2026-06-16: **fresh cancel_event per attempt**; `_reconcile_in_flight` only sets
  events for tickets currently in `futures`.
- 2026-06-16: **cancel rule = `state_id != states["started"]`**; cancelled → comment +
  released summary, no set_state, no retry (D-62).

## Feedback (from completion gate)

## Outcomes & retrospective
