---
status: completed
last_verified: 2026-06-17
owner: harness
type: exec-plan
tags: [daemon, director, reliability]
description: Gives the daemon exponential backoff so a failed worker is re-dispatched after a growing delay, an idle daemon grows its poll interval on a quiet board, and a failed claim is re-admitted after a backoff, while batch paths keep immediate retry.
base_commit: c78dce4
review_level: standard
---
# Daemon exponential backoff (daemon stage 3 — final)

## Goal

`python -m director.orchestrator --team T --daemon` backs off **exponentially**
instead of reacting at a fixed cadence (Symphony §8.4, parity gap #3): (A) a failed
worker is re-dispatched after `min(base·2^(retry-1), cap)` instead of immediately;
(B) an idle daemon grows its poll interval `poll_interval·2^idle_streak` (capped) on
a quiet board and resets when work appears; (D) a claim that failed is re-admitted
after a backoff instead of being excluded for the daemon's lifetime. All three share
one `_backoff_s` helper. The **batch paths keep immediate retry, unchanged.**

**Observable definition of done.** A new `tests/test_director_orchestrator.py` suite
(`DaemonBackoffTest`) demonstrates against the stage-2 daemon harness (background
thread + injected `shutdown_event`/`force_event` + `install_signals=False` +
`_wait_for`, with small backoff values): (R2) a failing daemon worker's re-dispatch
is *delayed* by ~`backoff_base_s` (not immediate) while the tick keeps running; (R3)
with `concurrency=1`, a pending-retry ticket blocks a second ready ticket's claim
until it resolves (slot accounting); (R4) the idle wait grows across consecutive idle
ticks and resets when work appears; (R5) a sustained poll failure backs off via the
idle path and recovers; (R6) a transiently claim-failing ticket is re-admitted after
backoff and eventually claimed, and the claim bookkeeping is cleared on success; (R9)
graceful drain abandons pending retries (no new submit) and still exits. Config tests
prove `backoff_base_s`/`backoff_cap_s` precedence (R8) and `_backoff_s` values (R1).
**All pre-existing `RunOnce*`/`RunUntilDrained*`/`ActiveRunReconcile`/`DaemonLoop`
tests stay green (R7 — batch + the stage-2 daemon contract unchanged).** Gate GREEN.

## Context

- **Spec (owns the design):** `docs/product-specs/2026-06-17-daemon-exponential-backoff.md`
  — R1–R9, D-74..D-81. Build from it; do not re-derive.
- **Predecessors (this layers on their seams):**
  `docs/product-specs/2026-06-17-continuous-daemon-loop.md` (stage 2 — `run_forever`,
  `_RunState`, the `_idle_wait_s` seam D-70, the `claim_failed` liveness gap D-73, the
  poll-failure throttle) +
  `docs/product-specs/2026-06-16-active-run-reconciliation.md` (stage 1 — covers
  Symphony's per-completion re-check, so it is a non-goal here).
- **Gap analysis:** `docs/design-docs/symphony-parity-gap.md` gap #3 (now cross-linked
  to this slice; the daemon track closes when this ships).
- **Code today (the seams this fills):** `director/orchestrator.py` —
  - `_idle_wait_s(poll_interval_s) -> poll_interval_s` (~:548, the D-70 backoff seam —
    a pure fn returning the constant; **its signature changes** this slice, one caller).
  - `_RunState.reap(done)` (~:382) — the retry branch does `self.submit(ticket)`
    **immediately** after `attempts[tid]+=1` + `status.retrying`. This is the shared
    batch+daemon machinery; the hook must not change the batch (no-arg) behavior.
  - `_RunState.claim_failed: set` (~:320) + `_claim_failed` (~:343) — the lifetime
    exclusion set (D-73 gap).
  - `run_forever` (~:585) — the tick: top-up (`free = concurrency - len(state.futures)`,
    `claimable[:free]`, the `poll_failing` once-on-transition log), two-path WAIT
    (`shutdown_event.wait(_idle_wait_s(poll_interval_s))` idle / `wait(futures,…)` busy),
    `state.reap(done)`, the monotonic `reconcile_interval_s` cadence, `not draining`
    guards, the force/`born_cancelled` block.
  - `resolve_settings` (~:559) + `main()` (~:812) — the `_pick(cli, cfg)` precedence and
    the `--poll-interval`/`--reconcile-interval` flags to mirror.
- **Config pattern:** `director/config.py` `DEFAULTS` + `DirectorConfig` +
  `_pos_num` + `_build` — `poll_interval_s`/`reconcile_interval_s` are the exact
  template for `backoff_base_s`/`backoff_cap_s`.
- **Test harness:** `tests/test_director_orchestrator.py` `DaemonLoopTest._run_bg`
  (background thread + injected events + `poll_interval_s=0.02`), `_wait_for`, `_DONE`,
  `_issue`, `orch.MockBoard`. Extend these.
- **Gate:** `python3 plugin/scripts/check.py` → `check: GREEN`. Commit discipline
  (CLAUDE.md): stage specific paths only (never `git add -A`), gate GREEN, then
  `git commit --no-verify`; never push/PR.

## Approach (self-generated alternatives)

The central choice is **how to add retry backoff (A) to the daemon without changing
the batch retry path** (`_RunState.reap` is shared; spec R7/D-75).

- **A — `reap(done, on_retry=None)` callback hook.** The retry branch becomes
  `(on_retry or self.submit)(ticket)`. Batch calls `reap(done)` → `on_retry=None` →
  immediate `self.submit` (byte-identical to today). The daemon passes
  `on_retry=schedule_retry`, which records `pending_retry[tid]=(ticket, now+delay)` and
  does **not** submit; a per-tick DUE-RETRY step submits when due. *Tradeoff:* one new
  optional param on the shared method — but the default path is provably unchanged
  (regression net), and it keeps the daemon-only scheduling out of `_RunState`.
- **B — a daemon-only `reap` reimplementation.** No touch to `_RunState.reap`, but
  duplicates the reconcile/retry/telemetry logic the stage-2 `_RunState` exists to
  unify. **Rejected** (violates D-63, the no-duplication invariant).
- **C — a `_RunState.scheduled_retry` flag + a `pending_retry` field on `_RunState`.**
  Moves the daemon-only scheduling state into the shared holder. **Rejected** — the
  batch wave never schedules; a daemon-only concern shouldn't bloat the shared object.
  The callback (A) keeps the scheduling state in `run_forever` where it belongs.

**Chosen: A.** The callback hook is the minimal, regression-safe seam; pending-retry
state (`pending_retry`, `claim_retry_at`, `claim_fails`, `idle_streak`) all live as
`run_forever` locals (daemon-only, main-thread — R13 holds, like all stage-2 daemon
state). Idle backoff (B) and claim re-admission (D) need no `_RunState` change at all.

The `now = time.monotonic()` clock is computed **once at the top of each tick** and
threaded to due-retry, claim-readmit, and the existing reconcile cadence — one clock
read per tick, consistent ordering.

## Assumptions & open questions (self-interrogation)

- **Assumption: deterministic backoff timing is unnecessary; small values + `_wait_for`
  suffice.** The stage-2 daemon tests already prove timing behaviors with real
  `time.monotonic()` + small intervals + `_wait_for` polling. Retry-backoff tests use
  `backoff_base_s≈0.2` and assert "no 2nd dispatch within ~0.05s, but within ~0.6s".
  *Breaks if* CI is so slow that 0.05s elapses before the loop even ticks — mitigated by
  generous upper bounds and `_wait_for(timeout=3.0)`. No fake-clock injection (would add
  a `now=` param threaded everywhere for a test-only need; not worth it — consistent
  with stage 1/2 which never injected a clock).
- **Assumption: `state.attempts[tid]` is the right exponent input at schedule time.**
  `reap` bumps `attempts[tid]` *before* calling `on_retry`, so at schedule time
  `attempts[tid]` is the new attempt number (2 for the first retry). `_backoff_s(attempts-1)`
  → `_backoff_s(1)` → `base`. *Breaks if* reap's order changes — pinned by R7 (reap
  default behavior unchanged) + a comment.
