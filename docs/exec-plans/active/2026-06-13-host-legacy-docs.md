---
status: active
last_verified: 2026-06-13
owner: harness
base_commit: ae0e7cf7b9cf6987225412f41146ec51b26101a2
---
# Host legacy-doc exemption (`docs/.harnessignore`)

## Goal
A doc-heavy host repo can adopt the harness and reach a GREEN gate without
force-migrating its pre-existing `docs/` content. Demonstrable: pointing the
fixed `lint_docs.py` at the real Lingual-Project host with its four legacy
doc roots declared in `docs/.harnessignore` drops the 74 legacy D3/D6/D7
failures to 0, while a frontmatter-less doc OUTSIDE the declared roots still
FAILs (govern-by-default preserved) and an entry naming a harness-managed
root (`memory/`, `design-docs/`, …) has no exempting effect.

## Context
First real port (Lingual-Project, `~/Documents/GitHub/Lingual-U/Lingual-Project`)
exposed the hole: `lint_docs.py` treats ALL of `docs/` as harness-owned and
enforces D3 (frontmatter), D6 (kebab-case), D7 (size) on every `*.md`. A real
host already uses `docs/` for human-curated trees (`business/` 28 fails,
`school-integration/` 36, `Pedagogy Research/` 5, plus root docs) with their
own deliberate conventions (UPPERCASE specs, spaced research titles). The
gate is unpassable on adoption — and force-renaming/reframing those files is
exactly the over-specific vandalism portability must avoid. The skill already
says "migrate in waves: gate first, remaining docs as tech-debt" but no
mechanism implements the wave boundary.

Measured surface (plugin lint_docs against the unmodified host):
44 D3 + 20 D6 + 10 D7 = 74 legacy fails; +11 D9 (pre-AGENTS-merge) +8 D10
(pre-scaffold) = 93 total. The 74 are the portability blocker.

Design: `docs/.harnessignore` — versioned, docs-relative path prefixes the
content lints skip (dir entries end `/`; bare filenames match one file).
`#` comments, blanks ignored. Absent → () → fresh-host behavior unchanged
(backward compatible). The list is a **migration backlog**: it shrinks as
legacy docs move into the convention. Govern-by-default holds — nothing is
skipped unless the host declares it. Harness-managed roots (`design-docs/`,
`memory/`, `exec-plans/`, `product-specs/`, `references/`, `generated/`)
CANNOT be exempted (the harness always governs its own tree) — `exempt_roots`
drops such entries so a host cannot un-govern the memory tree.

## Milestones
- [x] M1 `harness_lib.exempt_roots(root)` reads `docs/.harnessignore`, strips
  comments/blanks, drops harness-managed-root entries. Unit tests.
- [x] M2 `lint_docs` D3/D4/D5/D6/D7 honor host exemptions (thread `host`
  param, default `()`); main() computes it once. Tests: exempt root silences
  D3/D6/D7; non-listed doc still fails; managed-root entry is a no-op.
- [x] M3 `scaffold.py` seeds `docs/.harnessignore` (new template, empty +
  explanatory comments), idempotent. Tests: seeded, fresh host still GREEN.
- [x] M4 Wiring/docs: harness-init step (declare legacy roots = backlog),
  `agent-harness.md` template pointer, ARCHITECTURE invariant + SECURITY note
  (exemption scope is content-lints only; managed tree non-exemptable),
  tech-debt row resolution.
- [x] M5 PoC against the real host: temp `docs/.harnessignore` with the four
  roots → host lint_docs legacy fails 74 → 0; remove temp file. (No host
  writes committed in this plan; the full port is the follow-on.)
- [ ] M6 Completion gate: self-review + review-arch/reliability/security until
  SATISFIED.

## Progress log
- 2026-06-13: plan created from the Lingual port-attempt evidence.
- 2026-06-13: M1-M3 implemented; 57 tests green (+5). M4 wired (skill step,
  template pointer, ARCHITECTURE invariant 6, SECURITY T8, tracker partial).
- 2026-06-13: M5 PoC on real Lingual host — declaring 4 legacy roots + 3 root
  docs dropped legacy D3/D6/D7 from 74 → 0; the residual 19 (11 D9 + 8 D10)
  are scaffold/merge work, not legacy-doc fails. Temp file removed; host
  untouched.

## Surprises & discoveries
- The host already had `docs/superpowers/` — a tree the built-in `FM_EXEMPT`
  already exempts. The design anticipated per-tree exemption; this plan just
  generalized the hardcoded pair into host-declarable config.
- D9 (component coverage) and D10 (machine docs) also fire on a bare host, but
  those are *adoption* steps (AGENTS.md merge + scaffold), not the legacy-doc
  blocker — cleanly separable from the lint-scoping fix.

## Decision log
- 2026-06-13: exemption list (skip-list, govern-by-default) over managed-roots
  (allow-list) — preserves the blog's "docs/ is governed" philosophy; a host
  dropping a new ungoverned doc still gets linted. The shrinking skip-list is
  the visible migration backlog.
- 2026-06-13: file at `docs/.harnessignore` (not repo root) so entries being
  docs-relative is self-evident from location, matching the existing
  `FM_EXEMPT` entries (`generated/`, `superpowers/`).
- 2026-06-13: managed roots are non-exemptable (defense in depth) so
  `.harnessignore` can never be used to hide an unindexed/poisoned page in the
  harness's own memory/design tree.

## Feedback (from completion gate)

## Outcomes & retrospective
