---
status: stable
last_verified: 2026-06-26
owner: doc-gardener
type: methodology
tags: [quality, grading, doc-gardener]
description: The domain-by-layer quality grades from A to F that the doc-gardener updates on each gardening pass — covering both the plugin machine and the director/ host application.
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
| porting (harness-init) | - | B | B | - | - |
| host-enforcement (setter) | C | B | B | - | - |
| stop-tidy (gate) | - | B | - | - | C |

`-` = not built / not applicable for this domain-layer.
Initial grades C: works, unproven in daily use.

Grade notes:
- review-gate skills B: well-specified, used successfully in gate; no automated test coverage.
- review-gate agents A: caught 2 real P1s in live gate; grounding docs strong.
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

## director/ — host application (instance layer)

`director/` is THIS repo's self-hosting Symphony orchestrator (ARCHITECTURE "Host
runtime (`director/`) invariants"). It is instance-layer **application** code, so
the plugin-machine layers (`skills`/`agents`/`hooks`) are n/a here — `scripts` = the
Python modules, `docs` = the governing product-specs/ADRs + the ARCHITECTURE
host-runtime invariants. Its taste/review governance is graded under `review-gate` +
`taste-enforcement` above (the review personas that ground in these docs).

| Domain (director/) | docs | scripts | skills | agents | hooks |
|---|---|---|---|---|---|
| orchestration core (poll/dispatch/reconcile/daemon) | B | B | - | - | - |
| worker-runtime (app-server seam + autonomy/authority) | B | B | - | - | - |
| board adapter (Linear) | C | B | - | - | - |
| serialized merger | B | B | - | - | - |
| observability (dashboard/status/ticket-events) | B | B | - | - | - |
| lights-out autonomy (Director judge) | B | C | - | - | - |

director grade notes:
- ~611 unittest tests across the director subsystems + 11 TS app-server suites; the
  whole surface is review-gated (spec-compliance + code-quality every ExecPlan).
  `check.py` GREEN.
- orchestration core scripts B: heaviest coverage (orchestrator 111 / run 37 /
  config 78 / decider+drive+watch 34); the daemon + active-run reconciliation +
  exponential backoff shipped (`symphony-parity-gap.md` gaps #1–#3 CLOSED); exercised
  in a live dogfood run with findings tracked. Not A: live operability still thin
  (single real multi-ticket run so far).
- worker-runtime scripts B: app_server 21 + authority 31 + autonomy 8 + tools 17 +
  policy 9 (+ the TS app-server broker suites); strong app-server seam + deny-by-default
  secret boundary (exceeds Symphony §15.5).
- board adapter docs C: only the Linear adapter is built — the pluggable GitHub/local
  adapters (RV5) are not, so the "tracker-agnostic behind an adapter" promise is partial.
- serialized merger scripts B: 92 tests (merger 61 / merge_preserve 31); preservation
  tripwire + hygiene gate, hardened (`2026-06-19-merge-preservation-hardening`).
- lights-out autonomy scripts C: the `make_queue_decider` seam + the park /
  "awaiting human" marker are unit-tested, but the **Daemonized Claude Code runtime**
  that makes the human-absent deputy real is unbuilt (ADR 0003, separate track) — only
  the watched session runs live today. docs B: `DIRECTOR.md` + `PRINCIPLES.md` +
  ADR 0003 complete and fresh.

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
- 2026-06-21 (gardening): retired the `memory-store`/`feeder`/`imprint`/`dreaming`
  rows + grade notes — the feeder/imprint/dream loop was removed in packaging
  Slice 1 (`docs/logs.md`), so those domains no longer exist. Honest gap: the
  `director/` self-hosting application (the bulk of the repo today) is **not yet
  graded** here — a fuller gardening pass should add its rows. The surviving rows
  are unchanged from their last verification.
- 2026-06-26 (gardening): **closed the director/ honest gap** — added the
  `director/` host-application table (6 domain rows: orchestration core,
  worker-runtime, board adapter, serialized merger, observability, lights-out
  autonomy), grounded in ~611 director unittests + 11 TS app-server suites and the
  review-gated ExecPlan history. Mostly B (solid, shipped, review-gated); board
  adapter docs C (Linear-only, no pluggable adapters) and lights-out scripts C (the
  Daemonized Claude Code runtime is unbuilt — attended only in live use). Paired
  with the `symphony-parity-gap.md` refresh (substrate gaps #1–#5 CLOSED).