- **Assumption: pending-retry tickets need no active-run reconciliation.** They have no
  running worker (no `cancel_event`); a human moving one is caught when its retry submits
  and the next reconcile runs (short window; board-as-truth is the backstop). Resolved
  autonomously as acceptable (spec "에러/경계"); not worth reconciling a non-running ticket.
- **Open: does `_backoff_s(n)` count n from 1 or 0?** Resolved: n≥1, `n=1→base`
  (`min(base·2^(n-1), cap)`). Retry uses `n=attempts-1` (first retry → 1 → base); idle
  uses `n=idle_streak+1` (streak 0 → 1 → `poll_interval`); claim uses `n=claim_fails`
  (1st fail → 1 → base). All converge on "first occurrence = base", which is the natural
  reading.
- **Open: should claim re-admission distinguish transient vs permanent?** Resolved: no
  explicit distinction — the exponential `min(…, cap)` *is* the mechanism (a permanent
  failure retries at most every `cap`; surfaced via status). Simpler than a TTL/error-class
  taxonomy and adequate (spec D-79).
- **Open: idle base = `poll_interval_s` or `backoff_base_s`?** Resolved: idle base =
  `poll_interval_s` (the first idle wait stays the configured poll cadence; backoff grows
  from there). Retry/claim base = `backoff_base_s`. Shared `backoff_cap_s` (D-78).

