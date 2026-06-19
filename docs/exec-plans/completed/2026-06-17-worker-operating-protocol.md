---
status: completed
last_verified: 2026-06-17
owner: harness
type: exec-plan
tags: [worker, autonomy, taxonomy]
description: Gives every worker's first-turn prompt on all dispatch paths a stage-agnostic WORKER PROTOCOL preamble, plus impl-template disciplines for reproduction-first work, acceptance-criteria mirroring, temp-edit revert, and a PR feedback sweep.
base_commit: a42b90d
review_level: standard
---
# Worker operating-protocol depth (graduated-autonomy slice 1)

## Goal

Every worker's first-turn prompt — on **all** dispatch paths (orchestrator,
`run.main`, direct `drive`) — carries a stage-agnostic **WORKER PROTOCOL**
preamble (single living source-of-truth + no-scope-creep→typed child), and the
`impl` template additionally instructs reproduction-first, acceptance-criteria
mirroring, temp-proof-edit revert, and a **PR feedback sweep** (pre-handoff +
on-arrival). Demonstrable: `python3 -m unittest discover -s tests -p
'test_director_taxonomy*'` shows new assertions that fail on `base_commit` and
pass at HEAD; the full gate (`python3 plugin/scripts/check.py`) is GREEN; and
`git diff a42b90d..HEAD` touches only `director/taxonomy.py`, `director/run.py`,
`tests/test_director_taxonomy.py`, and this plan — `decider.py`, board-write
ownership, and `merger.py` byte-unchanged.

## Context

- **Spec (owns the design):**
  [`docs/product-specs/2026-06-17-worker-operating-protocol.md`](docs/product-specs/2026-06-17-worker-operating-protocol.md) — R1–R9 + the
  line-by-line `WORKFLOW.md` keep/adapt/reject triage. This plan builds it; it
  does not re-derive it.
- **Decision:** `docs/memory/adr/0002-graduated-autonomy.md` (ADR 0002) — this is
  slice 1 (the *enabler*); slice 2 is the selective-escalation decider.
