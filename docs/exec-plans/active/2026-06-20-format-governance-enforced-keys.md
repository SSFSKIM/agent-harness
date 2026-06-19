---
status: active
last_verified: 2026-06-20
owner: harness
type: exec-plan
phase: knowledge-format/06-enforced-keys
base_commit: dbce828a171196d7bce928536bc1650a26e4fc9b
review_level: standard
description: Build the KF v2.0 governance flip — D11/D12 lint rules escalating type/description/spec-phase to checked rules + validate-if-present for resource/supersedes/phase, with the docs and template conformance.
---
# Format governance — enforced navigation keys (KF v2.0) — build

## Goal

Implement [the spec](../../product-specs/2026-06-20-format-governance-enforced-keys.md):
escalate the load-bearing navigation keys from permissive to checked lint rules —
`type` + `description` blanket-required, `phase` required on `product-spec`, and
`resource`/`supersedes`/`phase` validated-if-present — bump KF to v2.0, and keep
the gate GREEN corpus-wide (migration = backfill the 2 missing descriptions). Done
= a governed page missing `type`/`description`, or a `product-spec` missing
`phase`, or a malformed `resource`/`supersedes`/`phase`, FAILs `check.py`; the live
corpus is GREEN; rules ship in `plugin/scripts/lint_docs.py` (portable).

## Context

- Spec (owns the design): `docs/product-specs/2026-06-20-format-governance-enforced-keys.md`.
- The lint to extend: `plugin/scripts/lint_docs.py` — `check_frontmatter` already
  iterates governed pages with parsed `fm` (D3/D4 live there); the D5 resolver
  pattern (`(p.parent/t).exists() or (root/t).exists()`) is reused for
  resource/supersedes.
- Format docs (KF v1.2 → v2.0): `docs/KNOWLEDGE_FORMAT.md` + host variant
  `plugin/skills/harness-init/templates/knowledge-format.md` (same semantic bump).
- Verified: all 30 existing phases match the canonical grammar; type 99/99,
  spec-phase 29/29 → only 2 `description`s need backfill.

## Approach (self-generated alternatives)

- A: add D11 (required nav keys) + D12 (validate-if-present) inside the existing
  `check_frontmatter` loop — reuses the governed-page scope + parsed `fm`, one
  pass, distinct rule numbers so failures read clearly. Chosen.
- B: a separate `check_navigation()` function — cleaner separation but re-walks the
  tree + re-parses frontmatter (duplicate I/O) for no real benefit.
- Chosen: A.

## Assumptions & open questions

- Assumption: D11/D12 run on the same `_governed_doc` scope as D3 (so relaxed hosts
  govern their managed roots; fresh hosts stay GREEN because the templates emit
  type/description/spec-phase). Breaks nothing — `tests/test_scaffold.py` guards it.
- Decision (recorded): `phase` required on `product-spec` only, NOT `exec-plan`
  (plans inherit via the `implements` edge; requiring it on 45 plans is redundant +
  a 44-page backfill). Confirmed with the human against the measured cost.
- Open: phase grammar strictness → resolved as `^[a-z0-9][a-z0-9-]*(/[0-9]+-[a-z0-9-]+)?$`
  (verified: every existing phase matches; nav's looser tolerance still degrades
  gracefully, the lint is the canonical form).

## Milestones

- **M1 — lint rules + tests.** Add to `check_frontmatter`: D11 (type +
  description present/non-empty; product-spec ⇒ phase present) and D12
  (resource path exists if a non-URL repo path; each supersedes target resolves;
  phase well-formed if present). Extend `tests/test_lint_docs.py`. At the end:
  the new tests pass and a crafted bad page FAILs each rule; run
  `python3 -m pytest tests/test_lint_docs.py`; expect green (rules fire correctly).
- **M2 — KF v2.0 docs.** `docs/KNOWLEDGE_FORMAT.md` + host template: move
  `type`/`description` to §2.1 required, document conditional spec-`phase` +
  validate-if-present in §2.2/§5, add D11/D12 to the conformance table, bump §6 to
  v2.0, reframe the §intro asymmetry + §7 OKF divergence (general exchange vs
  enforced single-actor memory). At the end: both docs read v2.0 coherently.