## Milestones

- **M1 — `_backoff_s` helper + `backoff_base_s`/`backoff_cap_s` config knobs.**
  *Scope:* the pure foundation everything else calls. Add `_backoff_s(n, *, base, cap)
  = min(base·2**(max(0, n-1)), cap)` to `director/orchestrator.py`. Add `backoff_base_s`
  (10.0) and `backoff_cap_s` (300.0) to `director/config.py` `DEFAULTS`, the
  `DirectorConfig` fields, and `_build` (`_pos_num`), mirroring `poll_interval_s`. Wire
  both through `orchestrator.resolve_settings` (`_pick(args.backoff_base, cfg.backoff_base_s)`
  etc.) and add `--backoff-base`/`--backoff-cap` argparse flags (default None); add the
  two params to `run_forever`'s signature (default `config.DEFAULTS[...]`) — **unused
  until M2/M3** — and have `main()` thread them. *At the end:* the helper exists and is
  unit-testable; config carries validated backoff knobs; `run_forever` accepts them.
  *Run:* `python3 -m unittest discover -s tests -p 'test_director_config.py'` and a new
  `_backoff_s` unit test. *Acceptance:* `_backoff_s(1,base=2,cap=100)==2`,
  `_backoff_s(2,…)==4`, `_backoff_s(3,…)==8`, `_backoff_s(99,…)==100` (cap); config
  precedence test (CLI > config > default) for both knobs (mirror
  `test_poll_interval_resolves`); existing config tests GREEN.

- **M2 — IDLE backoff (B) + poll-failure subsumption (C).**
  *Scope:* change `_idle_wait_s` to `_idle_wait_s(poll_interval_s, idle_streak, cap)`
  returning `_backoff_s(idle_streak+1, base=poll_interval_s, cap=cap)` and update its one
  caller. In `run_forever`, add an `idle_streak` local: the idle WAIT path becomes
  `shutdown_event.wait(_idle_wait_s(poll_interval_s, idle_streak, backoff_cap_s))` then
  `idle_streak += 1`; reset `idle_streak = 0` in the busy branch (futures non-empty). No
  separate poll-failure curve — a failing poll already lands on the idle path (R5/C
  subsumed); keep the existing `poll_failing` once-on-transition log. *At the end:* an
  idle daemon backs off its poll cadence and resets on work; a down board backs off too.
  *Run:* `python3 -m unittest discover -s tests -p 'test_director_orchestrator.py'`.
  *Acceptance:* a `DaemonBackoffTest` case shows, on an empty board with a tiny
  `poll_interval_s` + small `backoff_cap_s`, that the gap between successive `polls`
  grows across idle ticks (timing/observed) and that introducing a ready ticket resets it
  (work gets claimed promptly, not after a long backoff); a sustained-`list_ready`-raise
  case backs off then recovers (claims the ticket once the board returns). Existing
  `DaemonLoopTest`/`RunUntilDrained` tests GREEN (idle behavior on the batch paths is
  untouched — `_idle_wait_s` is daemon-only).

