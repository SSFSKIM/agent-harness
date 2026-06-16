---
status: active
last_verified: 2026-06-17
owner: harness
base_commit: 7091b0c
review_level: standard
---
# Continuous daemon loop (daemon stage 2)

## Goal

`python -m director.orchestrator --team T --daemon` runs an **always-on** loop:
it polls the board, claims ready work up to the concurrency cap, and — when the
board empties — **keeps polling forever** instead of exiting (the Symphony
identity, gap #2). As a concurrency slot frees, the next ready ticket is claimed
on the **next tick** without waiting for the rest of a batch to drain
(slot-free top-up). A human can stop the daemon: SIGTERM/SIGINT stops claiming and
drains in-flight workers; a second signal cancels them (reusing stage 1's
cooperative cancel). Throughout, the orchestrator keeps reconciling in-flight
tickets (stage 1, lifted unchanged) and writes a live heartbeat to
`status.json` (`mode`/`phase`/`last_poll_at`/`polls`).

**Observable definition of done.** A new `tests/test_director_orchestrator.py`
suite (`DaemonLoopTest`) demonstrates, against a scripted `FakeBoard` + a
cancellable mock worker: (R1) the loop does not return on an empty board until a
shutdown is signalled; (R2) with `concurrency=2` serving A,B,C, ticket C is
dispatched while B is still running (top-up, not wave-drain); (R3) at most
`concurrency` tickets are claimed/`In Progress` at once; (R5) an all-blocked board
writes `status.stuck` and keeps polling; (R6) an injected `shutdown_event` drains
in-flight then returns, and the force/cancel-all path returns `cancelled`; (R7)
idle does not busy-spin and a shutdown during idle returns promptly; (R8) a poll
that raises is survived and recovered from. The whole `python3
plugin/scripts/check.py` gate is GREEN, and **every pre-existing
`run_once`/`run_until_drained`/`_dispatch_wave`/`ActiveRunReconcileTest` test
still passes unchanged** (R10 — the batch paths are preserved).

## Context

- **Spec (owns the design):** `docs/product-specs/2026-06-17-continuous-daemon-loop.md`
  — R1–R11, D-63..D-72. This plan builds from it; it does not re-derive it.
- **Predecessor (lift its pieces unchanged):**
  `docs/product-specs/2026-06-16-active-run-reconciliation.md` +
  `docs/exec-plans/completed/2026-06-16-active-run-reconciliation.md` (stage 1).
- **Gap analysis:** `docs/design-docs/symphony-parity-gap.md` gap #2 (the identity
  gap) — its "structural root of #1/#2" note is exactly the barrier this slice
  removes.
- **Code today (the two barriers):** `director/orchestrator.py` —
  `_dispatch_wave` (the wave barrier, `while futures:` at ~:346, returns only when
  the whole claimed batch is terminal); `run_until_drained` (the pass barrier,
  `while True:` at ~:425, re-polls between waves but `break`s on
  drained/stuck/max/poll_failed). `run_once` is a single drain pass. The `futures`
  dict + `in_flight` set are already the running-map (stage 1 insight).
- **Stage-1 pieces to reuse verbatim:** `_reconcile_in_flight(board, futures,
  cancel_events, started_state_id, cancelled_states=None)` (free fn, no wave-local
  state); the `cancel_event` plumbing `dispatch → run.drive → app_server` and the
  `reconcile(... kind=="cancelled" ...)` branch (`director/orchestrator.py:189`,
  `director/run.py:182-230`); `board.fetch_issue_states_by_ids`.
- **Status surface:** `director/status.py` — `StatusWriter` is a main-thread,
  lock-free single writer (RELIABILITY R13); atomic temp+`os.replace` flush;
  methods `claimed/dispatched/retrying/terminal/wave/stuck/finished`. New heartbeat
  fields go under `run` (additive). Readers that must not break:
  `dashboard.build_view`, `status.context_for`.
- **Config:** `director/config.py` — `DEFAULTS` is the single source; the
  `reconcile_interval_s` knob (added in stage 1) is the exact template for
  `poll_interval_s`. `orchestrator.resolve_settings` resolves CLI > config >
  default via `_pick`.
