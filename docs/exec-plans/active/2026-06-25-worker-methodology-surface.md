---
status: active
last_verified: 2026-06-25
owner: harness
type: exec-plan
description: Implement ADR 0005 — fold the impl craft into WORKER_PROTOCOL, delete the five per-stage prompt templates, make compose_worker_prompt return the raw ticket, and keep the dev-stage label as dispatch/DAG metadata only.
base_commit: 6ef9d79
review_level: targeted
---
# Worker methodology surface — drop stage templates, WORKER_PROTOCOL carries the craft

## Goal
Implement [ADR 0005](../../adr/0005-no-stage-prompt-templates.md): the worker's only
injected operating instruction is `WORKER_PROTOCOL` (+ `TERMINAL_CONTRACT`); the five
per-stage prompt templates are gone; `compose_worker_prompt` returns the ticket's own
prompt unchanged; the dev-stage label survives as dispatch/DAG **metadata** only.

Observable definition of done: (a) `director/taxonomy.py` no longer defines
`_PLANNING_/_RESEARCH_/_DESIGN_/_SPEC_/_IMPL_TEMPLATE`; (b) `WORKER_PROTOCOL` carries the
implementation craft (reproduction-first, acceptance-mirroring, temp-proof-revert,
PR-feedback-sweep incl. resolve-threads + structured `report_outcome` evidence, self-QA,
gate cadence, sync-before-work, rework-reset) as conditional guidance; (c)
`compose_worker_prompt(ticket)` returns `ticket["prompt"]` for **every** ticket (typed or
not); (d) `ticket_type`/`TAXONOMY` still resolve a label → type for `dispatch_requires_label`
and DAG sequencing, with `template` removed from the registry; (e) the orchestrator and
`director.run` send byte-identical worker prompts for the same ticket; (f) tests + docs
updated; `python3 plugin/scripts/check.py` GREEN.