- **M3 — RETRY backoff (A): scheduled re-dispatch.**
  *Scope:* the heaviest piece. Change `_RunState.reap(done, on_retry=None)` — the retry
  branch's `self.submit(ticket)` becomes `(on_retry or self.submit)(ticket)` (after the
  `attempts[tid] += 1` + `status.retrying`); `on_retry=None` is byte-identical to today
  (batch unchanged). In `run_forever`: a `pending_retry: {tid: (ticket, retry_at)}` local
  + a `schedule_retry(ticket)` hook that sets `pending_retry[tid] = (ticket,
  now + _backoff_s(state.attempts[tid]-1, base=backoff_base_s, cap=backoff_cap_s))` (the
  ticket stays in `state.in_flight`, not in `futures`). Compute `now = time.monotonic()`
  once at the top of the tick (reused by the reconcile cadence below). Add a DUE-RETRY
  step (guarded `not draining`, D-81) that pops and `state.submit`s pending whose
  `retry_at <= now`. Change slot accounting to `free = concurrency - len(state.futures)
  - len(pending_retry)` (R3/D-76). Pass `on_retry=schedule_retry` to `state.reap`.
  *At the end:* a failed daemon worker waits before retrying, without blocking the main
  thread, and never over-commits concurrency. *Run:* the orchestrator suite.
  *Acceptance:* `DaemonBackoffTest` — (R2) a worker whose attempt 1 returns `failed`
  (retry_budget≥1) with `backoff_base_s≈0.2`: its 2nd dispatch (attempt 2) does NOT occur
  within ~0.05s of the failure but DOES within ~0.6s, and the daemon keeps ticking
  meanwhile (the main thread is not blocked — assert `polls` advances during the wait);
  (R3) `concurrency=1`, board has A and B ready: A fails → pending-retry; B is NOT claimed
  while A's retry is pending (`free==0`), and only after A resolves does B (or A's retry)
  proceed; (R9) `shutdown_event` set while a ticket is pending-retry → no re-submit
  happens and the daemon exits (pending retry abandoned, left In Progress). **All existing
  retry tests (`RunOnceRetryTest`) and the rest of the orchestrator suite stay green
  (R7)** — proof the `on_retry=None` default preserved the batch path.

- **M4 — claim RE-ADMISSION (D) + DIRECTOR.md.**
  *Scope:* in `run_forever`, add `claim_retry_at: {tid: when}` and `claim_fails: {tid:
  count}` locals. Before top-up, `state.claim_failed.discard(tid)` for any tid with
  `now >= claim_retry_at.get(tid, now)` (re-admit due ones). In the top-up claim loop,
  when `state.claim_and_submit(...)` returns False: `claim_fails[tid] += 1`,
  `claim_retry_at[tid] = now + _backoff_s(claim_fails[tid], base=backoff_base_s,
  cap=backoff_cap_s)`; on a successful claim, `claim_fails.pop(tid, None)` +
  `claim_retry_at.pop(tid, None)` (bounded — only currently-failing tids; D-79).
  `state.claim_failed` stays the exclusion set, now managed by re-admission rather than
  being permanent. Add the backoff paragraph to `docs/DIRECTOR.md` §12 (retry/idle/claim
  back off exponentially; `--backoff-base`/`--backoff-cap`). *At the end:* a transient
  claim failure recovers; the exclusion bookkeeping cannot grow without bound. *Run:*
  `python3 plugin/scripts/check.py`. *Acceptance:* `DaemonBackoffTest` — (R6) a board
  whose `update_issue_state(→started)` returns False the first N times then succeeds:
  the ticket is excluded, then re-admitted after backoff, then claimed and run to Done;
  after success `claim_fails`/`claim_retry_at` no longer contain its tid (assert via a
  small hook or by observing it claims exactly once after recovery). Full gate GREEN.

## Progress log
- [x] (2026-06-17) plan created; base_commit c78dce4; spec committed c78dce4.
- [x] (2026-06-17) M1 — `_backoff_s(n,*,base,cap)=min(base·2^(n-1),cap)` helper +
  `backoff_base_s`(10.0)/`backoff_cap_s`(300.0) config knobs (DEFAULTS + DirectorConfig +
  `_pos_num` + resolve_settings + `--backoff-base`/`--backoff-cap` + run_forever params,
  unused until M2/M3; main() threads them). Tests: `BackoffHelperTest` (values + cap +
  n<1 clamp) + config precedence/defaults/validation. Gate GREEN (402).