- **Source harvested:** `docs/symphony-original/WORKFLOW.md` (the disciplines;
  NOT the file's lifecycle/board-ownership steps, which the triage rejects).
- **The injection seam (verified this session):** `director/orchestrator.py:84`
  dispatches via `run.drive(composed, ...)`; `director/run.py:201` frames the
  first turn via `taxonomy.with_terminal_contract(ticket["prompt"])`. `run.main`
  (`run.py:201`) and direct `drive` callers share that exact line. So one seam
  there reaches every path.
- **Current shape of the seam** (`director/taxonomy.py`): `TERMINAL_CONTRACT`
  constant + `with_terminal_contract(prompt)` appends `"\n\n---\nTURN PROTOCOL\n"
  + TERMINAL_CONTRACT`. `compose_worker_prompt(ticket)` (orchestrator side) wraps
  the per-stage template around the ticket body; untyped tickets pass through raw.
- **Already covered (do NOT duplicate):** the `impl` self-QA + `push`-skill PR
  self-description come from
  `docs/product-specs/2026-06-16-worker-qa-and-serialized-pr-merge.md`; the
  multi-turn terminal contract from `2026-06-15-multi-turn-ticket-execution.md`.
- **Authority:** `issueCreate` and `commentCreate` are already in
  `director/worker/authority.py`'s `DEFAULT_MUTATION_ALLOWLIST` — so
  no-scope-creep→child-ticket needs no guardrail change.

## Approach (self-generated alternatives)

How to inject the stage-agnostic preamble at the single first-turn seam:

- **A — Extend `with_terminal_contract`** to append both WORKER PROTOCOL and TURN
  PROTOCOL blocks. Minimal wiring (run.py unchanged). Tradeoff: the function name
  understates what it now does (it frames the whole first turn), and the existing
  test reads as if it only adds the terminal contract.
- **B — Add `WORKER_PROTOCOL` + a new `frame_first_turn(prompt)` seam** that
  appends the WORKER PROTOCOL block then *delegates to the untouched*
  `with_terminal_contract` for the terminal block; rewire `run.py:201` to call
  `frame_first_turn`. Tradeoff: one extra function + one wiring-line change.
- **Chosen: B.** `with_terminal_contract` stays byte-stable (its pinned test —
  output starts-with prompt, contains `report_outcome` + `TURN PROTOCOL` — passes
  untouched, satisfying R8 strictly), the terminal-block format isn't duplicated
  (B reuses it), and the name `frame_first_turn` honestly describes the seam. The
  emitted order matches the spec diagram: `prompt → WORKER PROTOCOL → TURN
  PROTOCOL`.

## Assumptions & open questions (self-interrogation)

- **Assumption:** orchestrator, `run.main`, and direct `drive` all route through
  the `run.py:201` first-turn framing. *Verified* (`orchestrator.py:84` →
  `run.drive`; line 68 docstring "wraps run.drive"). If wrong, a path would miss
  the preamble — but it is confirmed, so R1 holds via the single seam.
- **Assumption:** the worker has in-sandbox shell + `gh`/network to run the PR
  feedback sweep (default posture is `workspace-write` + network). If a channel
  is unreachable, the worker routes `report_outcome(blocked/needs_human)` per the
  spec's edge-case handling — the sweep is a *procedure*, never a silent skip.
- **Open:** extend vs new seam → resolved as **B** (above; Decision log).
- **Open:** does WORKER_PROTOCOL name the specific per-stage doc? → resolved:
  **no** — phrase it generically ("your stage's output doc") so it stays
  stage-agnostic; the per-stage template already names the concrete doc/path.
- **Open:** enrich non-impl templates (research/design/spec/planning)? → resolved:
  **no** (YAGNI, spec Non-goals) — they get only the preamble; bodies untouched.

## Milestones

- **M1 — Shared preamble + single seam (R1/R2/R3, regression R8).** Add a
  `WORKER_PROTOCOL` constant to `director/taxonomy.py` holding exactly the two
  cross-stage disciplines — (1) *single living source-of-truth*: "your stage's
  output doc (research digest / design doc / product-spec / ExecPlan) is the one
  source of truth for plan and progress; maintain it in-place as you work — check
  items off, record decisions/surprises the moment they happen; do not scatter
  status across Linear comments or separate notes"; (2) *no scope-creep*: "if you
  find meaningful out-of-scope work, do not expand this ticket — file a separate
  typed child ticket (right stage label, `blocked_by`/`related` as appropriate)
  via the linear skill and note it." Add `frame_first_turn(prompt)` that appends
  `"\n\n---\nWORKER PROTOCOL\n" + WORKER_PROTOCOL` to the prompt then returns
  `with_terminal_contract(<that>)` — leaving `with_terminal_contract` itself
  byte-unchanged. Rewire `director/run.py:201` from `with_terminal_contract(...)`
  to `frame_first_turn(...)`. At the end the preamble exists, is emitted before
  the TURN PROTOCOL block, and is what `drive` injects on every path. Run
  `python3 -m unittest discover -s tests -p 'test_director_taxonomy*'`; expect new
  assertions green: `WORKER_PROTOCOL` names both disciplines (source-of-truth
  phrase + "child ticket"); `frame_first_turn("x")` starts with `"x"` and contains
  both `WORKER PROTOCOL` and `TURN PROTOCOL` + `report_outcome`; and the existing
  `test_with_terminal_contract_appends_to_prompt` still passes unchanged.

- **M2 — `impl` template enrichment (R4/R5/R6/R7).** Extend `_IMPL_TEMPLATE` in
  `director/taxonomy.py`, time-ordered and *after* the existing reproduce→plan
  framing but preserving the current SELF-QA + `push`-skill PR self-description
  block verbatim: (R4) reproduction-first — "before changing code, reproduce and
  capture the current behavior/issue signal (command/output or deterministic
  behavior) and record it in the ExecPlan `Notes`"; (R5) acceptance mirroring —
  "if the ticket carries `Validation`/`Test Plan`/`Testing` sections, mirror them
  into the ExecPlan as non-negotiable acceptance checkboxes and execute them
  before done"; (R6) temp-proof revert — "temporary local proof edits are allowed
  to validate assumptions but must be reverted before commit and documented in the
  ExecPlan"; (R7) PR feedback sweep — pre-handoff: "after opening the PR and before
  `report_outcome(done)`, sweep the PR's checks + all comment channels (top-level,
  inline review, bot, review summaries via `gh`), treat each actionable item as
  blocking until addressed by a code/test/docs change or an explicit justified
  pushback reply, re-run validation, and repeat until nothing is outstanding and
  checks are green"; on-arrival: "if the ticket already has a PR attached when you
  pick it up, run that PR feedback sweep first, before new work." At the end the
  `impl` worker prompt instructs all four disciplines while the self-QA/PR block is
  intact. Run the same discover command; expect new `impl` assertions green
  (substrings: reproduction/reproduce, the mirror-as-non-negotiable phrase, revert
  proof edits, "feedback sweep") and the existing
  `test_impl_prompt_includes_self_qa_and_pr_procedure` still passing.

- **M3 — Docstring touch + scope-fence verification (R9) + full regression.**
  Update the `director/taxonomy.py` module docstring with a one-line mention of the
  new `WORKER_PROTOCOL` preamble (so the file self-documents the seam). Then prove
  the scope fence: `git diff a42b90d..HEAD --stat` lists only `director/taxonomy.py`,
  `director/run.py`, `tests/test_director_taxonomy.py`, and this plan; and
  `git diff a42b90d..HEAD -- director/decider.py director/merger.py` is empty. Run
  the full gate `python3 plugin/scripts/check.py`; expect GREEN (all tests,
  including the untouched orchestrator/run/merger suites, pass — the preamble is
  additive and the batch/daemon paths are byte-equivalent in behavior). This
  milestone is the pre-completion-gate checkpoint.

## Progress log
- [x] (2026-06-17) plan created; base_commit a42b90d, review_level standard.
- [x] (2026-06-17) M1 done. Added `WORKER_PROTOCOL` (2 cross-stage disciplines) +
  `frame_first_turn` (delegates to untouched `with_terminal_contract`) in
  `director/taxonomy.py`; rewired the single seam at `director/run.py:201`. Tests:
  `WorkerProtocolTest` (3) added — failed before (AttributeError), green after.
  `unittest discover -p 'test_director_taxonomy*'` → 16 OK. `with_terminal_contract`
  byte-unchanged (R8).
