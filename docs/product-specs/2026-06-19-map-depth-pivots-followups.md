---
status: stable
last_verified: 2026-06-19
owner: harness
phase: knowledge-format/05-map-depth
type: product-spec
tags: [knowledge-format, nav, roadmap, pivots, tech-debt]
description: Two depth layers on the charter-rooted map — declared `supersedes` pivots surfaced inline (sparse, load-bearing) and a follow-up drill-down (`nav.py followups` + a count badge on the map) for the high-volume tech-debt tier.
---
# Map depth — declared pivots + follow-up drill-down

## Problem

The charter-rooted `nav.py map` (the [charter & progress-map](2026-06-19-charter-and-progress-map.md)
slice) gives the Big Picture → initiatives → phases → specs/plans overview. Two
layers the relationship picture still needs are missing or empty:

1. **Pivots (③)** render inline (`[superseded-by …]`) but only *inferred*
   archived-supersession is detected — **0 in the corpus**. A genuine design
   pivot (a spec that replaced another) lives in prose, invisible to the map.
2. **Follow-ups (②)** — derived work / tech-debt — live in a flat
   `tech-debt-tracker.md` table with **0 graph edges**. "What did task X spawn?"
   is unanswerable from the map.

The agreed architecture is the **volatility principle**: *inline what is sparse
and load-bearing (pivots); drill-down what is high-volume and contextual
(follow-ups).* Inlining every follow-up would re-create the pivot-flood the
charter slice fixed; so pivots go in the overview, follow-ups go behind a query
with only a count badge surfacing in the overview.

## Requirements

- **R1 — Declared pivots (③).** KF gains one optional key, `supersedes` (a
  repo-relative `.md` path, or a list of them) — a **declared** supersession
  edge. `nav.relations()` emits a `supersedes` edge for each declared target, *in
  addition to* the inferred archived-supersession. The map/roadmap pivot
  annotation (already supersedes-only) surfaces it inline automatically, with
  `basis: declared`. Lint stays permissive (D3 unchanged). KF bumps to **v1.2**.
  Verifiable: a page declaring `supersedes: x.md` makes `relations --rel supersedes`
  emit that edge and the roadmap annotate the target `[superseded-by …]`.
- **R2 — Follow-up query (②).** `nav.py followups [<node>]` parses the
  `tech-debt-tracker.md` table, extracts each row's **source** (a `.md` link in
  the Source cell) resolved to a repo path, and groups rows by source node. With
  `<node>`, lists that node's follow-ups; without, the full grouping. Rows with no
  source link → an advisory `(unsourced)` group. `--json`. Fail-soft: no tracker /
  malformed rows degrade, never raise. Verifiable: `followups <plan>` lists the
  tracker rows citing that plan.
- **R3 — Count badge in the overview (②).** `nav.py map` annotates a node with a
  `[N follow-ups]` badge when N>0 — the sparse glanceable signal; the rows
  themselves stay behind `followups <node>` (NOT inlined — that is the flood we
  avoid). Verifiable: a node with tracker rows shows the badge; the map stays
  skeleton-readable.
- **R4 — Tracker source convention.** The tracker's **Source** column links the
  originating plan/spec (`.md` link); documented in the tracker header. Backfill
  the rows whose source is cleanly identifiable. Verifiable: tracker header states
  the convention; `followups` resolves the backfilled rows.
- **R5 — Dogfood.** Declare any genuine spec-level supersession via `supersedes:`
  (honest — there may be few); backfill tracker source links; `nav.py followups`
  and `nav.py map` (with badges) render real data.
- **R6 — Portability (belief 13).** `supersedes` ships via `KNOWLEDGE_FORMAT.md`
  (+ host template, same-semantics variant); `followups` + the map badge live in
  `plugin/scripts/nav.py`; no self-host paths.

## Design

**Components & changes**

| Artifact | Change |
|---|---|
| `docs/KNOWLEDGE_FORMAT.md` (+ host template) | Add `supersedes` to §2.2 (routing/binding); bump §6 to **v1.2** ("first declared edge; only supersession, the genuine pivot"). |
| `plugin/scripts/nav.py` | `relations()` emits declared `supersedes` from the `supersedes` frontmatter key (basis `declared`), additive to inferred; `build_index` records `supersedes`. New `followups(records, node=None)` (tracker table parser) + `_emit_followups` + CLI `followups`. `charter_map`/`_emit_map` add a per-node follow-up **count** badge. |
| `docs/exec-plans/tech-debt-tracker.md` | Header documents the Source-link convention; backfill identifiable rows with a source `.md` link. |
| `plugin/skills/docs-nav/SKILL.md` | Document `followups` + the map badge. |
| `tests/test_nav.py` | declared-supersedes edge; followups grouping + unsourced + fail-soft; map badge count. |

**Contracts**

- `supersedes` value: a repo-relative `.md` path or a list; resolved like a link
  (page dir then root); an unresolvable target is skipped (fail-soft), never an
  error. Declared `supersedes` edges are deduped against inferred ones by the
  existing `_adjacency` `(src,dst)` collapse.
- `followups` parses table rows (`|`-split), reads the Source cell, extracts the
  first `.md` markdown link, resolves it; the follow-up record is
  `{source, summary (Item, truncated), severity, status}`. Pure read, nothing
  persisted.
- map badge: `charter_map` counts followups per node path; `_emit_map` appends
  `  [N follow-ups]` to a row when N>0. Count only — no row text in the overview.

## Non-goals

- **NG1 — No enforcement.** `supersedes` and the Source-link convention are never
  a gate (permissive/advisory).
- **NG2 — Follow-ups are not inlined as rows in the map.** Only a count badge; the
  rows live behind `followups` (the volatility principle — avoid the flood).
- **NG3 — No general declared-relationship system.** R1 adds exactly one declared
  key, `supersedes` (the genuine pivot). Other declared edge types remain a future
  KF minor.
- **NG4 — No tracker restructure into pages.** The tracker stays a markdown table,
  parsed in place; rows do not become individual pages.
- **NG5 — No viz.html / visual graph.** Agent-facing text + JSON only (the
  human-glance rendering, gap ④, stays deferred).

## Acceptance criteria

1. KF v1.2 documents `supersedes` in both the canonical and host KF docs; lint
   permissive; a page declaring it produces a `supersedes` edge
   (`relations --rel supersedes`, basis `declared`) and an inline `[superseded-by …]`
   on the target in `roadmap`/`map`.
2. `python3 plugin/scripts/nav.py followups` groups tracker rows by source node;
   `followups <node>` filters; unsourced rows bucketed; `--json` validates;
   no-tracker/malformed is fail-soft.
3. `python3 plugin/scripts/nav.py map` shows `[N follow-ups]` badges on nodes with
   tracker rows and stays skeleton-readable (rows not inlined).
4. The tracker header documents the Source-link convention; ≥3 real rows backfilled
   and resolved by `followups`.
5. Full gate (`python3 plugin/scripts/check.py`) GREEN; new tests pass.