- **Test machinery to extend:** `tests/test_director_orchestrator.py` —
  `orch.MockBoard`, `_CancelBoard` (fetch flips a ticket out of `started`),
  `_wait_then(disposition, fallback)` (a cancellable long mock worker that blocks
  on its `cancel_event`), `GrowingBoard` (poll returns new tickets over time),
  `mock.patch("director.orchestrator.dispatch", ...)`.
- **Gate command:** `python3 plugin/scripts/check.py` (must end `check: GREEN`).
  Commit discipline (repo CLAUDE.md): stage only the specific paths (never
  `git add -A`), gate GREEN manually, then `git commit --no-verify` with an
  explicit pathspec; never push/PR.

## Approach (self-generated alternatives)

The central build choice is **how the daemon shares the batch path's hard logic
(claim-before-act + reap/reconcile/retry/telemetry/`cancelled_states`) without
duplicating it**, given the spec's non-negotiable D-63.

- **A — a small `_RunState` holder + methods; refactor `_dispatch_wave` onto it.**
  `_RunState` owns the running-map dicts (`futures`/`in_flight`/`cancel_events`/
  `cancelled_states`/`attempts`/`results`) and the run-scoped knobs
  (board/states/retry_budget/queue_base/workspace_root/status/command/wave_kwargs),
  exposing `claim_and_submit(ticket, *, wave) -> bool` (claim-before-act board
  write → on success `attempts`/`in_flight`/`status.claimed`+pool submit with a
  fresh `cancel_event`; on raise/False → record `claim_failed` + `status.terminal`
  claim_failed row; returns whether dispatched) and `reap(done_futures)` (the exact
  `for fut in done:` body — pop, `reconcile(... external_state=cancelled_states.pop
  ...)`, retry→`claim_and_submit` else terminal). `_dispatch_wave` and `run_forever`
  both build a `_RunState`; they differ ONLY in claim cadence and stop condition.
  *Tradeoff:* touches `_dispatch_wave`'s internals (refactor risk) — but the
  existing batch tests are the regression net, and the reap reaches `submit`
  (a closure today), which a holder models cleanly.
- **B — leave `_dispatch_wave` untouched; `run_forever` re-implements claim/reap.**
  Zero batch refactor risk, but duplicates the trickiest logic → guaranteed
  divergence over time. **Rejected** (violates D-63).
- **C — free helper functions taking explicit dicts, both loops call them.**
  No duplication, smaller structural change to `_dispatch_wave` — but the reap's
  need for a `submit` callable + six dicts makes the signatures unwieldy;
  effectively `_RunState` without the ergonomics.

**Chosen: A.** It is the only option that puts the hard logic in exactly one place
*and* reads cleanly given the reap↔submit coupling. The pool's `ThreadPoolExecutor`
also becomes a `_RunState` field (the daemon needs one pool for its whole
lifetime, not per-wave). The regression net (R10) makes the refactor safe: if any
batch test changes behavior, the refactor is wrong. (If during M2 the
`_dispatch_wave` refactor proves to perturb a batch test's observable output,
fall back to C for the batch side only — `run_forever` still uses `_RunState`;
the invariant is no-duplication + batch-green, not the holder per se.)

The daemon's claim cadence is deliberately **different** from the batch wave
(D-64): `_dispatch_wave` floods (claims every eligible ticket up front; the pool
queues them); `run_forever` claims **≤ `concurrency - len(futures)`** per tick so
the board's `In Progress` count equals the running-worker count and each poll can
re-prioritize. This is why `run_forever` is its own loop, not "`_dispatch_wave`
minus the barrier."

## Assumptions & open questions (self-interrogation)

