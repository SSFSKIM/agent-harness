---
status: completed
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
- [x] M6 Completion gate: self-review + review-arch/reliability/security until
  SATISFIED (reliability r1; arch + security r2 after the P1 fixes).

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
- 2026-06-13 (gate r1): `_exempt` matches on path-segment boundaries, not bare
  `startswith` — one root cause behind both arch-P1 (sibling over-exemption)
  and security-P1 (`mem`→`memory/` guard bypass). Trailing `/` is now optional.
- 2026-06-13 (gate r1): top-level machine docs get their own non-exemptable set
  `MANAGED_DOCS` (they're not under a managed subdir, so the dir-prefix guard
  missed them).
- 2026-06-13 (gate r2 P2, fixed-now): `exempt_roots` normalizes entries
  (strip `./`, `//`, `.` segments) before the drop-guard so both enforcement
  layers agree on `./memory`-style inputs (was inert via `_exempt`, now also
  dropped at source).

## Feedback (from completion gate)
- **review-reliability: SATISFIED** (round 1). Empirically verified fail-open
  on every bad input (missing/dir/perm/non-UTF8/BOM/CRLF/whitespace/`.`/`..`/`/`),
  no gate crash, scaffold idempotent, deterministic. Flagged the substring
  footgun as accept-as-is; security escalated it — see below.
- **review-arch: CHANGES REQUESTED** (round 1) → both P1s fixed:
  - P1 prefix collision: `_exempt` used bare `startswith` → entry `business`
    matched `business-plan.md`. FIXED: segment-boundary match in `_exempt`
    (`rel == x or rel.startswith(x.rstrip('/')+'/')`). Trailing slash now
    optional/forgiving. Test: slashless_entry_is_segment_matched.
  - P1 top-level grounding docs exemptable: `MANAGED_ROOTS` covered only
    subdirs. FIXED: `MANAGED_DOCS` added; `exempt_roots` drops those entries.
    Test: cannot_exempt_top_level_machine_doc.
- **review-security: CHANGES REQUESTED** (round 1) → both P1s fixed (same
  root cause):
  - P1 `mem` bypassed the managed-root guard (segment-equality guard vs
    substring `_exempt`) → could reach `memory/…` and, with a one-line index
    edit (D8) + the feeder reading by content, inject a poisoned page on a
    GREEN gate. FIXED by the segment-match in `_exempt` (a partial prefix can
    no longer reach `memory/…`). Test: partial_prefix_cannot_bypass_managed_guard.
  - P1 grounding docs exemptable: same fix as arch P1.
  - P2 T8 overclaimed ("feeder's structural checks" don't exist). FIXED: T8
    reworded to credit only D8 + content lints, and to name MANAGED_DOCS.
  - P2 imprint child has unscoped Write (pre-existing T1/T2): a transcript
    injection could write `docs/.harnessignore`. Logged as an Important
    tracker row (path-scope imprint writes to docs/memory/); T8 now notes the
    Tier-0 framing depends on the T1 guard.
- Post-fix: 60 tests green (+3 boundary tests); host PoC still 0 legacy fails
  under segment matching; self-host gate GREEN.

## Outcomes & retrospective
Shipped: `docs/.harnessignore` lets a doc-heavy host scope which `docs/` the
content lints govern — govern-by-default preserved, harness-managed trees and
top-level machine docs non-exemptable, segment-boundary matching. 61 tests
green (+6 over the plan's life). The real Lingual host went from 74 legacy
D3/D6/D7 failures to 0 by declaring 4 subtrees + 3 root docs — the lint-scoping
blocker to adoption is closed.

Retrospective:
- The gate paid off a THIRD consecutive time: two personas independently
  converged on one root cause (substring vs segment match) that self-review +
  57 green tests missed, and security caught that the change could exempt its
  OWN grounding doc — a self-referential hole. The fixture (fresh empty host)
  is structurally blind to this entire class; only the real port surfaced it.
- Methodology lesson: "demonstrably working" must be tested at the boundary,
  not the center. The first round's 5 tests all used well-formed slash-dir
  entries and passed while both P1s sat undetected. Boundary/negative tests
  (slashless, partial-prefix, machine-doc, dotslash) are where the value was.
- This is the harness improving itself from a real adoption attempt — the
  intended compounding loop. The fix is general (no Lingual-specific code); the
  next doc-heavy host adopts with a `.harnessignore` and a GREEN gate.

Follow-on (not this plan): complete the actual Lingual port — scaffold, merge
the existing 6KB AGENTS.md + 12KB CLAUDE.md, write the real `.harnessignore`,
migrate/triage docs in waves, author instance verify/boot skills for the
Firebase+Python+frontend app, gate GREEN, commit to the host. The threshold-
VALUE tuning + HARNESS_LINT_CMD (G3) remain open tracker items.
