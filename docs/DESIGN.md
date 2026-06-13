---
status: stable
last_verified: 2026-06-12
owner: review-arch
---
# DESIGN.md — taste for building harness components

Grounding document for the review-arch persona (with ARCHITECTURE.md).

## Scripts
- Pure stdlib; allowlist in lint_structure.py. New import → justify or drop.
- Every check function takes explicit paths (root/plugin) so tests run on
  fixtures; `main()` does the wiring. Logic-free runners (check.py) are the
  only TDD exemption.
- Lint failures: `FAIL <rule> <path>: <problem> FIX: <instruction>` — the FIX
  text is the product; write it for an agent that will act on it verbatim.

## Host vs machine enforcement
- The plugin lints (S/D series) govern only the harness's OWN structure
  (`plugin/`, `docs/`, and the root `AGENTS.md`/`ARCHITECTURE.md` map). A host's
  app-code invariants are authored per-repo by the `architecture-setup` skill,
  routed by FORM — `.claude/lints/` (wired via `.harness.json`) for mechanical
  invariants, `.claude/skills/` guide-skills for methodology — never folded into
  the plugin's universal lints. Our thresholds (D1/D7/D4) are defaults a host
  overrides via `.harness.json`, not mandates. Determinism is the cheap,
  reproducible floor; what stays per-repo is WHAT to enforce, in WHICH medium,
  and WHO authors it (ARCHITECTURE invariant 7). A universal hardcoded rule
  applied to every host is the lint-layer form of the monolithic-AGENTS.md
  anti-pattern.
- Docs governance is tiered, not global. Machine-critical docs and
  harness-managed roots (`design-docs`, `exec-plans`, `memory`) stay strict by
  default because the machine reads them. Host-owned business/product/research
  docs under `docs/` are flexible by default; `harness-init` should shape them
  into natural project-specific roots and only opt a root into blocking
  governance (`.harness.json` `managed_doc_roots` or `doc_governance: strict`)
  when the host actually wants that contract.
- Plugin component drift is self-host strict and ported-host advisory by
  default. A host that wants plugin inventory or component mention coverage to
  block commits opts in with `.harness.json` `component_inventory: strict` or
  `component_coverage: strict`.

## Skills
- A skill owns one procedure (create/maintain/gate/dream/garden). Knowledge
  belongs in docs/, not in SKILL.md (skills point, docs explain).
- Frontmatter description states WHEN to use it, in trigger language.
- Commit steps must narrow `git add` to the changed subtree (e.g.
  `git add docs/memory/` for dream, `git add docs/` for garden) — never
  `git add -A`. The state dir `.claude/harness/` is gitignored, so the guard
  works today, but explicit scoping makes the invariant written and lint-able.

## Agents (personas)
- One persona ↔ one grounding doc, 1:1 (lint S5). Personas must not invent
  taste beyond their grounding doc; gaps go to "Proposed rule additions".
  Grounding docs are **taste/contract authority**, not blinders: review personas
  may still raise demonstrable correctness, reliability, or security bugs when
  the diff, tests, or runtime evidence prove them. A P1 needs either a cited
  written rule or concrete bug evidence.
- Output contract — **review** personas (review-arch/reliability/security):
  P1 (blocks) / P2 (fix-forward) / Verdict. **Constructive** personas
  (doc-gardener, dreamer) instead report their work product (what they
  changed/authored); they don't emit a Verdict.
- Construction that needs the repo's FULL context is a **skill**, not a persona
  (e.g. `architecture-setup`): an isolated subagent can't read the codebase as
  deeply, and a one-time setup action doesn't need the per-commit guarantee a
  lint gives. Review wants isolation (independent judgment); setup wants the main
  agent's hands. doc-gardener/dreamer remain personas for now (bounded
  memory/docs scope) — revisit if they outgrow it.
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