- **Assumption: board-as-truth makes daemon dedup cheap.** A successfully claimed
  ticket is moved to `started` *before* dispatch, so it leaves the `ready` poll
  immediately; done→`Done`, escalate/stuck/terminal_unknown→`started`,
  cancelled→human-owned — none reappear in a `ready` poll. So the only things the
  daemon must dedup are (1) tickets currently in `futures` and (2) tickets whose
  *claim failed* (still in `ready`, must not be hammered every tick). *Breaks if:*
  the board lets a `started` ticket also appear in the `ready` list — but
  `MockBoard`/Linear filter by `state_id`, so it can't. The `in_flight` set already
  guards intra-poll duplicates (the `DupBoard` test).
- **Assumption: `concurrent.futures.wait([], timeout=T)` returns immediately**
  (does NOT sleep T). Confirmed by the stdlib contract. Hence the two-path wait
  (D-67): block on `wait(futures, timeout, FIRST_COMPLETED)` only when `futures` is
  non-empty; when idle, sleep on `shutdown_event.wait(_idle_wait_s())`. *Breaks if*
  someone "simplifies" to a single `wait(futures, ...)` → idle busy-spin (CPU pegged
  + a test asserting bounded polls would catch it).
- **Assumption: signal handlers can be tested without real signals.** The handler
  is a 2-line fn that flips Events; tests call it directly and assert the event
  set, and drive the loop via an injected `shutdown_event` — `os.kill` is never
  used in tests (flaky, process-global). *Resolved autonomously:* `run_forever(...,
  shutdown_event=None, install_signals=True, max_ticks=None)`; tests pass
  `install_signals=False` + their own `shutdown_event` + a `max_ticks` safety
  bound; production passes neither (installs handlers, unbounded).
- **Assumption: the daemon may be watched OR autonomous** — the decider choice
  (`make_queue_decider` vs `autonomous_decide`) is orthogonal to loop mode and is
  already resolved in `main()` by `--autonomous`/`--mock`. No coupling added.
- **Open: which `wave` value does `status.claimed` get in the daemon?** Resolved
  autonomously: pass the daemon's monotonic poll counter (`polls`) as `wave` —
  reuses the field without inventing a daemon-only status entry-point.
- **Open: idle "stuck" recompute cost.** Resolved: only compute the stuck report
  when idle (`not futures`) AND the poll returned ready-but-all-blocked tickets —
  exactly `run_until_drained`'s stuck condition, extracted to a shared pure
  `_stuck_report(pending, done_set)` so both call one implementation.
- **Open: does `--daemon` need `max_passes`/`max_dispatched`?** No — those are batch
  safety bounds; the daemon is unbounded by design. The test-only `max_ticks`
  guards test hangs. (Not a product fork; recorded D-72 already fences mode.)

## Milestones

- **M1 — additive plumbing: `poll_interval_s` config knob + `status.py` heartbeat.**
  *Scope:* the zero-behavior-risk additions every later milestone builds on.
  Add `poll_interval_s` to `director/config.py` `DEFAULTS` (default `10.0`),
  `DirectorConfig` field, `_pos_num` validation in `_build`, mirroring
  `reconcile_interval_s` exactly; wire it through `orchestrator.resolve_settings`
  (`_pick(args.poll_interval, cfg.poll_interval_s)`) and add the `--poll-interval`
  argparse flag (default `None`). In `director/status.py`, add additive `run`
  fields `mode` (default `None`), `phase` (`None`), `last_poll_at` (`None`),
  `polls` (`0`) to the `_run` dict + `snapshot()`, and a light writer method
  `polled(self, *, phase, mode="daemon", stuck_count=0)` that sets
  `mode`/`phase`/`last_poll_at=self._now()`, increments `polls`, and `_flush()`s —
  no change to any existing field/method. *At the end:* config carries a validated
  `poll_interval_s`; a `StatusWriter` snapshot exposes the four heartbeat fields
  (None/0 until `polled()` is called); existing readers unaffected. *Run:*
  `python3 -m unittest discover -s tests -p 'test_director_config.py'` and
  `... -p 'test_director_status.py'`. *Acceptance:* a new config test proves
  `poll_interval_s` precedence CLI > config > default (mirror
  `test_reconcile_interval_resolves`); a new status test calls `polled(phase="idle")`
  and asserts the snapshot's `run.mode=="daemon"`, `run.phase=="idle"`,
  `run.polls==1`, `run.last_poll_at` non-None, and that a snapshot with no
  `polled()` call still has the four fields present with default values (back-compat).