- [x] (2026-06-17) M2 done. `_IMPL_TEMPLATE` gains reproduction-first (R4),
  acceptance mirroring as non-negotiable (R5), temp-proof revert (R6), and the PR
  feedback sweep — pre-handoff step (5) + on-arrival ("if a PR is already attached…
  run the sweep FIRST") (R7); existing SELF-QA + push-PR block kept verbatim. New
  test `test_impl_prompt_includes_the_four_operating_disciplines` failed before,
  green after; existing impl/self-QA tests still pass.
- [x] (2026-06-17) M3 done. `taxonomy.py` module docstring gains a one-line mention
  of `frame_first_turn` + `WORKER_PROTOCOL`. Scope fence verified: `git diff
  a42b90d..HEAD` (incl. working tree) touches only `taxonomy.py`, `run.py`,
  `tests/test_director_taxonomy.py`, and this plan; `decider.py`/`merger.py` diff is
  empty. Full gate `check.py` GREEN.

## Surprises & discoveries

## Decision log
- 2026-06-17: Inject via a new `frame_first_turn` seam that delegates to an
  untouched `with_terminal_contract` (Approach B) — keeps the pinned terminal-
  contract test byte-green, reuses the terminal-block format, honest naming.
- 2026-06-17: WORKER_PROTOCOL holds only the 2 cross-stage disciplines; the four
  impl-specific disciplines live in `_IMPL_TEMPLATE`; non-impl bodies untouched
  (spec YAGNI).
- 2026-06-17: source-of-truth maps onto our living repo doc, NOT a Linear-comment
  workpad; env-stamp dropped — both rejected in the spec triage (redundant with
  `status.py` snapshot + telemetry).

## Feedback (from completion gate)

Gate GREEN (414 tests). Self-review: clean — diff matches the plan, the on-arrival
"(below)" is an intentional forward-reference to sweep step (5). Both `standard`
personas **SATISFIED**, no P1, no P2:
- **review-arch** — verified layer law, all five `director/` invariants, the R9
  scope fence (`decider.py`/`merger.py` byte-empty diff), and the three taste
  decisions (delegating seam, protocol scoping, repo-doc source-of-truth) against
  ADR 0002. Two **proposed rule additions** (non-blocking, no written rule
  violated) → tracked as doc-debt (tech-debt-tracker, 2026-06-17): (1) write down
  `run.drive` as THE single first-turn framing seam (an ARCHITECTURE.md `director/`
  invariant); (2) a DESIGN.md taste rule for worker-prompt protocol text
  (terse / stage-agnostic-preamble-vs-stage-template). Not fixed in-gate — below
  P2, and feedback-once; promote on recurrence.
- **review-reliability** — confirmed the rewire preserves the first-turn framing
  contract (prompt-first, `report_outcome`/`TERMINAL_CONTRACT` present → no
  loop-to-stuck), `with_terminal_contract` is byte-unchanged (R8), and the PR
  feedback sweep loop is **bounded** by `drive`'s `max_turns=8` cap + the
  `report_outcome(blocked/needs_human)` escape when PR channels are unreachable —
  no unbounded wedge. No proposed rules (prompt-only change touches no new failure
  mode beyond R6/R8).

## Outcomes & retrospective

**Shipped.** Every worker's first-turn prompt now carries a stage-agnostic
`WORKER_PROTOCOL` preamble (single living source-of-truth + no-scope-creep→typed
child) injected at one seam (`frame_first_turn` in `run.drive`, covering
orchestrator/run.main/direct-drive), and the `impl` template additionally drives
reproduction-first, acceptance mirroring (non-negotiable), temp-proof revert, and
the PR feedback sweep (pre-handoff + on-arrival). All R1–R9 met; +4 tests
(414 total); gate GREEN; `decider.py`/`merger.py` byte-unchanged.

**What went to plan.** Approach B (new seam delegating to an untouched
`with_terminal_contract`) kept the pinned terminal-contract test byte-green and
the terminal-block format un-duplicated — the R8 regression net held with zero
churn to the shared seam. The triage's hard call (source-of-truth = repo doc, not
a Linear-comment workpad) was validated by review-arch as the right
board-ownership-consistent adaptation.

**The notable insight.** The slice was *smaller than `WORKFLOW.md`'s length
suggested*: much of its value already lives in our skills (the impl template
already says "follow execplan/qa/push"), so the genuine net-new was only the
cross-cutting disciplines no skill captured. Naming that up front (spec triage)
kept the build from re-inlining what we already factor into skills.

**This is graduated-autonomy slice 1 of 2 (ADR 0002).** It earns the worker trust
that **slice 2 (selective-escalation decider)** will spend — graduating
`decider.py` from the binary watched/`--autonomous` into a dial that auto-continues
the routine and wakes the Director only on the §2 taste/risk subset. Slice 2 is
the natural next move; not started here.