## Context
- Decision + rationale: [ADR 0005](../../adr/0005-no-stage-prompt-templates.md) (owns the
  *what*/*why* — do not re-derive). Completes [ADR 0004](../../adr/0004-ticket-purpose-unit.md);
  grounded in the LIN-29 dogfood (a worker right-sized with only `WORKER_PROTOCOL`).
- Files: `director/taxonomy.py` (templates, `WORKER_PROTOCOL`, `TAXONOMY`,
  `compose_worker_prompt`), `tests/test_director_taxonomy.py`,
  `tests/test_director_orchestrator.py` (the `TypeRoutingTest` prompt assertions),
  `director/orchestrator.py:91` (calls `compose_worker_prompt` — stays, now a raw pass-through),
  `director/run.py:428` (`frame_first_turn` — unchanged).
- The impl craft to PRESERVE lives today in `_IMPL_TEMPLATE` (self-QA + PR self-description
  from the worker-qa slice; reproduction/acceptance/temp-proof/PR-sweep from gap #5;
  sync-before-work + rework-reset from ADR 0004). None of it may be lost — it MOVES into
  `WORKER_PROTOCOL`.
- Memory: [[parallel-sessions-share-master-index]] — stage only this plan's own paths.

## Approach (self-generated alternatives)
- **A — Delete templates; fold impl craft into `WORKER_PROTOCOL`; `compose_worker_prompt`
  → raw; keep `TAXONOMY` minus `template`.** Tradeoff: smallest surface that realizes ADR
  0005; converges run/orchestrator; keeps label/DAG semantics intact. Cost: `WORKER_PROTOCOL`
  grows (it becomes the full operating contract) — accept, phrased conditionally.
- **B — Keep `_IMPL_TEMPLATE`, delete only the other four.** Tradeoff: smaller diff, but
  leaves the label shaping the prompt for `impl` (contradicts ADR 0005 "label = metadata
  only") and keeps the run/orchestrator divergence for impl tickets. Rejected — it doesn't
  realize the decision.
- **Chosen: A.** It is exactly ADR 0005. (Mirrored in Decision log.)

## Assumptions & open questions (self-interrogation)
- **Open (load-bearing) — does the claude worker auto-load `AGENTS.md`?** ADR 0005 relies on
  it. Verify on the claude worker (worker-runtime app-server): does an SDK session read
  `AGENTS.md`/`CLAUDE.md` from cwd at start? → M-verify: a tiny live/inspection check, or read
  the SDK options in `worker-runtime`. If it does NOT auto-load, add a single first-turn
  pointer line to `frame_first_turn` (the minimal fallback ADR 0005 names) and record it.
  Resolved direction: ship template removal regardless; the AGENTS.md-autoload result only
  decides whether the one fallback line is needed.
- Assumption: nothing consumes the `template`/`methodology_refs`/`output` registry fields at
  runtime (only `compose_worker_prompt` reads `template`). Verify by grep before deleting the
  fields. What breaks if wrong: a consumer KeyErrors. Mitigation: grep + keep the fields if
  any non-test consumer exists.
- Assumption: `ticket_type` is still needed (dispatch_requires_label + DAG). Verified — keep it.
- Open: keep `child_types` in `TAXONOMY`? → resolved KEEP — it documents the DAG typing
  (ADR 0004's size-split edge) and has test coverage; it is metadata, consistent with 0005.

## Milestones
- **M1 — `WORKER_PROTOCOL` absorbs the impl craft.** Rewrite `WORKER_PROTOCOL` so that, after
  its existing cross-stage disciplines (source-of-truth, board-comment mirror, propose-don't-set,
  two-trigger self-contained issuance, proportional context), it carries a conditional
  **"When you implement / open a PR"** block with: reproduction-first, acceptance-criteria
  mirroring, temp-proof-revert, the PR-feedback sweep (all channels, resolve each thread,
  structured `report_outcome` evidence — `checks_state`/`unresolved_threads`/`acceptance_verified`,
  merger re-verifies), self-QA (host gate green + spec/code self-review + task-specific tests),
  gate cadence (targeted during iteration, full gate once near completion), sync-before-work
  (origin/main + recorded evidence), and rework-reset (approach-rejected → close PR / fresh
  branch / fresh plan vs incremental sweep). At the end every discipline currently in
  `_IMPL_TEMPLATE` is present in `WORKER_PROTOCOL`, phrased conditionally. Run
  `python3 -m unittest discover -s tests -p test_director_taxonomy.py`; expect the migrated-
  discipline assertions (moved to target `WORKER_PROTOCOL`) green.
- **M2 — Delete the five templates; `compose_worker_prompt` → raw; trim `TAXONOMY`.** Remove
  `_PLANNING_/_RESEARCH_/_DESIGN_/_SPEC_/_IMPL_TEMPLATE`; `compose_worker_prompt(ticket)` returns
  `ticket.get("prompt","")` for all tickets; drop the `template` field (and the now-orphan
  `methodology_refs`/`output` host pointers — grep-confirmed unconsumed) from `TAXONOMY`, keeping
  `label`/`stage`/`child_types`. `ticket_type` unchanged. At the end no stage template exists and
  the composed prompt equals the raw ticket. Run the taxonomy suite; expect green.
- **M3 — Tests realigned.** `tests/test_director_taxonomy.py`: drop the template-content
  assertions (spec/impl/planning template substrings); assert instead `compose_worker_prompt`
  returns the raw prompt unchanged for a typed AND untyped ticket, and that the impl-craft
  substrings now live in `WORKER_PROTOCOL`; keep `ticket_type`/label/`child_types` tests.
  `tests/test_director_orchestrator.py` `TypeRoutingTest`: the per-type prompt assertions
  (`sub-project`/`design-docs`/`product-design`/`execplan`) become "the composed prompt equals
  the raw ticket prompt" (routing now sequences by label/DAG, not prompt content). Run both
  suites; expect green.
- **M4 — AGENTS.md auto-load verification + docs + gate.** Verify the claude worker auto-loads
  `AGENTS.md` (inspect `worker-runtime` SDK options or a gated check); if not, add the one
  fallback pointer line to `frame_first_turn` and note it (else record "auto-load confirmed —
  no pointer needed"). Update `director/taxonomy.py` module docstring (no templates; WORKER_PROTOCOL
  is the contract; label = metadata), `.claude/DIRECTOR.md` §14 worker-profile (worker prompt =
  raw ticket + WORKER_PROTOCOL + TERMINAL_CONTRACT; methodology via AGENTS.md/skills). Run
  `python3 plugin/scripts/check.py` GREEN. Completion gate: behavioral check = the run/orchestrator
  prompt-parity assertion (a real observable — the composed prompt) + N/A for app behavior; self-review
  vs base_commit; always-on review-spec-compliance → review-code-quality; targeted review-arch (it
  removes a subsystem layer). Process P1/P2; complete + `git mv` to completed/.

## Progress log
- [x] (2026-06-25) Plan created (base_commit 6ef9d79; ADR 0005 + plan committed 604e48e).
- [x] (2026-06-25) M1 — `WORKER_PROTOCOL` absorbs the impl craft as a conditional "when you
  implement / open a PR" block (reproduction-first, sync-before-work, acceptance mirroring,
  temp-proof revert, self-QA, gate cadence, PR self-description, PR-feedback sweep + resolve
  threads + structured evidence, rework-reset) — host-AGNOSTIC (no `check.py`/execplan path).
- [x] (2026-06-25) M2 — deleted all five stage templates; `compose_worker_prompt` returns the
  raw ticket prompt; `TAXONOMY` trimmed to `label`/`stage`/`child_types` (dropped `template`/
  `methodology_refs`/`output`; grep-confirmed no non-test consumer); `ticket_type` unchanged.
- [x] (2026-06-25) M3 — `tests/test_director_taxonomy.py`: template-content tests → raw-passthrough
  (`ComposePromptTest`) + impl-craft-in-`WORKER_PROTOCOL` (`ImplCraftInProtocolTest`); registry-
  fields test trimmed; gate-cadence test moved to `WORKER_PROTOCOL`. `tests/test_director_orchestrator.py`
  `TypeRoutingTest`: per-type prompt-content assertions → raw-passthrough + DAG-order. Both suites green.
- [x] (2026-06-25) M4 — **AGENTS.md auto-load CONFIRMED**: worker `settingSources` defaults to
  `["user","project","local"]` (SDK: `"project"` loads CLAUDE.md), app-server doesn't override →
  CLAUDE.md auto-loads → points to AGENTS.md. **No `frame_first_turn` fallback needed.** Docs:
  taxonomy docstring (M2) + DIRECTOR.md §14 worker-profile (first-turn prompt + AGENTS.md carrier).

## Surprises & discoveries
- (2026-06-25) DIRECTOR.md §14 still cited `director/taxonomy.py:_IMPL_TEMPLATE` for the SELF-QA
  discipline — a stale surviving body of the deletion (the rule I keep re-learning). Repointed to
  `WORKER_PROTOCOL`. The grep for stale template refs across director/tests/plugin is part of M3.

## Decision log
- 2026-06-25: Approach A (delete all five; fold impl craft into WORKER_PROTOCOL) over B
  (keep _IMPL_TEMPLATE) — B contradicts ADR 0005 "label = metadata only" and keeps the
  run/orchestrator divergence.

## Feedback (from completion gate)

## Outcomes & retrospective