- **M2 — shared `_RunState` primitive; refactor `_dispatch_wave` onto it (regression net).**
  *Scope:* introduce `_RunState` in `director/orchestrator.py` holding the
  running-map dicts + the pool + run-scoped knobs, with `claim_and_submit(ticket,
  *, wave) -> bool` and `reap(done) -> None` carrying the **exact** current
  `submit`/`claim_failed`/`for fut in done:` logic (including `cancel_events`
  fresh-Event-per-attempt, `cancelled_states.pop`, retry vs terminal, all `status.*`
  calls). Refactor `_dispatch_wave` to: build a `_RunState`, run its existing
  flood-claim loop via `state.claim_and_submit(...)`, then its `while state.futures:`
  loop calling `state.reap(done)` + the stage-1 `_reconcile_in_flight` cadence
  (unchanged). **No new behavior, no signature change to `_dispatch_wave`/
  `_reconcile_in_flight`/`reconcile`.** Also extract the pure `_stuck_report(pending,
  done_set)` helper and use it inside `run_until_drained`'s stuck branch (same
  output). *At the end:* one implementation of claim/reap; `_dispatch_wave` is a thin
  loop over `_RunState`. *Run:* `python3 -m unittest discover -s tests -p
  'test_director_orchestrator.py'`. *Acceptance:* **all pre-existing orchestrator
  tests pass byte-unchanged** (the `RunOnce*`, `RunUntilDrained*`, `Telemetry*`,
  `OrchestrationVisibility*`, `ActiveRunReconcileTest`, `ReconcileMergeEnqueue*`
  suites) — this is the proof the refactor preserved the batch contract (R10). No
  new test asserts new behavior here; M2 is a pure structure-preserving refactor.

