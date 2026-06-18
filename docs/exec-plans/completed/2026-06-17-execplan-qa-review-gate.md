---
status: completed
last_verified: 2026-06-17
owner: harness
type: exec-plan
tags: [execplan, review, autonomy]
description: Adds two always-on review agents to the ExecPlan completion gate — spec-compliance and code-quality — that emit the P1/P2/Verdict finding contract on every plan completion alongside the risk-budgeted personas.
base_commit: 35d4d1fdf5dee4d469e0c6209a1a78ec0ce03343
review_level: targeted
---
# ExecPlan QA gate — always-on spec-compliance + code-quality review

## Goal

The `agent-harness:execplan` completion gate gains **two always-on review agents**
adapted from superpowers — `review-spec-compliance` (did we build exactly the
spec/plan — nothing missing, nothing extra?) and `review-code-quality` (is the diff
clean, tested, maintainable?) — that emit our existing **P1/P2/Verdict** finding
contract and run on **every** ExecPlan completion, alongside the risk-budgeted
personas. Observable definition of done:
1. `plugin/agents/review-spec-compliance.md` and `plugin/agents/review-code-quality.md`
   exist in our agent format (frontmatter + grounding + the `P1 / P2 / Proposed rule
   additions / Verdict` output block, like `review-arch.md`).
2. `docs/PLANS.md` completion gate + Review-budget document them as **always-on**, and
   reframe `review_level` to govern only the *risk personas* (arch/reliability/security)
   — the two QA reviews are unconditional.
3. `plugin/skills/execplan/SKILL.md` completion gate dispatches them as a step
   (ordered: spec-compliance → code-quality → risk personas), with the same
   P1→fix-now / P2→tech-debt processing.
4. `docs/generated/component-inventory.md` is regenerated to include both agents and
   `docs/design-docs/agent-harness.md` catalogues them (D9 coverage stays green on the
   self-hosted plugin).
5. `python3 plugin/scripts/check.py` is GREEN.

## Context

- **Why (this conversation, 2026-06-17):** the execplan gate had no always-on
  "did you build the spec?" + "is the code good?" check — review was risk-budgeted
  personas only (`review_level: none` skipped review entirely). Surfaced when a slice-2
  completion ran only `review-arch`. AGENTS.md law: "Struggling = harness gap → encode
  the fix." User decision: add the two superpowers reviews as always-on gate steps,
  Claude agents (no codex requirement), adapted to our verdict format.
