---
status: active
last_verified: 2026-06-12
owner: harness
base_commit: 5f17c42
---
# Build the memory loop (Phases 3-5) + retrospective (Phase 6)

## Goal
Layer 2 of the v1 spec: STORE tree, 2-stage feeder (INJECT), imprint queue
(IMPRINT), dreaming (CONSOLIDATE). Done = spec §7 success criteria pass.

## Context
- Spec: docs/superpowers/specs/2026-06-12-agent-harness-v1-design.md §3
- Superpowers plan: docs/superpowers/plans/2026-06-12-agent-harness-v1.md
  Tasks 12-18 (this ExecPlan mirrors them — update both).
- References: docs/references/ digests (hook contracts).

## Milestones
- [ ] M1 memory STORE tree + lint green (Task 12)
- [ ] M2 SessionStart feeder injects context pack (Task 13)
- [ ] M3 first-prompt enrichment works (Task 14)
- [ ] M4 imprint queue: session digest written after a session ends (Task 15)
- [ ] M5 /dream consolidates and gate stays green (Task 16)
- [ ] M6 completion gate + spec §7 validation (Tasks 17-18)

## Progress log
- 2026-06-12: plan created; Phases 0-2 done (foundation, lint gate, skills,
  personas). Phase 0-1 review gate passed: D5/D9 lints tightened per quality
  review (be20209); 4 fix-forward items logged in tech-debt-tracker.

## Surprises & discoveries
- lint_structure must exempt itself from S2/S3 (defines the token literals
  it scans for) — found by Task 4 implementer.
- D5/D8 needed scope fixes (superpowers/ exemption; empty-category skip)
  before the gate could ever go green — found when check.py first ran.

## Decision log
- 2026-06-12: PreCompact uses imprint queue, not in-session injection —
  hooks digest confirmed PreCompact does NOT support additionalContext.
- 2026-06-12: feeder = script-embedded prompt, not agents/feeder.md
  (hooks spawn headless claude; DRY).
- 2026-06-12: unittest over pytest (internalization rule).
- 2026-06-12: CLAUDE.md = 3-line pointer to AGENTS.md.

## Feedback (from completion gate)

## Outcomes & retrospective
