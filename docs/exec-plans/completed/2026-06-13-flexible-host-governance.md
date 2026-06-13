---
status: completed
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
- Completion gate run during PR #1 review (`review_level: standard` + security,
  because the diff touches the live exec surface `plugin/scripts/*`), diff
  `master..HEAD`. Codex was rate-limited, so the standard+security pass was
  performed by Claude (Opus 4.8) per the CLAUDE.md fallback, tracing the code
  paths empirically (not just reading). **Verdict: SATISFIED.**
- Highest-stakes check (poisoning vector): a hostile relaxed host (`.harness.json`
  relaxing every key + `.harnessignore` listing the managed core) CANNOT
  un-govern `docs/memory|design-docs|exec-plans/**` or the top-level machine
  docs — `_managed_roots` is append-only, `_machine_doc` is mode-independent,
  `exempt_roots` drops MANAGED_ROOTS/MANAGED_DOC entries (incl. normalized
  `./memory`). Relaxed path crash-free. No P1.
- P2 (fixed in this PR): `lint_docs.py` `HOST_MANAGED_ROOTS` vs `hl.MANAGED_ROOTS`
  "generated" divergence → added a clarifying comment so a future edit won't
  "reconcile" the deliberate one-element difference.
- Rejected finding: a reported P2 about an `sd = min(sd, STALE_DAYS)` stale-days
  clamp at `lint_docs.py:143` — that code does not exist; the real tighten-only
  clamp is the *size* clamp at L~199 and is already clear. (Verify findings, do
  not obey them.)
- Pyright (not part of the gate): "harness_lib unresolved" is a runtime-sys.path
  false positive; "append str to Literal list" in `_managed_roots` is narrow
  type inference, not a runtime bug (the gate's 89 tests append and pass). Left
  as-is — out of P2 scope, no runtime impact.
- Proposed rule additions (deferred, non-blocking): (1) DESIGN.md note that a
  bug-evidence P1 must cite a reproducing diff/test/runtime trace, not a
  hypothetical; (2) a RELIABILITY rule that an advisory check must emit a visible
  SKIP, never silently no-op.

## Outcomes & retrospective
- Shipped tiered docs governance: machine-critical docs + managed roots
  (`memory`/`design-docs`/`exec-plans`) stay strict in both modes; host-owned
  business/product/research docs are flexible on ported hosts unless opted in
  (`managed_doc_roots` / `doc_governance: strict`). Component inventory/coverage
  is self-host strict, ported-host advisory. Review cost is risk-budgeted
  (`review_level`), and personas may flag evidence-backed bugs beyond their
  grounding doc. The self-host repo stays the strict reference implementation.
- Gate closed at PR #1 review: SATISFIED, one P2 fixed, one reported P2 rejected
  on verification, two proposed rule additions deferred. Bundled into PR #1 with
  the front-loading self-gates plan and merged to master.
