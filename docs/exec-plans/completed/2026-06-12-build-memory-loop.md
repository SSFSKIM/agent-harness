---
status: completed
last_verified: 2026-06-12
owner: harness
type: exec-plan
tags: [memory, store, feeder, dreaming, consolidation]
description: Built Layer 2 of the v1 spec — the memory loop with a STORE tree, a two-stage feeder for injection, an imprint queue, and dreaming-based consolidation passing the spec's success criteria.
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
- [x] M1 memory STORE tree + lint green (Task 12)
- [x] M2 SessionStart feeder injects context pack (Task 13)
- [x] M3 first-prompt enrichment works (Task 14)
- [x] M4 imprint queue: session digest written after a session ends (Task 15)
- [x] M5 /dream consolidates and gate stays green (Task 16)
- [x] M6a completion gate passed (Task 17)
- [x] M6b spec §7 validation (Task 18)

## Progress log
- 2026-06-12: plan created; Phases 0-2 done (foundation, lint gate, skills,
  personas). Phase 0-1 review gate passed: D5/D9 lints tightened per quality
  review (be20209); 4 fix-forward items logged in tech-debt-tracker.
- 2026-06-12: M1 done — memory STORE tree (bootloader, progress, 4 category indexes).
- 2026-06-12: M2 done — SessionStart feeder (feeder_sessionstart.py + hooks/hooks.json). Live
  verification: haiku quoted "Phase 0-2 complete..." from the injected pack. 33 tests green.
- 2026-06-12: M3 done — first-prompt feeder (feeder_firstprompt.py + UserPromptSubmit hook).
  mark_if_new R7 confirmed: second call returns immediately; seen-sessions.txt written. 34 tests green.
- 2026-06-12: M4 done — imprint loop (imprint_guard/enqueue/run + PreCompact+SessionEnd hooks). E2E verified:
  synthetic transcript → digest 2026-06-12-e2e-test.md (status: archived), knowledge/recursion-guard.md
  written, progress/current.md updated, lint GREEN. Idempotency confirmed (duplicate enqueue skipped).
  36 tests green. Commit 1a9ca64.
- 2026-06-12: M5 done — dreamer agent + dream skill (direct-write, lint-terminated). Live consolidation
  against 2026-06-12-e2e-test.md: recursion-guard.md already current (truthful no-op, UPDATE-beats-duplicate
  verified). Marker written. progress/current.md updated. check.py GREEN. 36 tests green.
- 2026-06-12: M6a done — completion gate (Task 17). 3 persona reviews (parallel). arch: SATISFIED (0P1);
  reliability: NOT SATISFIED → P1 fixed (per-entry exception isolation in imprint_run.py) → SATISFIED;
  security: NOT SATISFIED → P1 fixed (json.dumps encoding in feeder_firstprompt.py prompt) → SATISFIED.
  R8/R9/R10 added to RELIABILITY.md; T6/T7 added to SECURITY.md; DESIGN.md updated (skills, agents).
  MEMORY.md digest filename contract added. 2 new P2s in tech-debt-tracker. check.py GREEN.

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
- 2026-06-12 Phase 3-5 review gate: spec COMPLIANT (no P1); digest filename
  collision fixed immediately (event suffix added); 13 fix-forward findings
  logged in tech-debt-tracker (3 Important: poison-entry drain stall,
  untested compile_pack degradation, drain logic untestable in main()).
- 2026-06-12 Task 17 completion gate (3 personas): review-arch SATISFIED;
  review-reliability NOT SATISFIED (P1: no per-entry exception isolation in
  imprint_run drain → fixed immediately, re-verified SATISFIED); review-security
  NOT SATISFIED (P1: raw user prompt interpolated into feeder child prompt,
  T1 violation → fixed with json.dumps encoding, re-verified SATISFIED).
  2 new P2s added to tech-debt-tracker (dreamer T7 guard, imprint Bash glob).
  Rule additions adopted: RELIABILITY.md R8/R9/R10; SECURITY.md T6/T7;
  DESIGN.md skill commit-scoping + non-review persona grounding discipline;
  MEMORY.md session-digest filename contract.
  "Non-review persona grounding doc lint enforcement" noted as tech-debt (not
  yet lint-enforced). Arch proposed rule "skill git add -A discipline" adopted
  in DESIGN.md (already had m3 in tracker for the dream case).
- 2026-06-12: §7 validation 4/4 PASS (criterion 2 with staleness caveat → limitations/progress-staleness.md); in-plugin persona dispatch verified live.

## Outcomes & retrospective

Built the full memory loop (Phases 3-6): STORE tree (bootloader + 4 category
indexes), 2-stage INJECT (SessionStart feeder + first-prompt enrichment feeder),
IMPRINT queue (enqueue/guard/run + PreCompact+SessionEnd hooks writing session
digests), and CONSOLIDATE (dreamer agent + dream skill, lint-terminated). All
live-verified end-to-end against real sessions and synthetic transcripts.

The completion gate (3 parallel personas) proved its value immediately: caught 2
real P1s that would have shipped — per-entry exception isolation (a poison queue
entry would have stalled every drain indefinitely) and raw-prompt injection into
the headless child (T1 violation). Both fixed in-session, re-verified SATISFIED.

Grounding docs grew substantially: R8-R10 (RELIABILITY), T6-T7 (SECURITY), 3
DESIGN rules (skill commit-scoping, non-review grounding discipline, git add -A
narrowing), MEMORY session-digest filename contract. Knowledge feedback loop
exercised: criterion-2 caveat immediately filed as limitations/progress-staleness.md.

§7 success criteria: 4/4 PASS. Self-hosting loop closed (in-plugin Task dispatch
confirmed). Continuity pass with one staleness caveat now documented.

Top v2 candidates from tech-debt: centralize headless-spawn/fail-open helpers in
harness_lib (Important — repeated in 3 hook scripts); compile_pack degradation
tests (Important — R2 headline untested); extract drain() from main() for fixture
tests (Important — per DESIGN explicit-params rule).
