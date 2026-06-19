---
status: active
last_verified: 2026-06-19
owner: harness
base_commit: 4f34d15d3f2a1d36297533695ba1bd31392f0c54
review_level: standard
phase: knowledge-format/05-map-depth
---
# Map depth — declared pivots + follow-up drill-down — build

## Goal

Ship the two depth layers from
[the spec](../../product-specs/2026-06-19-map-depth-pivots-followups.md): **③** a
declared `supersedes` frontmatter key (KF v1.2) that nav surfaces inline as a
pivot (`[superseded-by …]`), and **②** a `nav.py followups` drill-down over the
tech-debt-tracker plus a `[N follow-ups]` count badge on `nav.py map`. Done =
declaring `supersedes:` lights up a pivot in roadmap/map; `nav.py followups`
groups tracker rows by source node; `map` shows count badges and stays
skeleton-readable; gate GREEN.

## Context

- Spec (owns the design): `docs/product-specs/2026-06-19-map-depth-pivots-followups.md`.
- Builds directly on the charter slice: `plugin/scripts/nav.py` (`relations`,
  `roadmap`, `charter_map`, `_infer_rel` supersedes, `EDGE_RULES`/`INVERSE`).
- KF format: `docs/KNOWLEDGE_FORMAT.md` + host variant
  `plugin/skills/harness-init/templates/knowledge-format.md` (same semantic bump).
- Tracker to parse + backfill: `docs/exec-plans/tech-debt-tracker.md`.

## Approach (self-generated alternatives)

- ③ A: declared `supersedes` key parsed into an edge (additive to inferred). — one
  bounded declared key, deduped by existing `_adjacency`; matches the
  pivot-is-supersession decision.
- ③ B: a general declared-relationship system (`relates: [{rel,target}]`). —
  rejected, NG3: over-broad, re-opens the whole declared-edge surface.
- ② A: a `followups` query that parses the tracker table + a count badge on map.
  — keeps follow-ups as the drill-down layer; only a sparse count in the overview.
- ② B: turn tracker rows into pages so they join the page link graph. — rejected,
  NG4: heavy restructure for a high-churn list.
- Chosen: ③A + ②A (the volatility principle from the spec).

## Assumptions & open questions

- Assumption: `read_frontmatter` reads `supersedes` as scalar or list (it is
  list-aware) — no parser change.
- Assumption: the tracker is a single markdown table; rows are `|`-delimited and
  the Source cell is column 4. A row with no `.md` link in Source → `(unsourced)`.
- Open: declared vs inferred supersedes collision → resolved: both emit a
  `supersedes` edge; `_adjacency` already dedupes `(src,dst)`, and `relations()`
  may list both (faithful) — acceptable (basis distinguishes them).
- Open: which real supersessions to declare → resolved autonomously by scanning
  for genuine spec-level replacements; if none are truly supersessions (vs
  refinements), declare none and note it (the mechanism still stands).

## Milestones

- **M1 — ③ declared `supersedes` (KF v1.2 + nav).** Add `supersedes` to
  KNOWLEDGE_FORMAT §2.2 + host template; bump §6 to v1.2. `build_index` records
  `supersedes`; `relations()` emits a declared `supersedes` edge per resolved
  target (basis `declared`), additive to inferred. At the end: a fixture page
  declaring `supersedes:` yields the edge + inline `[superseded-by]`; run the gate;
  expect GREEN.
- **M2 — ② `nav.py followups` + map badge.** `followups(records, node=None)` parses
  the tracker table → `{source: [rows]}` (+ `(unsourced)`), CLI + `--json`,
  fail-soft. `charter_map`/`_emit_map` add a `[N follow-ups]` count badge per node.
  `docs-nav` SKILL documents both. At the end: `followups` groups rows, `map` shows
  badges; tests pass; gate GREEN.
- **M3 — dogfood + tracker convention.** Document the Source-link convention in the
  tracker header; backfill identifiable rows with a source `.md` link; declare any
  genuine `supersedes`. At the end: `nav.py followups` resolves ≥3 real rows and
  `nav.py map` shows real badges; gate GREEN.

## Progress log
- [x] (2026-06-19) M1 — KF v1.2 `supersedes` declared key (both KF docs);
  `build_index` resolves it, `relations()` emits a `supersedes` edge (basis
  `declared`) that wins over the inferred edge for the same pair. Verified: a
  declaring page yields exactly one `supersedes/declared` edge + inline pivot.
- [x] (2026-06-19) M2 — `nav.py followups [<node>]` (tracker table parser, grouped
  by source node, `(unsourced)` bucket, `--json`, fail-soft) + `[N follow-ups]`
  count badge on `nav.py map`. `docs-nav` SKILL documents both.
- [x] (2026-06-19) M3 — tracker Source-link convention documented + 5
  knowledge-format-slice sources backfilled; `followups` resolves them, `map`
  badges the plans. `supersedes`: declared nowhere (see Surprises).

## Surprises & discoveries
- **③ has no real data to show — honestly.** Scanning the corpus, there is **no
  genuine spec-level supersession** (it evolves by *refinement*, not replacement;
  the one conceptual reframe, ADR 0003 vs 0002, is between ADRs, not roadmap-tier
  pages). So `supersedes` is declared on zero real pages — the *mechanism* is
  delivered + tested (fixture), but the dogfood pivot view is correctly empty.
  Same shape as the charter slice's pivot finding: this project's evolution is
  refinement-heavy, supersession-light.
- **② the (unsourced) bucket is 66/77 rows** — historical tracker rows written
  before the Source-link convention. Backfilled only the 5 cleanly-identifiable
  knowledge-format-slice sources; bulk-linking the historical rows is doc-gardener
  work, not this scope (recorded, not done).

## Decision log
- 2026-06-19: declared edges limited to `supersedes` only (NG3) — the one genuine
  pivot; a general declared-relationship system stays a future KF minor.
- 2026-06-19: follow-ups surface as a count badge in the overview + a `followups`
  drill-down, never inlined rows (volatility principle; avoids the pivot-flood).

## Feedback (from completion gate)

## Outcomes & retrospective
