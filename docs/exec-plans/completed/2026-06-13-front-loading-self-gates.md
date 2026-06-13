---
status: completed
last_verified: 2026-06-13
owner: claude
base_commit: 808e41891df3f3d9c917beae915b0e140b532333
review_level: targeted
---
# Front-loading self-gates in the ExecPlan methodology

## Goal
The ExecPlan Create step front-loads three design disciplines borrowed from
superpowers' spec-driven workflow, but as **agent self-gates** (the agent
reasons with itself) rather than human approval gates: (1) self-generated
alternatives before locking an approach, (2) a self-interrogated assumptions
ledger, (3) a creation-time self-review — plus a scope-check that forces
multi-subsystem work to split into linked plans. Definition of done, observable:
reading `docs/PLANS.md`, `plugin/skills/harness-init/templates/plans-md.md`, and
`plugin/skills/execplan/SKILL.md` shows the template carrying `## Approach` and
`## Assumptions & open questions` sections, `## When` carrying a scope-check, the
Rules carrying a "front-loading is self-gates" + creation-time-self-review rule,
and the skill's `## Create` prescribing scope-check → front-loading fill →
creation-time self-review; `python3 plugin/scripts/check.py` is GREEN; and this
plan itself has Approach + Assumptions filled (the first use of the new sections).

## Context
- Method + template the change edits: `docs/PLANS.md` (the harness's own
  instance copy) and `plugin/skills/harness-init/templates/plans-md.md` (the
  copy shipped to ported hosts) — kept in sync; the procedure lives in
  `plugin/skills/execplan/SKILL.md`.
- The constitution this builds on: `docs/PRODUCT_SENSE.md` — "Human touchpoints
  (the only two)" + "Escalate ONLY for judgment: product direction, taste
  tradeoffs… / Throughput beats ceremony". Front-loading must embody this:
  self-gates, human only on Taste/Style.
- Source of the borrowed disciplines: superpowers `skills/brainstorming/SKILL.md`
  (propose 2-3 approaches; spec self-review; decompose multi-subsystem) and
  `skills/writing-plans/SKILL.md` (no-placeholder self-review). These are
  human-paired-IDE methodologies; we import the discipline, not the human gates.
- `review_level` (none/targeted/standard/full) was added on this branch
  (808e418, M3 of the flexible-host-governance plan); the front-loading sections
  are tier-proportional against it.

## Approach (self-generated alternatives)
Generated ≥2 viable approaches and chose — own reasoning, not a human dialogue.
- A: Add front-loading as a separate, human-gated phase (literal superpowers
  brainstorm→spec→plan with approval gates between). — Rejected: breaks the
  autonomy thesis (PRODUCT_SENSE.md "minimum human-in-loop"); the human would
  gate every plan, not just Taste/Style.
- B: Add front-loading as **self-gate sections inside the single living
  ExecPlan** (Approach + Assumptions in the template) + steps in the Create
  procedure (scope-check, fill, creation-time self-review). — **Chosen.**
- C: Document the disciplines as prose guidance only, no template sections / no
  Create steps. — Rejected: no forcing function; an autonomous agent that "just
  starts" would skip prose it isn't structurally required to fill.
- Chosen: B — it makes the discipline structural (a section the agent must fill,
  a Create step it must run) while keeping it autonomous and inside the one
  living document. (mirrored into Decision log)

## Assumptions & open questions (self-interrogation)
- Assumption: `review_level` is the right tiering hook, so "review_level: none →
  one line" makes the sections tier-proportional. — Breaks if review_level is
  later removed; then the "none → one line" note detaches and must be reworded.
  Acceptable: review_level just landed (M3) and is the chosen direction.
- Assumption: the two PLANS.md copies (instance `docs/PLANS.md` + host template)
  must both carry the change or hosts won't inherit it. — Confirmed by the
  fan-out: 808e418 itself edited both copies.
- Open: should the execplan skill also be templatized per-host like PLANS.md?
  → Resolved autonomously: no — the skill is machine-shared (one copy under
  `plugin/skills/`), not an instance doc; edit it once.
- Open: which branch does this land on, given the change depends on review_level
  (only on the unmerged, pushed `flexible-host-governance`)? → Escalated as a
  true integration judgment call; human chose: stack on flexible-host-governance.

## Milestones
- [x] M1 `docs/PLANS.md` (instance) carries: scope-check in `## When`; `##
  Approach` + `## Assumptions & open questions` in the Template; the
  self-gate + creation-time-self-review rules in `## Rules`; `last_verified`
  bumped. Verify by reading the file.