- [x] (2026-06-17) M2 — IDLE backoff: `_idle_wait_s(poll_interval_s, idle_streak, cap)` =
  `_backoff_s(idle_streak+1, base=poll_interval_s, cap)`; run_forever `idle_streak` grows
  per idle tick, resets to 0 in the busy branch. Poll-failure (C) subsumed (a failed poll
  → idle path → backs off). Tests: `_idle_wait_s` curve unit test; `DaemonBackoffTest`
  idle-streak-grows (spy on `_idle_wait_s`), resets-after-work, sustained-poll-failure-
  backs-off-and-recovers. Gate GREEN (406).
- [x] (2026-06-17) M3 — RETRY backoff: `_RunState.reap(done, on_retry=None)` hook (default
  immediate submit = batch unchanged); run_forever `pending_retry` map + `schedule_retry`
  (retry_at = now + `_backoff_s(attempts-1, base, cap)`) + `not draining`-guarded DUE-RETRY
  step + slot accounting `free = concurrency − futures − pending_retry`; `now` at tick top
  for pre-wait checks, fresh clock post-WAIT for the reconcile cadence. **Removed stage-2's
  now-dead `born_cancelled`** (superseded — see Surprises); rewrote its test. Tests:
  retry-is-delayed, pending-retry-holds-a-slot, drain-abandons-pending-retry, force-drain-
  abandons-retry; `RunOnceRetryTest` + all batch tests stay green (R7). Gate GREEN (409).
- [x] (2026-06-17) M4 — CLAIM re-admission: run_forever `claim_retry_at`/`claim_fails`
  locals; before top-up, re-admit (discard from `state.claim_failed`) tids whose backoff
  elapsed; on a failed claim bump `claim_fails` + set `claim_retry_at = now + _backoff_s(...)`;
  on success pop both (bounded — only failing tids; D-79). DIRECTOR.md §12 backoff paragraph
  (retry/idle/claim curve, knobs, drain interaction, batch unaffected). Test:
  claim-failure-re-admitted-after-backoff (transient rejection recovers). Gate GREEN (410).

## Surprises & discoveries
- (M3) M3's scheduled-retry + `not draining`-guarded due-retry (D-81) **supersedes stage
  2's `born_cancelled`** force-defeat-by-retry fix: a failed daemon worker's retry is now
  *scheduled* and *abandoned on drain* — it can't be resubmitted during a force-stop at
  all, so `born_cancelled` (which pre-set the cancel Event on submit-during-force) became
  unreachable dead code (no `submit` runs during drain). Removed it; rewrote the stage-2
  `test_force_cancels_a_retry_spawned_during_drain` into `DaemonBackoffTest.
  test_force_drain_abandons_a_failed_workers_retry` (asserts the stronger guarantee:
  attempt 2 never spawns). A clean case of a later slice removing an earlier fix's *cause*.
- (M3) The reconcile cadence must read a FRESH clock AFTER the WAIT (idle backoff can sleep
  minutes) — the tick-top `now` (for pre-wait due-retry/claim-readmit) is stale by then.
  Two clock reads per tick is correct; the plan's "one now per tick" was an oversimplification.

## Decision log
- 2026-06-17: Chose Approach **A** (`reap(on_retry=None)` hook) — minimal, regression-safe
  seam; daemon scheduling state stays in `run_forever` locals, not the shared `_RunState`
  (D-75). Rejected duplication (B) and bloating `_RunState` (C).
- 2026-06-17: `now = time.monotonic()` computed once per tick, threaded to due-retry +
  claim-readmit + the existing reconcile cadence — one clock, consistent ordering.
- 2026-06-17: Milestones ordered foundation (M1) → simplest application (M2 idle) →
  heaviest (M3 retry) → smallest liveness fix (M4 claim) so each is independently
  verifiable and a regression is attributable to one milestone.
- 2026-06-17: No fake-clock injection — small backoff values + `_wait_for` (the stage-2
  daemon-test idiom); avoids threading a `now=` param through for a test-only need.

