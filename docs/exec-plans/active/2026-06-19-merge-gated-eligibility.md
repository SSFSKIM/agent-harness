---
status: active
last_verified: 2026-06-19
owner: harness
base_commit: 7263318989e1f35703fbdf3af24ce6ac1643b857
review_level: standard
---
# Merge-gated DAG eligibility — child waits for the parent PR to LAND

## Goal

A child ticket must not dispatch until its parent's PR has actually **landed on `main`**.
Definition of done (observable): in a mock orchestration where parent `P` (with a PR) blocks
child `C`, after `P`'s worker reports `done` the board shows `P` in a new **`merging`** state
and `C` is **not** dispatched; only once the serialized merger lands `P`'s PR (and the
orchestrator's next sweep moves `P` → `done`) does `C` become eligible and dispatch. With the
`merging` state **unconfigured**, behavior is byte-identical to today (`C` dispatches as soon
as `P` reports done). `python3 plugin/scripts/check.py` GREEN throughout.

## Context

- **Spec (owns the design):**
  `docs/product-specs/2026-06-19-merge-gated-eligibility.md` — build from it; do not
  re-derive. Direction A (human pick): make board-`done` *mean* merged-to-main by parking a
  PR-bearing done in an optional `merging` state and finalizing `merging`→`done` when the
  merge lands.
- **The gap:** `reconcile`'s done branch enqueues the merge then immediately sets the board
  `done` (`director/orchestrator.py:179-181`); `eligible_tickets` clears a blocker on
  `state_type ∈ done_types` (`director/orchestrator.py:257-263`). So a child can dispatch
  while the parent's PR is still unmerged in the serialized merger's queue, cloning a stale
  `main`.
- **Grounding:** RELIABILITY **R19** (act-before-consume), the ARCHITECTURE principle that
  the **orchestrator owns board writes** (the merger never writes the board — it surfaces via
  the queue: `director/merger.py` `_surface_escalation`/`_consume`), Symphony's
  Todo→In Progress→Human Review→**Merging**→Done lifecycle (`docs/symphony-original/SPEC.md`).
- **Reused machinery:** `board.fetch_issues_by_states(team, ids)` (parity R1 — already used by
  `_startup_recovery`), the deterministic merge-queue ids `merge|{tid}|a{n}` /
  `mergereview|{tid}|a{n}` with `merge_result` answers (`director/queue/__init__.py`), and
  `resolve_states`'s optional-state group (`director/orchestrator.py:62-69`).

## Approach (self-generated alternatives)

The chosen *representation* and *who-finalizes* were settled in the spec (Decision log D2/D3);
this is the execution shape.

- **A — `merging` board state + orchestrator-finalized sweep (chosen).** Park PR-done in a
  `merging` state; a new orchestrator sweep observes the land and writes `done`. Eligibility,
  orphan-recovery, active-run reconciliation stay *pure board reads* (unchanged). Tradeoff:
  finalize is eventual (next tick) and daemon-centric; a batch run that exits before a land
  leaves the ticket `merging` until re-run.
- **B — merger writes `done` on land.** Immediate, all-modes. Rejected (spec D3): violates the
  stated "orchestrator owns board writes" principle and puts board credentials in a second
  process.
- **C — merge-aware `eligible_tickets` (consult the queue).** No board state. Rejected
  (spec D2): two sources of truth in eligibility + a separate abandoned-set for the abandon
  case.
- **Chosen: A** — smallest blast radius given the repo's invariants; one optional state, one
  `reconcile` branch, one sweep reusing `fetch_issues_by_states`.

## Assumptions & open questions (self-interrogation)

- **Assumption:** `merge|{tid}|a{n}` is the only merge-request id family and its consumed
  answer carries `merge_result` (`merged`/`escalated`/`failed`). *Breaks if* the queue id
  scheme changes — guarded by a test asserting the helper against real `append_merge_request`
  + `write_answer`.
- **Assumption:** `DEFAULT_STATE_NAMES` aliases `config.DEFAULTS["states"]`, so adding
  `merging: None` there flows into `resolve_states`'s `names`. *Breaks if* the alias was
  copied — verify in M1 by reading the alias at the top of `orchestrator.py`.
- **Assumption:** a `merging` ticket has no live worker (the worker already reported done), so
  active-run reconciliation and orphan-recovery (which only touches `started`) never act on
  it. *Breaks if* some path re-dispatches `merging` — guarded by M4's E2E (child-not-dispatched
  proves the parent isn't re-run either).