- **M3 — migration + GREEN.** Backfill `description` on the 2 plans lacking it
  (metadata-only, no `last_verified` bump). At the end: `python3
  plugin/scripts/check.py` GREEN on the full corpus; `tests/test_scaffold.py`
  (fresh host GREEN) passes.

## Progress log
- [x] (2026-06-20) M1 — D11 (type+description blanket, phase on product-spec) +
  D12 (resource exists / supersedes resolves / phase well-formed) in
  `check_frontmatter`; reserved spines exempt; 6 tests in `TestLintNavKeys`.
- [x] (2026-06-20) M2 — KF v2.0 in both KNOWLEDGE_FORMAT docs (§2.1 required gains
  type/description, §2.2 split into optional + validate-if-present, §5 +D11/D12,
  §6 v2.0, §7 OKF-divergence reframe); stale "optional type" guidance fixed.
- [x] (2026-06-20) M3 — migration: 2 plan `description`s (+ the ExecPlan-template
  `description:` placeholder) + 10 seeded-template
  type/description backfills + ExecPlan/product-design authoring guidance; fresh
  scaffold lints GREEN; full gate GREEN.

## Surprises & discoveries
- **Migration was bigger than "2 descriptions" — but the tool told me where.** My
  estimate used `nav catalog` (which excludes `index.md` spines); the *lint*
  governs spines. Running the new rule surfaced 7 `index.md` files with no
  type/description. Forcing `type` on a listing is wrong → **exempted reserved
  spines** (index.md/MEMORY.md) from D11/D12, consistent with nav's `RESERVED` and
  the catalog-scoped 99/99 the spec measured. The spec's R1/R2 wording was
  refined to "governed *content* page".
- **The contract didn't self-apply to ported hosts until the templates did.** A
  fresh scaffold would have FAILed D11 — most seeded templates
  (`reliability.md`, `design-md.md`, `core-beliefs.md`, …) carried no
  type/description. Backfilled 10 templates so a ported host is GREEN by
  construction (belief 13). Same class as the earlier ExecPlan-template `type`
  gap: a new required key must be added to every template that emits the doc, or
  the gate is self-host-only.
- **Test fixture had to move with the contract.** `fixtures.fm()` emitted no
  type/description → it now defaults them (+ optional `phase`), or every existing
  lint test that writes a content page would fail D11.

## Decision log
- 2026-06-20: `phase` required on `product-spec` only (not exec-plan) — plans
  inherit via `implements`; data showed spec=0/plan=44 backfill. Human-confirmed.
- 2026-06-20: `type` value stays free (presence-only) — keep OKF tolerate-unknown
  for values; enforce only presence (spec NG1).

## Feedback (from completion gate)

Reviews — all SATISFIED: review-spec-compliance, review-arch, review-reliability
(the dedicated personas; used over Codex per the CLAUDE.md fallback after Codex
stalled earlier this session). review-code-quality below.

P2s fixed inline:
- (arch) `docs/design-docs/agent-harness.md` had a same-doc version contradiction
  my diff introduced (one line v2.0, another still "(KF v1.0)") → both v2.0.
- (spec-compliance) spec acceptance #1 + plan progress wording said "governed
  page" / "3 plan descriptions" → "governed *content* page" / "2 plan descriptions
  (+ the ExecPlan-template placeholder)".

Promoted: **RELIABILITY R22** — the commit-gate lint (`lint_docs.py`) is total
over a hostile corpus (R21's higher-stakes sibling: a lint crash blocks commits).
Third instance of the pattern (D4 list-degradation → D11 `isinstance` guards →
D12 path/grammar totality), so promoted rather than tracked.

Recorded in `tech-debt-tracker.md` (non-blocking): one shared path-resolver helper
(D5/D11/D12 re-inline the pattern — review-arch); D12 list-valued `resource`/`phase`
under-enforcement vs D11 (benign/fail-soft — review-reliability observation).

## Outcomes & retrospective