- **Source rubrics (adapt, don't blind-copy):**
  `…/superpowers/skills/subagent-driven-development/spec-reviewer-prompt.md`
  (spec compliance: don't trust the report, read code, check missing/extra/misunderstood)
  and `…/code-quality-reviewer-prompt.md` + `…/requesting-code-review/code-reviewer.md`
  (plan-alignment, separation of concerns, tests-verify-real-behavior, single
  responsibility / file growth).
- **Our format + contract:** `plugin/agents/review-arch.md` — frontmatter
  (`name`/`description`/`tools`) + grounding + the exact `## P1 (blocks completion) /
  ## P2 (fix-forward) / ## Proposed rule additions / ## Verdict: SATISFIED | NOT
  SATISFIED` block. Adapt the superpowers rubric INTO this contract so the gate's
  P1→fix / P2→tech-debt loop applies uniformly.
- **The gate to edit:** `plugin/skills/execplan/SKILL.md` "Completion gate" step 3
  (Spend the plan's review budget) + `docs/PLANS.md` "Review budget" + Template.
- **D9 / inventory coupling (must not redden the self-hosted gate):** adding a plugin
  agent requires (a) regenerating `docs/generated/component-inventory.md` and (b) the
  agent being mentioned in a coverage hand-doc — `docs/design-docs/agent-harness.md`
  catalogues the existing review agents (tech-debt-tracker row 15 records this
  self-hosted coupling). The regen command lives in `docs/design-docs/agent-harness.md`.

## Approach (self-generated alternatives)

- **A — a separate `/qa` skill invoked after execplan.** Mirrors the
  product-design→execplan handoff most literally. Rejected: a skill you must *remember*
  to invoke is forgettable, which defeats "always-on" — the whole requirement.
- **B — two more review agents as an always-on step inside the execplan completion
  gate (chosen).** The completion gate already runs unconditionally as execplan's final
  phase, so a step there is genuinely always-on. The two agents stack on the existing
  personas and reuse the P1/P2/Verdict processing verbatim. This is exactly the user's
  instruction ("just adding two more review agents alongside review-arch").
- **Chosen: B.** Always-on by construction; minimal new surface; uniform finding loop.

## Assumptions & open questions (self-interrogation)

- **Assumption:** "always-on" = unconditional for every ExecPlan regardless of
  `review_level`; `review_level` now governs only the risk personas
  (arch/reliability/security). User confirmed ("always-on review gate"). *If wrong:*
  they'd be budgeted like the personas — a one-line wording change.
- **Assumption:** always-on does NOT over-ceremony trivial work, because the PLANS.md
  entry decision routes throwaway/small work to an in-conversation plan with **no
  execplan gate at all** — only real ExecPlans (non-trivial by definition) hit this gate.
- **Assumption:** spec-compliance grounds in the linked `docs/product-specs/` spec
  (R1..Rn) when present, else the plan's Goal + Milestone acceptance — so it works for
  both spec-backed and inline-spec ExecPlans. Baked into the agent prompt.
- **Open:** does a new agent need registration beyond the file + inventory + coverage
  doc? → resolved by running the gate (D9/inventory are the arbiters); fix to GREEN.
- No product-direction forks remain (user settled where-it-lives, executor, format) →
  no escalation.

## Milestones

- **M1 — the two agent files.** At the end, `plugin/agents/review-spec-compliance.md`
  and `plugin/agents/review-code-quality.md` exist, each: frontmatter (`name`,
  one-line `description` naming "always-on execplan gate", `tools: Read, Grep, Glob,
  Bash`), a grounding paragraph (spec-compliance → the linked product-spec else the
  plan Goal/acceptance, read the CODE not the report; code-quality → the diff +
  `docs/DESIGN.md`, the superpowers checklist), and the exact `## P1 / ## P2 /
  ## Proposed rule additions / ## Verdict` output block. Acceptance: both files parse
  as agents (same shape as `review-arch.md`); `python3 plugin/scripts/check.py` does not
  yet need to be green here (M3 closes coverage).

- **M2 — wire into the gate.** At the end, `plugin/skills/execplan/SKILL.md` completion
  gate has an always-on review step (run spec-compliance, then code-quality only if
  compliance is SATISFIED, then the `review_level` risk personas; all findings flow
  through the same P1→fix-now / P2→tech-debt loop), and `docs/PLANS.md` Review-budget +
  completion-gate text states the two QA reviews are always-on while `review_level`
  governs only the risk personas. Acceptance: reading the skill + PLANS.md, a novice
  runs spec-compliance + code-quality on every ExecPlan; the diff shows both files
  updated; gate GREEN after M3.

- **M3 — coverage + inventory + GREEN, then dogfood.** At the end,
  `docs/design-docs/agent-harness.md` catalogues both new agents and
  `docs/generated/component-inventory.md` is regenerated (via the command named in
  `docs/design-docs/agent-harness.md`), so D9 coverage + inventory-check pass. Run
  `python3 plugin/scripts/check.py`; expect GREEN. Then **dogfood**: the completion gate
  for THIS plan runs the two NEW always-on agents (+ `review-arch`, `targeted`) on this
  diff — the first live use validates them on their own change.

## Progress log
- [x] (2026-06-17) M1 — created `plugin/agents/review-spec-compliance.md` (read code
  not report; missing/extra/misunderstood vs the linked spec R1..Rn else plan
  Goal/acceptance) + `plugin/agents/review-code-quality.md` (grounded in DESIGN.md +
  core-beliefs; decomposition/file-growth/error-at-real-boundaries/tests-verify-real;
  Critical→P1, Important+Minor→P2). Both emit the exact review-arch P1/P2/Proposed/Verdict block.
- [x] (2026-06-17) M2 — execplan SKILL.md completion gate: new step 3 (always-on
  spec-compliance → code-quality-if-compliance-SATISFIED), risk personas demoted to
  step 4 governed by `review_level` only; renumbered process/finalize. PLANS.md
  Review-budget reframed (two QA reviews always-on; `review_level` governs only risk
  personas, `none` still runs the QA pair).
- [x] (2026-06-17) M3 — catalogued both agents in docs/design-docs/agent-harness.md;
  regenerated docs/generated/component-inventory.md (both agents present);
  `python3 plugin/scripts/check.py` GREEN. Dogfood review in the completion gate below.

## Surprises & discoveries
- **Agent-registry staleness:** an agent `.md` created mid-session is NOT dispatchable
  by `subagent_type` until the next session — the registry loads at session start.
  `agent-harness:review-spec-compliance` returned "not found" when dispatched this
  session. The files are correct (review-arch confirmed the format; both appear in the
  regenerated inventory + coverage doc) and WILL dispatch next session. The dogfood was
  therefore run via `general-purpose` agents carrying the exact rubric from each agent
  file (functionally identical: same rubric, same diff, same P1/P2/Verdict contract).
  Implication: the always-on gate is fully live from the NEXT ExecPlan onward.

## Decision log
- 2026-06-17: chose gate-step over a separate `/qa` skill — a separate skill is
  forgettable, which defeats always-on (user-confirmed where-it-lives).
- 2026-06-17: agents are Claude (no codex requirement) — user dropped the codex
  constraint for the execplan QA agents; the global CLAUDE.md note stays untouched.

## Feedback (from completion gate)
Dogfood — the new gate run on its own change:
- **review-arch (targeted):** SATISFIED, no P1/P2. Proposed (→ tech-debt): DESIGN.md's
  "1 persona ↔ 1 grounding doc" phrasing is now imprecise (code-quality grounds in two
  docs; spec-compliance in per-plan specs); `subagent_type`↔filename has no lint.
- **review-spec-compliance (via general-purpose; registry-stale):** SATISFIED, no
  P1/P2 — all 5 Goal DoD items + 3 milestone acceptances verified against the files.
- **review-code-quality (via general-purpose):** SATISFIED, no P1. Two **P2 doc-drift**
  findings — `AGENTS.md` §Review and `ARCHITECTURE.md` REVIEW data-flow still described
  review as `review_level`-only — **fixed now** (one clause each: the always-on QA pair
  precedes the risk personas). Proposed (→ tech-debt): harness-init seed templates
  (`plans-md.md`/`agents-md.md`) still carry the old framing — host-customizable by
  design, so deliberately left.

## Outcomes & retrospective
**Shipped:** two always-on review agents — `review-spec-compliance` ("built exactly the
spec/plan?") and `review-code-quality` ("is it well-built?") — adapted from superpowers
into our `P1/P2/Proposed/Verdict` contract, wired into the execplan completion gate as an
**unconditional** step 3 (compliance → code-quality-if-SATISFIED) ahead of the
`review_level` risk personas (step 4). `docs/PLANS.md`, `AGENTS.md`, and `ARCHITECTURE.md`
reframed so the QA pair is always-on and `review_level` governs only the risk personas;
both agents catalogued + the component inventory regenerated.

**Result:** every future ExecPlan now gets "did you build the spec?" + "is the code
good?" unconditionally, on top of the risk-budgeted personas — closing the methodology
gap that let a completion run only `review-arch`. Gate GREEN; all three completion
reviews SATISFIED. The gate was dogfooded on its own change.

**Caveat:** mid-session registry staleness meant the two new agents were exercised via
`general-purpose` carrying their rubric this session; they dispatch by `subagent_type`
from the next session on (see Surprises). The standing tech-debt items are doc-debt
follow-ups (DESIGN.md grounding phrasing; harness-init seed-template framing).
