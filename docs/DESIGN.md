---
status: stable
last_verified: 2026-06-18
owner: review-arch
type: methodology
tags: [design-taste, review-arch, scripts]
description: The grounding document of design taste for building harness components, used by the review-arch persona alongside ARCHITECTURE.md.
---
# DESIGN.md — taste for building harness components

Grounding document for the review-arch persona (with ARCHITECTURE.md).

## Scripts
- Pure stdlib + `harness_lib` only (the `lint_structure.py` allowlist) — a
  script never imports a sibling script. New import → justify or drop. A helper
  two scripts share is promoted to `harness_lib` under a public name, never
  cross-imported between scripts: the `plugin/scripts` analog of ARCHITECTURE.md's
  `director/` invariant 8 (`SEEDS`/`render`/`components_table` live in `harness_lib`
  so `lint_base` and `scaffold` share one source instead of importing each
  other).
- Every check function takes explicit paths (root/plugin) so tests run on
  fixtures; `main()` does the wiring. Logic-free runners (check.py) are the
  only TDD exemption.
- Lint failures: `FAIL <rule> <path>: <problem> FIX: <instruction>` — the FIX
  text is the product; write it for an agent that will act on it verbatim.
- The checked-in `base/` reference instance is **rendered, not baked**:
  `lint_base` re-renders the seed set and diffs, so markers an adopting host
  fills (`{{PROJECT}}`/`{{TODAY}}`) are preserved verbatim while machine-derived
  content (`{{COMPONENTS}}`/`{{CATEGORY}}`) is substituted; the drift-check is
  **self-host-gated** (a no-op when `base/` is absent), and `base/` lives
  outside `docs/` so the repo lints and `nav.py` never scan it.

## Host vs machine enforcement
- The plugin lints (S/D series) govern only the harness's OWN structure
  (`plugin/`, `docs/`, and the root `AGENTS.md`/`ARCHITECTURE.md` map). A host's
  app-code invariants are authored per-repo by the `architecture-setup` skill,
  routed by FORM — `.claude/lints/` (wired via `.harness.json`) for mechanical
  invariants, `.claude/skills/` guide-skills for methodology — never folded into
	  the plugin's universal lints. Our stale-date threshold (D4) is a default a
	  host overrides via `.harness.json`, not a mandate. Determinism is the cheap,
  reproducible floor; what stays per-repo is WHAT to enforce, in WHICH medium,
  and WHO authors it (ARCHITECTURE invariant 7). A universal hardcoded rule
  applied to every host is the lint-layer form of the monolithic-AGENTS.md
  anti-pattern.
- Docs governance is tiered, not global. Machine-critical docs and
  harness-managed roots (`design-docs`, `exec-plans`, `memory`,
  `product-specs`) stay strict by default because the machine reads them or the
  agent needs them to understand product intent. Host-owned
  business/marketing/research docs under `docs/` are flexible by default;
  `harness-init` should shape them into natural project-specific roots and only
  opt a root into blocking governance (`.harness.json` `managed_doc_roots` or
  `doc_governance: strict`) when the host actually wants that contract.
- Plugin component drift is self-host strict and ported-host advisory by
  default. A host that wants plugin inventory or component mention coverage to
  block commits opts in with `.harness.json` `component_inventory: strict` or
  `component_coverage: strict`.
- Gate **behavior** that is machine-universal propagates to the `harness-init` seed
  templates; host **policy** stays host-customizable. The always-on QA pair
  (spec-compliance then code-quality, run at EVERY ExecPlan completion regardless of
  `review_level`) is machine *method* — it belongs in the seed `PLANS.md`/`AGENTS.md` so
  every ported host inherits it. `review_level` and which risk personas a host dispatches
  are host *policy* (overridable). The line: a guarantee the machine makes everywhere → seed
  it; a knob the host tunes → leave it host-owned.

## Skills
- A skill owns one procedure (create/maintain/gate/garden). Knowledge
  belongs in docs/, not in SKILL.md (skills point, docs explain).
- Frontmatter description states WHEN to use it, in trigger language.
- Commit steps must narrow `git add` to the changed subtree (e.g.
  `git add docs/` for garden) — never `git add -A`. The state dir
  `.claude/harness/` is gitignored, so the guard works today, but explicit
  scoping makes the invariant written and lint-able.
- Agent/worker operating-protocol prose (the `WORKER_PROTOCOL` preamble + the dev-stage
  templates in `director/taxonomy.py`) is product text held to the same "map not
  encyclopedia" bar as a SKILL.md: stage-agnostic disciplines in the shared preamble,
  stage-specific guidance only in the template, terse throughout. Enrich it by adding a
  load-bearing discipline, never prose volume — the worker re-reads it every first turn,
  so every sentence costs tokens and attention.
- `harness-init` seed templates an agent re-reads at runtime (`PRINCIPLES.md`,
  `PRODUCT_SENSE.md`, the index guides) sit on the same token-cost footing and the same
  map-not-encyclopedia bar. They frame purpose via the **centralized consumption model by
  reference only** — a host's Director is read centrally, so a seed never assumes the host
  runs the Director locally.
- **Retiring a name = grep the surviving bodies, not just the links.** D5 catches a broken
  markdown link but not a stale prose self-reference (a §-pointer, a code comment, a
  how-to-invoke line). When you remove or rename a skill, doc, or path, grep every
  surviving doc/file body for the old name and repoint it in the same change.

## Agents (personas)
- One persona ↔ one **primary** grounding doc, 1:1 (lint S5) — additional constraint
  docs (e.g. `core-beliefs.md` for review-code-quality) or per-plan inputs (the ExecPlan /
  linked product-spec, as review-spec-compliance and review-code-quality consume) are
  allowed alongside the primary, not a violation. Personas must not invent
  taste beyond their grounding doc; gaps go to "Proposed rule additions".
  Grounding docs are **taste/contract authority**, not blinders: review personas
  may still raise demonstrable correctness, reliability, or security bugs when
  the diff, tests, or runtime evidence prove them. A P1 needs either a cited
  written rule or concrete bug evidence.
- Output contract — **review** personas (review-arch/reliability/security):
  P1 (blocks) / P2 (fix-forward) / Verdict. A **constructive** persona
  (doc-gardener) instead reports its work product (what it
  changed/authored); it doesn't emit a Verdict.
- Construction that needs the repo's FULL context is a **skill**, not a persona
  (e.g. `architecture-setup`): an isolated subagent can't read the codebase as
  deeply, and a one-time setup action doesn't need the per-commit guarantee a
  lint gives. Review wants isolation (independent judgment); setup wants the main
  agent's hands. doc-gardener remains a persona for now (bounded
  docs scope) — revisit if it outgrows it.
- Non-review personas must cite at least one `docs/` path in their body as the
  primary grounding doc; the host repo's own files (its `ARCHITECTURE.md`,
  source) are read as DATA/target input, not as taste authority over the persona.
  Secondary constraint docs (e.g. SECURITY.md) are labeled constraints, not
  primary authority.

## Hooks
- hooks.json is wiring only; all logic in scripts. Hook scripts: parse stdin
  JSON, guard headless, delegate, exit 0 (never break the user's session —
  fail open, log to state dir).
- Exception — gate hooks: a hook whose job is corrective feedback
  (tidy_stop) may exit 2 to feed FAIL/FIX lines back to the agent, but it
  must be loop-guarded (R11) and still fail open on its own errors.