## Feedback (from completion gate)

Both personas **SATISFIED**, no P1. Both **independently** found the same P2 (highest-
confidence signal); fixed in-gate. Two more tracked as doc-debt.

- **P2 (review-arch AND review-reliability, same finding) — `claim_fails`/`claim_retry_at`
  slow leak. FIXED in-gate.** The maps were popped only on a *successful* claim; a ticket
  that transient-claim-failed once and then *left the board* (human moved/deleted it) was
  never popped — leaking for the daemon's lifetime, contradicting the spec's own D-79
  "bounded" claim. Fix: each successful poll, GC any claim-backoff tid not in
  `ready ∪ in_flight` (it has left the board → its backoff state is dead). Verified by
  inspection + both reviewers + the existing `test_claim_failure_is_re_admitted_after_backoff`
  still exercises the maps (the GC is memory hygiene with no behavioral signature, so no
  dedicated test).
- **P2 (review-reliability) — DIRECTOR.md §12 imprecise wording. FIXED in-gate.** "the
  board never shows more In Progress than are really running" was wrong (a pending-retry
  ticket IS In Progress but not running) → reworded to "never more In Progress than
  `concurrency` allows".
- **Proposed rules (both personas), TRACKED as doc-debt:** (1) every daemon-lifetime map
  keyed by ticket id must be evicted when the ticket leaves the relevant set (not only on
  the success path) — the general form of the leak above + the stage-2 `retain_results`/
  `attempts`-pop precedents; promote to a numbered RELIABILITY rule. (2) `_RunState` is
  *the* named batch/daemon sharing boundary and a force-stop's "no new worker during a
  drain" is now a structural guarantee (superseding `born_cancelled`) — promote the two
  load-bearing stage-2 daemon rules (parked at tech-debt-tracker) to ARCHITECTURE.md now
  that the daemon track is closed. (3) reconciliation reach = `futures` only, so a
  `pending_retry` ticket is human-cancel-blind until its retry submits (accepted short
  window, board-as-truth converges) — codify as accepted-staleness.

## Outcomes & retrospective

**Shipped:** exponential backoff (Symphony §8.4) for the daemon — closing parity gap #3 and
the **entire daemon track** (gaps #1 reconciliation / #2 continuous loop / #3 backoff). One
`_backoff_s(n,base,cap)` helper powers three behaviors: a failed worker retries after a
growing delay (scheduled, never blocking the main thread); a quiet/unreachable board is
polled less and less often (idle backoff, with poll-failure subsumed); a transient claim
rejection recovers via backed-off re-admission instead of lifetime exclusion. Batch paths
keep immediate retry, byte-unchanged (the `reap(on_retry=None)` default + the green batch
suite are the proof).

**The cleanest moment of the slice** was M3 *removing* stage-2's `born_cancelled` fix: the
scheduled-retry + drain-abandon design (D-81) closes the force-defeat-by-retry hole at its
*cause* (no worker spawns during a drain at all), making the earlier symptom-patch dead
code. A later slice subsuming an earlier fix — and the diff is net-simpler for it.

**Two design corrections surfaced mid-build** (recorded in Surprises): the reconcile cadence
needs a *fresh post-WAIT clock* (the plan's "one `now` per tick" was wrong — idle backoff can
sleep minutes); and the completion gate's two independent reviewers converged on the same
claim-map leak (the spec's D-79 "bounded" claim held only for the success exit, not the
left-the-board exit) — fixed in-gate with a GC against the live set.

**Proof:** full gate GREEN at **410 tests** (+11: config +2, `_backoff_s`/`_idle_wait_s` unit
+2, `DaemonBackoffTest` +7, minus the rewritten stage-2 force test). Both review personas
SATISFIED; 2 P2s fixed in-gate, 3 rule-promotions tracked.

**Track status:** daemon track CLOSED. Symphony parity now: gaps #1–#4 done; only **gap #5
(agent operating-protocol depth — the `WORKFLOW.md` body / richer per-stage templates)**
remains, on the separate worker-protocol track. The `_backoff_s` seam and the `_RunState`
sharing boundary are the durable artifacts a future loop-mode change inherits.
