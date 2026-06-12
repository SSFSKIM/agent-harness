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
- Output contract: P1 (blocks) / P2 (fix-forward) / Verdict.
- Non-review personas must cite at least one `docs/` path in their body as the
  primary grounding doc. Secondary constraint docs (e.g. SECURITY.md) are
  allowed but should be labeled as constraints, not primary authority.

## Hooks
- hooks.json is wiring only; all logic in scripts. Hook scripts: parse stdin
  JSON, guard headless, delegate, exit 0 (never break the user's session —
  fail open, log to state dir).
- Exception — gate hooks: a hook whose job is corrective feedback
  (tidy_stop) may exit 2 to feed FAIL/FIX lines back to the agent, but it
  must be loop-guarded (R11) and still fail open on its own errors.