- [x] M2 `plugin/skills/harness-init/templates/plans-md.md` (host template)
  mirrors M1's section changes verbatim (so ported hosts inherit them). Verify
  the same four sections are present and `{{TODAY}}` preserved.
- [x] M3 `plugin/skills/execplan/SKILL.md` `## Create` prescribes the
  scope-check, the front-loading fill (Approach + Assumptions), and a
  creation-time self-review step. Verify by reading the file.
- [x] M4 `python3 plugin/scripts/check.py` is GREEN; this plan demonstrates the
  new Approach + Assumptions sections filled; completion gate (targeted →
  review-arch) SATISFIED.

## Progress log
- 2026-06-13: Plan created. Ran the *new* creation-time self-review on this plan
  itself (dogfood): no placeholders; Approach↔Goal↔Milestones consistent; single
  subsystem (the methodology docs) so no decompose; requirements read one way.
- 2026-06-13: M1-M3 done — edited both PLANS.md copies (When scope-check,
  Template Approach + Assumptions, Rules self-gate + creation-time self-review)
  and execplan SKILL.md Create (scope-check → front-loading fill →
  creation-time self-review, renumbered 1-5). Gate GREEN (lint_structure /
  lint_docs / gen_inventory OK, 89 tests). Self-reviewed the working-tree diff:
  nothing to flag. Committing the implementation, then targeted persona review.

## Surprises & discoveries
- The harness repo was checked out from `flexible-host-governance` to `master`
  mid-session by an external actor (reflog HEAD@{0} `checkout: ... to master`,
  likely a SessionStart hook). Caught it before editing because the same path
  read differently across two reads (review_level present, then absent). Lesson:
  on a multi-worktree repo, re-confirm the branch before every edit/commit.
- `review_level` lives only on this branch, not master — so this change is
  branch-coupled until `flexible-host-governance` merges. Stacking here (vs a
  master-based tier-neutral version) was the human's integration call.

## Decision log
- 2026-06-13: Chose Approach B (self-gate sections in the living plan) over a
  separate human-gated phase (A) or prose-only guidance (C) — structural forcing
  without breaking autonomy.
- 2026-06-13: Land on `flexible-host-governance` (stack on 808e418), not master
  — the change depends on review_level which only exists here; human-confirmed
  integration choice. base_commit pinned to 808e418 so the completion-gate diff
  is exactly this change.
- 2026-06-13: Rejected importing superpowers' human approval gates, uniform
  per-project ceremony, and two-document (spec+plan) split — all conflict with
  PRODUCT_SENSE.md (autonomy, risk-budgeted ceremony, single living ExecPlan).
  Imported only the front-loading *discipline*, as self-gates / one document.

## Feedback (from completion gate)
- review-arch (codex gpt-5.5, effort high), diff 808e418..HEAD: **SATISFIED** —
  no P1, no P2, no proposed rule additions. Consistent with the self-review and
  the GREEN gate. (targeted budget: one persona, the architecture/design-taste
  risk this diff touches.)

## Outcomes & retrospective
- Shipped: front-loading discipline (self-generated Approach alternatives,
  self-interrogated Assumptions, a scope-check, a creation-time self-review) is
  now structural in ExecPlan Create — sections in the template + steps in the
  skill — in both the instance (`docs/PLANS.md`) and host-template copies, plus
  the machine-shared execplan skill. Imported as **self-gates**: the agent
  reasons with itself; the human stays on Taste/Style/judgment (PRODUCT_SENSE.md).
- Dogfood result: this plan is the first artifact written under the new format
  (Approach + Assumptions filled). The new creation-time self-review found
  nothing to fix — the right outcome for a small, single-subsystem plan, and a
  live demonstration that the gate is cheap when the plan is already good.
- What we deliberately did NOT import from superpowers: human approval gates,
  uniform per-project ceremony, and the two-document (spec + plan) split — each
  conflicts with the harness's autonomy + risk-budgeted-ceremony + single-living-
  ExecPlan model. Only the discipline crossed over, reshaped into self-gates.
- Forward: the sections are tier-proportional ("review_level: none → one line").
  Watch that they don't ossify into ceremony on trivial plans; if a `none`-tier
  plan ever feels heavier for them, tighten the wording. When
  `flexible-host-governance` merges to master, this change rides along.