- **M3 — `run_forever`: the continuous daemon tick loop.**
  *Scope:* add `run_forever(board, command, *, team, states, done_types=("completed",),
  poll_interval_s, reconcile_interval_s=..., concurrency=..., shutdown_event=None,
  install_signals=True, max_ticks=None, status=None, **wave_kwargs)` (signal
  installation itself lands in M4; M3 accepts the params and an injected
  `shutdown_event`). Build the tick (over one lifetime `_RunState`):
  (1) **top-up** — `free = concurrency - len(state.futures)`; if `free > 0`, poll
  inside `try/except` (on raise: record `status.last_error` via a `polled(phase=
  "idle")`-style write + skip top-up this tick, R8/D-69), filter `eligible_tickets`,
  drop ids in `state.in_flight`/`state.claim_failed`, `state.claim_and_submit` the
  first `free`; (2) **wait** — two-path (D-67): `wait(list(state.futures),
  timeout=poll_interval_s, return_when=FIRST_COMPLETED)` when futures present, else
  `shutdown_event.wait(_idle_wait_s(poll_interval_s))`; (3) **reap** —
  `state.reap(done)`; (4) **reconcile-in-flight** — `_reconcile_in_flight(...)` on
  the stage-1 monotonic `reconcile_interval_s` cadence (lifted unchanged);
  (5) **heartbeat/stuck** — `status.polled(phase=...)` where phase is `active` if
  futures else `idle`; when idle and the last poll returned ready-but-all-blocked
  tickets, `status.stuck(_stuck_report(...))` (D-66) — **never `break` on empty**
  (R1). Add the module-level `_idle_wait_s(poll_interval_s)` returning the constant
  today (the gap #3 backoff seam, D-70). Daemon-scoped dedup via `state.claim_failed`
  (a set, daemon-lifetime, surfaced; D-65). Loop continues `while not
  shutdown_event.is_set()` (+ `max_ticks` guard); on shutdown set, fall to M4's
  drain. For M3, when `shutdown_event` is set the loop stops claiming and returns
  once `state.futures` is empty (drain), calling `status.finished("shutdown")`.
  *At the end:* a fully working daemon loop, terminable by an injected
  `shutdown_event`. *Run:* `python3 -m unittest discover -s tests -p
  'test_director_orchestrator.py'`. *Acceptance:* a new `DaemonLoopTest` with a
  scripted `FakeBoard` (subclass of `MockBoard` whose `list_ready_issues` serves a
  queue of issue-batches then `[]`, and which can flip a flag to raise once) +
  `_wait_then`-style cancellable workers proves: **R1** empty board → loop runs
  `>1` poll and does not return until `shutdown_event.set()`; **R2** `concurrency=2`,
  board serves [A,B] then [C]: C is dispatched while B's worker still blocks
  (assert dispatch order/overlap via a shared live-set, like `RunOnceConcurrencyTest`);
  **R3** board serves 5 ready, `concurrency=2`: at most 2 `In Progress`/live
  dispatches at once (claim count bounded); **R5** board serves a ready ticket
  blocked by a failed/un-done blocker → `status.stuck` written, loop keeps polling
  (does not return); **R7** idle path uses `shutdown_event.wait` (assert no
  busy-spin: with a tiny `poll_interval_s` and `max_ticks`, poll count stays bounded;
  and `shutdown_event.set()` during idle returns within a small bound); **R8**
  `list_ready_issues` raises on the first poll then succeeds → loop survives and
  later dispatches the ticket. All assertions use injected `shutdown_event` +
  `install_signals=False` + `max_ticks`.

- **M4 — graceful shutdown signals + `--daemon`/`--poll-interval` CLI + DIRECTOR.md.**
  *Scope:* in `run_forever`, when `install_signals=True`, install SIGTERM+SIGINT
  handlers that ONLY flip Events (main-thread-safe, R13): 1st signal →
  `shutdown_event.set()` (stop claiming, drain); 2nd signal → set every
  `state.cancel_events[*]` (cooperative cancel-all, reusing stage 1) so long
  in-flight workers stop at the next turn boundary / mid-turn. Restore prior
  handlers on return (`finally`). The drain semantics from M3 already stop claiming
  once `shutdown_event` is set and return when `futures` empties; the 2nd-signal
  path makes that fast. In `director/orchestrator.py` `main()`: add `--daemon`
  (route to `run_forever`) and `--poll-interval` (type float, default None);
  default mode stays `run_until_drained`, `--once` preserved (D-72); resolve
  `poll_interval_s` from `resolve_settings`. Add a daemon section to `docs/DIRECTOR.md`
  (start with `--daemon`; stop via SIGTERM / double-SIGINT; how to read the
  idle/active/stuck heartbeat from `status.json`). *At the end:* the daemon is
  operable from the CLI and stoppable by signals. *Run:* `python3
  plugin/scripts/check.py`. *Acceptance:* (a) a test calls the installed handler fn
  directly (no real signal) and asserts 1st call sets `shutdown_event`, 2nd call
  sets all `cancel_events`; (b) **R6** an injected `shutdown_event` set while a
  `_wait_then` worker runs → loop stops claiming, reaps the in-flight worker to
  terminal, returns, `status.finished("shutdown")`; the force path (set all
  cancel_events) → the worker returns `cancelled` and the loop exits promptly;
  (c) a `MainCliTest` daemon case mocks `orch.run_forever` and asserts `main([...,
  "--daemon", "--poll-interval", "2"])` calls it with the resolved `poll_interval_s`
  (CLI 2 wins over config/default) — avoids running a real forever-loop in the CLI
  test; (d) full gate GREEN.

## Progress log
- [x] (2026-06-17) plan created; base_commit 7091b0c; spec committed 7091b0c.
- [x] (2026-06-17) M1 — `poll_interval_s` config knob (DEFAULTS 10.0 + DirectorConfig
  + `_pos_num` + resolve_settings + `--poll-interval`; `--daemon` flag declared, routed
  in M4); status.py additive `run.mode/phase/last_poll_at/polls` + `polled()` writer.
  Config 27 tests (+2), status 19 (+2); full gate GREEN.
- [x] (2026-06-17) M2 — extracted `_RunState` holder (running-map dicts + pool +
  `claim_and_submit`/`submit`/`reap`/`reconcile_in_flight`/`shutdown`); `_dispatch_wave`
  refactored to a thin loop over it (flood-claim + drain barrier preserved). Extracted
  pure `_stuck_report` + routed `run_until_drained` through it. **No new behavior, no
  signature change.** Regression net: all 51 orchestrator tests pass byte-unchanged;
  full gate GREEN (389).
- [x] (2026-06-17) M3 — `run_forever` daemon loop: bounded free-slot top-up, two-path
  wait (`wait(futures,…)` busy / `shutdown_event.wait(_idle_wait_s())` idle), reap,
  `reconcile_in_flight` on the stage-1 cadence, idle/heartbeat + stuck-as-status,
  never-exit, claim-failed dedup, poll fail-soft (stderr surface), `_idle_wait_s` backoff
  seam. Graceful shutdown built here too (coupled to the fn): `_daemon_signal_action`
  (1st drain / 2nd force) + `_install_daemon_signals`; `_RunState(retain_results=False)`
  + `attempts.pop` on terminal bound daemon memory. DaemonLoopTest: 7 tests for
  R1/R2/R3/R5/R6(drain+force)/R7/R8 via injected events. Gate GREEN (396).
  **Scope adjustment:** signal handling moved into M3 (it lives inside run_forever); M4
  narrows to the CLI surface (`--daemon` routing) + DIRECTOR.md + a CLI-routing test.
- [x] (2026-06-17) M4 — `main()` `--daemon` branch routes to `run_forever` with the
  resolved `poll_interval_s` (precedence over `--once`; signal handlers install by default
  on the main thread; batch bounds don't apply). DIRECTOR.md §12 "Running as a daemon"
  (start/stop via SIGTERM·double-SIGINT, idle/active/stuck heartbeat, reconciliation still
  applies). CLI-routing test (run_forever mocked → asserts `poll_interval_s=2.0`, CLI wins).
  Gate GREEN (397).

## Surprises & discoveries

## Decision log
- 2026-06-17: Chose Approach **A** (`_RunState` holder, refactor `_dispatch_wave`
  onto it) over duplication (B) or free-helpers (C) — the reap↔`submit` coupling +
  six shared dicts make a holder the only clean single-implementation; batch tests
  are the regression net (D-63).
- 2026-06-17: Daemon claim cadence is **bounded top-up** (≤ free slots), distinct
  from the batch flood-claim (D-64) — keeps board `In Progress` == running and
  allows per-poll re-prioritization; this is why `run_forever` is its own loop.
- 2026-06-17: Milestone split isolates the **risky structure-preserving refactor**
  (M2, proven by byte-green batch tests) from the **new behavior** (M3 loop, M4
  signals/CLI) so a regression is attributable to exactly one milestone.
- 2026-06-17: Test signals via injected `shutdown_event` + `install_signals=False`
  + `max_ticks`; handler tested as a plain fn — no `os.kill` (flaky/process-global).
- 2026-06-17: `_idle_wait_s(poll_interval_s)` is the single backoff seam (D-70);
  it returns the constant today and is the only thing gap #3 swaps.
- 2026-06-17 (D-73, new): daemon memory is bounded by `_RunState(retain_results=False)`
  (its durable output is the bounded `status.json` recent[], not an in-memory results
  dict) + pruning `attempts` on terminal. The `claim_failed` set still grows, but only
  on rare claim failures; retry-claim-with-backoff is deferred to gap #3 (the same seam).
  This preempts the "unbounded memory in a forever loop" reliability concern.
- 2026-06-17: signal handling implemented in M3 (it lives inside `run_forever`), via a
  pure `_daemon_signal_action` (testable without real signals) + `_install_daemon_signals`
  (main-thread only, restores prior handlers). M4 reduces to CLI routing + DIRECTOR.md.
- 2026-06-17: poll failure is surfaced as a one-line JSON to stderr (daemon operational
  log) and survived — a deliberate minimal surface; richer poll-failure visibility +
  backoff is gap #3.

## Feedback (from completion gate)

## Outcomes & retrospective
