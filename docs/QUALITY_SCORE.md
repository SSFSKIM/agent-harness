---
status: stable
last_verified: 2026-06-14
owner: doc-gardener
---
# QUALITY_SCORE.md — domain × layer grades

Grades: A (exemplary) / B (solid) / C (works, debt noted) / D (fragile) /
F (broken). doc-gardener updates grades + history on each gardening pass.

## Current grades

| Domain | docs | scripts | skills | agents | hooks |
|---|---|---|---|---|---|
| knowledge-system | C | C | - | - | - |
| taste-enforcement | C | C | - | - | - |
| review-gate | - | - | B | A | - |
| dreaming (memory-as-docs) | B | B | B | - | - |
| porting (harness-init) | - | B | B | - | - |
| host-enforcement (setter) | C | B | B | - | - |
| stop-tidy (gate) | - | B | - | - | C |

`-` = not built / not applicable for this domain-layer.
Initial grades C: works, unproven in daily use.

Grade notes:
- review-gate skills B: well-specified, used successfully in gate; no automated test coverage.
- review-gate agents A: caught 2 real P1s in live gate; grounding docs strong.
- dreaming (memory-as-docs) docs B: memory-architecture + dreaming-v2 + docs-sync
  design docs solid; the routing taxonomy is unified with the docs-tree skill.
- dreaming scripts B: dream_run/phase1/phase2/router + memories_* with a real
  unittest suite (extraction, routing allowlist, workspace-scope revert, locking).
- dreaming skills B: `dream-rollouts` lint-terminated, live router PoC verified
  (one real session → tracker row + journal line).
- porting scripts/skills B: scaffold idempotent + fresh-host-lint-green tested;
  live self-host run confirmed idempotency (21 SKIP / 1 CREATE).
- stop-tidy scripts B: 5 unit tests (block-once, fail-open, headless guard);
  hooks C: wired in hooks.json, not yet observed in a live plugin session.
- host-enforcement scripts B: gate_config/gate_command/host-lint step +
  PROTECTED_PATHS clamp, 82 tests, survived a 3-round adversarial gate;
  skills B: the `architecture-setup` skill (FORM-routed: lint for mechanical
  invariants, guide-skill for methodology) + harness-init step 7; its METHOD was
  exercised inline on Lingual (L1 locale lint). agents n/a: the setter was
  converted agent → skill (2026-06-13 — setup needs the main agent's full repo
  context). docs C: ARCHITECTURE inv7 + DESIGN rule + SECURITY T9, fresh.

## History
- 2026-06-12: initial table (Phase 1).
- 2026-06-12: memory loop + review gate graded after §7 validation (Phase 3-6).
- 2026-06-12: portability hardening — porting + stop-tidy rows added; S7/D10
  lints and pre-commit hook land in existing domains' scripts.
- 2026-06-13: host-enforcement (setter) row added — `.harness.json` substrate
  (host-lint step + threshold overrides) + architecture-setter persona;
  demonstrated on Lingual (locale-parametric L1 lint). Passed a 3-round gate.
- 2026-06-13: architecture-setter agent → `architecture-setup` skill; output
  FORM-routed (lint for mechanical invariants, guide-skill for methodology).
  Setup needs full repo context; review-arch stays a persona.
- 2026-06-14: portable propagation — the old memory loop (`feeder`/`imprint`/
  `memory-store`/`dreamer`) was retired; its scorecard rows + notes collapse into
  the one `dreaming (memory-as-docs)` row (memory IS the docs tree now).