- **Open:** does the dashboard need to show `merging` tickets distinctly? → Resolved
  autonomously: **no** (spec non-goal; the board is the truth, dashboard surfacing is a later
  best-effort add). Not a taste fork.
- **Open:** batch mode exiting before a land leaves a `merging` ticket. → Resolved: acceptable
  (daemon is the steady-state mode; a re-run's sweep finalizes); recorded as a spec Open
  question, not a blocker.

## Milestones

- **M1 — `merging` as an optional resolved state (spec R1).** Scope: `director/config.py` and
  `director/orchestrator.py` `resolve_states`. At the end, `config.DEFAULTS["states"]` carries
  `"merging": None`, `_STATE_KEYS` includes `"merging"`, `_build` validates it string-or-None
  (reusing `_str_or_none`, unknown-key behavior unchanged), and `resolve_states` resolves
  `merging` in the optional group (`for opt in ("failed", "blocked", "merging")`) —
  configured-but-missing name → `RuntimeError` at startup; `None` → `out["merging"] = None`.
  Run: `python3 -m pytest tests/test_director_config.py -q` (or unittest). Expect: a new test
  proves `director.states.merging: "Merging"` resolves to the board id, and an absent/None
  `merging` resolves to `None` with every other state unchanged.

- **M2 — PR-done parks in `merging`, no-PR done stays immediate (spec R2).** Scope:
  `director/orchestrator.py` `reconcile`, the `terminal`/`ostatus == "done"` branch
  (`:171-184`). At the end, the order is unchanged (`enqueued = _maybe_enqueue_merge(...)`
  **first** — R19), then: `if enqueued and states.get("merging"): set_state(states["merging"])`
  + `summarize("completed", "merging", merge_enqueued=True)`; `else: set_state(states["done"])`
  + `summarize("completed", "done", merge_enqueued=enqueued)` (covers no-PR tickets AND the
  `merging`-unconfigured fallback). The comment text distinguishes "merging" vs "done". Run:
  `python3 -m pytest tests/test_director_orchestrator.py -q`. Expect new tests: a done
  disposition with `pr_url` + `merging` configured → `update_issue_state(tid, merging_id)`
  called + a `merge|tid|a1` queued + summary `final_state=="merging"`; a done disposition with
  **no** PR → `update_issue_state(tid, done_id)`; with `merging` **unconfigured** → `done_id`
  even with a PR.

- **M3 — orchestrator merge-completion sweep (spec R3/R5).** Scope: a `merge_outcome(tid, *,
  base) -> "landed"|"pending"|"unresolved"` helper (placed in `director/merger.py` beside the
  other queue-reading helpers, imported by the orchestrator — keeps merge-queue semantics in
  one module; the merger stays board-free) reading `dq.read_pending` + `dq.read_answer(
  "merge|{tid}|a{n}")` across attempts: `landed` iff no `merge|tid|*` pending AND the latest
  answered attempt's `merge_result == "merged"`; `pending` iff a `merge|tid|*` is pending;
  else `unresolved` (escalated/abandoned). And `_reconcile_merges(board, *, team, states,
  queue_base, status=None)` (sibling of `_startup_recovery`): if `not states.get("merging")`
  return; else `for t in board.fetch_issues_by_states(team, [states["merging"]])`: on
  `merge_outcome(t["id"]) == "landed"` → `set_state(done)` + `comment("🔀 PR landed — merged
  to main")` (+ `status` recent update if a writer is present, best-effort). Whole body
  fail-soft (one try/except logging `{"daemon": "merge_reconcile_skipped", "error": …}` to
  stderr, mirroring `_startup_recovery`), never crashing the loop. Wire it: once per tick in
  `run_forever` (beside `reconcile_in_flight`, `:870-875`) and once per pass in
  `run_until_drained` (before the re-poll). Run: `python3 -m pytest
  tests/test_director_orchestrator.py -q`. Expect new tests: landed → `done` written;
  pending → no write (stays `merging`); unresolved/abandoned → no write; running the sweep
  twice writes `done` at most once meaningfully (idempotent — already-done isn't re-fetched as
  `merging`); a `fetch_issues_by_states`/queue error logs `merge_reconcile_skipped` and does
  not raise.

- **M4 — docs + behavioral E2E (spec R7 / acceptance 6).** Scope: `docs/DIRECTOR.md` §4 and §7
  — record that a PR-bearing `terminal(done)` parks the board in `merging` (work done,
  integration pending) and the orchestrator finalizes `merging`→`done` when the merger lands,
  so "the orchestrator executes the board transition" spans the terminal disposition **and**
  the merge sweep (still orchestrator-owned; merger stays board-free); the Director reads a
  `merging` ticket as "done work, awaiting land". Behavioral: a mock-orchestration test (a
  `MockBoard` with parent `P`+PR blocking child `C`) drives `P` to done → asserts `P` is
  `merging` and `C` was **not** dispatched; then simulate the land (write a
  `merge_result=merged` answer for `P`) → run the sweep → assert `P` is `done` and the next
  eligibility pass admits `C`. Run: the full gate `python3 plugin/scripts/check.py`. Expect:
  GREEN, and the E2E test demonstrates child-blocked-until-parent-landed end to end.

## Progress log
- [x] (2026-06-19) plan created; base_commit 7263318.
- [x] (2026-06-19) M1 — `merging` added to `config.DEFAULTS["states"]` (None) + `_STATE_KEYS`;
  `resolve_states` resolves it in the optional group (+docstring). Tests: config
  `test_merging_state_optional`; orchestrator `test_merging_state_resolved_when_present`/
  `_none_when_unconfigured`/`_configured_merging_state_missing_raises`; updated the
  exact-equality `test_resolves_defaults_to_ids` to include `merging: None`. Gate GREEN (532).
- [x] (2026-06-19) M2 — `reconcile` done branch: enqueue first (R19), then PR-done +
  `merging` configured → `set_state(merging)` + `summarize(final_state="merging")`; else →
  `done` (no-PR ticket AND merging-unconfigured fallback). Tests
  `test_done_with_pr_parks_in_merging_when_configured` + `test_no_pr_done_goes_to_done_even_
  when_merging_configured`; the existing unconfigured tests are the R7 byte-identical proof.
  Gate GREEN (534).
- [x] (2026-06-19) M3 — `merger.merge_outcome(tid)` (landed/pending/unresolved, reads
  `read_pending` + `read_answer("merge|tid|aN")` across attempts, highest-attempt
  authoritative) + `orchestrator._reconcile_merges` (fetch `merging` tickets → finalize
  landed ones to `done`, fail-soft per ticket AND per sweep), wired before the poll in both
  `run_until_drained` (top of loop) and `run_forever` (inside `if free > 0`). Tests:
  `MergeOutcomeTest` (6) + `MergeReconcileTest` (7: landed/pending/abandoned/idempotent/
  unconfigured-noop/fetch-fail-soft/per-ticket-fail-soft). Gate GREEN (547).
- [x] (2026-06-19) M4 — `docs/DIRECTOR.md` §4 (terminal: PR-done parks in `merging`, sweep
  finalizes →Done) + §7 (happy-path merging→Done note) updated. Behavioral E2E
  `MergeGatedEligibilityE2ETest::test_child_blocked_until_parent_pr_lands` drives the real
  `run_until_drained` loop: run 1 → P opens a PR → parks `merging` → C does NOT dispatch
  (stopped_reason "stuck"); simulate the merger land (merged answer) → run 2 → sweep finalizes
  P→Done → C dispatches. Gate GREEN (548). Entering completion gate (self-review + reviews).

## Surprises & discoveries
- 2026-06-19: `DaemonLoopTest::test_bounded_claim_and_top_up_as_slot_frees` is **flaky** under
  the full concurrent run (timing-based bounded-claim test) — failed once in a full-gate run,
  passed 3/3 in isolation and on gate re-run. Unrelated to this work (it uses default states,
  `merging` unconfigured → unchanged path). Noted for the tech-debt tracker if it recurs.

## Decision log
- 2026-06-19: `merge_outcome` helper lives in `director/merger.py` (not the orchestrator) —
  merge-queue id/answer semantics belong with the merger's other queue readers
  (`pending_merges`), and the orchestrator importing it keeps the merger board-free while
  reusing one source of truth for "did this PR land".
- 2026-06-19: the sweep writes `done` via the orchestrator's existing board handle (not the
  merger) — preserves the stated "orchestrator owns board writes" principle (spec D3).
- 2026-06-19: DROPPED the speculative `status=None` param on `_reconcile_merges` the plan
  sketched (the "+ status recent update" idea). There is no clean `StatusWriter` API to mutate
  an existing `recent[]` row's `final_state`, and dashboard/merging surfacing is an explicit
  spec non-goal — so the param would be dead weight (the same speculative-param trap a prior
  code-quality review flagged on `run_hook`'s `env`). The board is the truth a `merging` ticket
  reports; the sweep's job is the board write only.

## Feedback (from completion gate)

## Outcomes & retrospective
