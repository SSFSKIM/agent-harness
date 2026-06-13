---
status: active
last_verified: 2026-06-13
owner: codex
base_commit: f89b5a50c8ce268ece146a7c031182a2ea9f2cb8
review_level: standard
---
# Flexible Host Governance
## Goal
Make the harness less bureaucratic for ported hosts while keeping the
machine-critical surface strict: host-specific docs become agentically shaped by
`harness-init`, ExecPlan review cost becomes risk-budgeted, and review personas
can flag demonstrable bugs without inventing unwritten taste rules.
## Context
- `ARCHITECTURE.md` defines the instance/machine split and the current strict
  S/D lint substrate.
- `plugin/scripts/lint_docs.py` currently governs most docs by default and runs
  D9 component coverage against host prose.
- `plugin/skills/harness-init/SKILL.md` and its templates define the porting
  experience for fresh and legacy repos.
- `plugin/skills/execplan/SKILL.md`, `docs/PLANS.md`, and the review personas
  define the completion-gate cost.
- Human direction on 2026-06-13: models get better; remove unnecessary fixed
  constraints so agents can reason project-specifically. Keep the harness
  structure clear, but do not let strict defaults limit progress.
## Milestones
- [x] M1 Relax docs governance for ported hosts: only machine-critical docs and
  harness-managed roots are strict by default; host-specific docs under `docs/`
  are flexible unless opted into governance.
- [x] M2 Update `harness-init` and docs-tree guidance so agents create
  project-specific docs structure during porting instead of forcing every host
  into the same product-specs/references shape.
- [x] M3 Add ExecPlan `review_level` semantics and make the completion gate
  risk-budgeted (`none`, `targeted`, `standard`, `full`).
- [x] M4 Narrow review-persona "ONLY authority" language to taste authority;
  demonstrable correctness/reliability/security bugs may still be P1s.
- [x] M5 Replace the negative-space command rule with a preferred-path rule:
  named commands/skills are routine defaults, but exploratory CLI work is
  allowed when it serves the task; repeated usage gets promoted into docs/skills.
- [x] M6 Verify with focused tests plus the full gate.
## Progress log
- 2026-06-13: Plan created from user-approved maturity direction.
- 2026-06-13: Implemented tiered docs governance (`doc_governance`,
  `managed_doc_roots`, self-host strictness, D9 self-host default), made
  external-plugin component inventory advisory unless opted into strictness,
  updated harness-init/docs-tree/templates, added review budget semantics,
  softened review persona authority, and replaced negative-space wording. Gate
  GREEN: `python3 plugin/scripts/check.py` (89 tests).
- 2026-06-13: Re-ran final gate after memory/progress updates: GREEN
  (`lint_structure`, `lint_docs`, `gen_inventory`, 89 tests).
## Surprises & discoveries
## Decision log
- 2026-06-13: Keep self-host strict. The self-host repo is the reference
  implementation, so strict D-lints still catch drift here.
- 2026-06-13: Ported hosts default to flexible project docs. Machine-critical
  docs remain blocking; host-owned business/product/research docs do not become
  commit blockers unless the host opts them into managed roots.
## Feedback (from completion gate)
## Outcomes & retrospective
