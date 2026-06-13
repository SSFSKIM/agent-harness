---
status: stable
last_verified: 2026-06-13
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
| memory-store | B | - | - | - | - |
| feeder (INJECT) | C | B | - | - | B |
| imprint | B | B | - | - | B |
| dreaming | B | - | B | B | - |
| porting (harness-init) | - | B | B | - | - |
| host-enforcement (setter) | C | B | B | - | - |
| stop-tidy (gate) | - | B | - | - | C |

`-` = not built / not applicable for this domain-layer.
Initial grades C: works, unproven in daily use.

Grade notes:
- review-gate skills B: well-specified, used successfully in gate; no automated test coverage.
- review-gate agents A: caught 2 real P1s in live gate; grounding docs strong.
- memory-store docs B: bootloader + category indexes solid; degradation path untested.
- feeder docs C: pack compile path live-verified; R2 degradation branch untested.
- feeder scripts B: mark_if_new confirmed idempotent; non-atomic rewrite noted (Minor debt).
- feeder hooks B: live-verified; injection encoding P1 fixed; no harness_lib centralization yet.
- imprint scripts B: E2E-verified; poison-entry P1 fixed; drain() not extractable yet.
- imprint hooks B: PreCompact+SessionEnd confirmed; TOCTOU race noted (Minor debt).
- dreaming docs B: feeder/dreamer docs solid; no dreaming unit tests.
- dreaming skills B: lint-terminated, live no-op verified; single-digest path only.
- dreaming agents B: T7 guard added post-gate; consolidation logic shallow (single source).
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
