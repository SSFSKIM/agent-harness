---
status: completed
last_verified: 2026-06-19
owner: harness
base_commit: fea93c187123d3c2acf324830f3e6255d1a9d925
review_level: standard
type: exec-plan
tags: [knowledge-format, navigation, graph, hierarchy, inference]
description: Build the inferred-typed-graph + nav.py tree feature from the derived-hierarchy spec — relations() over an EDGE_RULES table and a directory-independent derived-hierarchy renderer, inference-only with no frontmatter change.
---
# Derived hierarchy — inferred typed graph + `nav.py tree`

## Goal

`plugin/scripts/nav.py` gains two read-only capabilities, with no frontmatter
change: (1) `nav.py relations [--rel R] [--json]` types the existing link graph by
inferring an edge kind from each link's `(src.type, dst.type)` pair (plus the
target `status` for supersession), and (2) `nav.py tree <path>` / `nav.py tree
--type <T>` renders a derived hierarchy — an indented ASCII (or `--json`) tree built
purely from frontmatter + links, never the directory layout. Done is observable
when, on this repo, `nav.py tree --type product-spec` prints a tree whose nodes
span ≥2 different directories under one root (the "structure = projection" proof),
`nav.py relations` correctly labels the real `implements`/`refines`/`grounded-in`
edges, a deliberately-cyclic fixture does not loop, and `python3
plugin/scripts/check.py` is GREEN with new `tests/test_nav.py` coverage.

## Context

Builds the design in the product-spec
[Derived hierarchy — inferred typed graph + `nav.py tree`](../../product-specs/2026-06-19-nav-derived-hierarchy.md)
— the spec owns the design (EDGE_RULES table, direction semantics, NG list); this
plan owns the build. Prior art it extends:
- [Knowledge navigation tool (Phase 2)](../../product-specs/2026-06-18-knowledge-navigation-tool.md)
  and the existing `plugin/scripts/nav.py` — same `build_index` records (each
  already carries `path`, `type`, resolved `links`); this adds projections over them.
- [`docs/KNOWLEDGE_FORMAT.md`](../../KNOWLEDGE_FORMAT.md) §2.2/§2.3 — the `type`
  vocabulary inference reads, and the "`type` authoritative, directory is location"
  thesis this demonstrates.
- `tests/test_nav.py` — the fixture-corpus pattern (`_page`/`_fixture`) the new
  tests reuse.

Inference-only (NG-1 in the spec): no new frontmatter key, no change to
`read_frontmatter`/`harness_lib`/`build_index`. Read-only, live, no gate step.

## Approach (self-generated alternatives)

- **A — Inference computed inside `build_index`** (store a `rel` on each link at
  index time). Tradeoff: couples typing into the core record builder that lint
  shares conceptually; every consumer pays for typing even when it only wants the
  flat graph; harder to keep `build_index` a pure structural pass.
- **B — Inference as a separate projection over existing records** (`relations()`
  reads `records` and returns typed edges; `tree()` builds adjacency from
  `relations()`). Tradeoff: one extra pass over the link list, but `build_index`
  stays untouched and the typed layer is a clean, testable projection — matching how
  `catalog`/`stale`/`orphans` already sit *over* the records.
- **Chosen: B** — it mirrors the established "build_index → pure projection
  functions" shape (consistency with Phase 2), keeps the core record builder
  unchanged (lower blast radius, R1's "build_index unchanged"), and makes each
  inferred edge independently unit-testable.

## Assumptions & open questions (self-interrogation)

- Assumption: every record carries `type` from the Phase-1 backfill, but some
  (host pages, un-backfilled) may not. Handled, not assumed away: a missing/unknown
  `type` matches no rule → edge stays `links` (graceful degradation, R2). What
  breaks if wrong: nothing — untyped is the safe default.
- Assumption: the real corpus actually contains an `exec-plan→product-spec` link and
  a `*→design-doc` link so the directory-independence proof (R5) has live data. If a
  completed exec-plan's spec link resolves, this holds; verified in M2's behavioral
  check. If somehow absent, the dedicated fixture test still proves the mechanic.
- Open: default `tree` direction → resolved autonomously as **forward = what the
  page is built on (dependencies)**, `--reverse` for dependents (spec Design); not a
  taste fork.
- Open: should `documents` (page→`resource` code path) edges appear in `tree`? →
  resolved as **no** (tree walks page→page only; `relations` may list them flat) per
  spec Design — keeps the hierarchy clean.
- Open: rule-table location → **code, not config** (`EDGE_RULES` constant), per spec
  (D-56 precedent). Not escalated.

## Milestones

- **M1 — Inference layer (`relations` + `EDGE_RULES`).** Scope: add the
  `EDGE_RULES` table keyed on `(src_type, dst_type)` with the archived-target
  condition for `supersedes`, the inverse-label map for reverse traversal, and
  `relations(records, root)` returning `{src, dst, rel, basis}` per intra-corpus
  link (unmatched → `rel="links"`, `basis="untyped"`); plus the `relations [--rel R]
  [--json]` CLI subcommand and its text/JSON emitters. At the end, typed-edge
  inference exists as a pure projection and a CLI. Run: `python3
  plugin/scripts/nav.py relations --json` and `python3 -m unittest discover -s tests
  -p test_nav.py`. Expect: JSON edges with `rel`/`basis`; new `TestNavRelations`
  green (each edge type — implements/refines/supersedes/grounded-in/governed-by/
  references — plus missing-`type` → `links`).
- **M2 — Derived hierarchy (`tree`).** Scope: `tree(records, root, start, *,
  reverse, rels, max_depth)` building adjacency from `relations()` (inverted when
  `reverse`, filtered to `rels`), DFS with a visited-set (`seen` marker) and depth
  bound; `_render_tree` for indented ASCII (`├─`/`└─`/`│`, `type: slug [rel]`
  labels); the `tree <path>` and `tree --type T` subcommands with `--reverse
  --rel --json`. At the end, a directory-independent hierarchy renders from
  metadata alone. Run: `python3 plugin/scripts/nav.py tree --type product-spec` and
  the unittest. Expect: an indented forest; `TestNavTree` green incl. a cycle
  fixture that does not loop and a directory-independence assertion (root + child
  from different dirs, relation ≠ `links`).
- **M3 — Skill, behavioral proof, gate.** Scope: update
  `plugin/skills/docs-nav/SKILL.md` with the `relations`/`tree` intents + a compact
  EDGE_RULES summary + cross-links (`KNOWLEDGE_FORMAT.md`, `okf-comparison.md`);
  confirm no frontmatter/format change leaked. At the end, the feature is documented
  and the full gate is green. Run: `python3 plugin/scripts/check.py`; behavioral:
  `nav.py tree --type product-spec` on this repo. Expect: GREEN; the tree visibly
  groups pages from ≥2 directories (capture output in Progress log as the R5 proof).

## Progress log
- [x] (2026-06-19) M1 — `EDGE_RULES` + `_infer_rel` + `relations()` +
  `relations` CLI; `TestNavRelations` (each edge type + basis + missing-type → links).
- [x] (2026-06-19) M2 — `_adjacency`/`tree`/`_tree_lines` + `tree` CLI
  (`<path>`/`--type`/`--reverse`/`--rel`/`--json`); `TestNavTree` + `TestNavTreeCycle`.
- [x] (2026-06-19) M3 — `docs-nav/SKILL.md` intents + rule-table summary +
  cross-links; full gate GREEN (452 tests); behavioral R5 proof captured (one tree
  rooted in `exec-plans/` reaches `product-specs/` + `design-docs/` — 3 dirs).

## Surprises & discoveries
- **Pyright caught `root` unused** in `relations`/`_adjacency`/`tree`: the records
  already carry resolved repo-relative links, so no root/filesystem access is needed
  (unlike `drift`). Dropped the param from all three — also consistent with
  `catalog`/`orphans`/`stale` which take no root.
- **Duplicate children in the tree**: a page that markdown-links the same target
  more than once produced repeated edges → repeated (seen-marked) children. Fixed by
  collapsing `(src,dst)` in `_adjacency` (the rel is deterministic per type-pair, so
  lossless); `relations()` stays faithful one-edge-per-link.

## Decision log
- 2026-06-19: Approach B (projection over records, `build_index` untouched) — mirrors
  Phase-2 shape, lowest blast radius, per-edge testable.
- 2026-06-19: `EDGE_RULES` in code not config; default tree direction forward;
  `documents`/resource edges excluded from tree — all per spec Design.
- 2026-06-19: dropped the unused `root` param from the typed-graph functions
  (records carry resolved links); dedupe `(src,dst)` in `_adjacency` only.

## Feedback (from completion gate)
All four reviewers SATISFIED (spec-compliance + code-quality after a fix round; arch
+ reliability on the first pass).
- **spec-compliance (codex) — P1, fixed.** R7 wants every inferred edge type tested;
  the `references` (`*->knowledge`) edge was uncovered. Added a product-spec→knowledge
  fixture edge + assertion (plus an INVERSE-completeness test). Re-review → SATISFIED.
- **code-quality (codex) — P2, fixed.** The `_adjacency` `(src,dst)` dedup path had no
  regression test. Added `TestNavTreeDedup` (relations()=2 faithful edges vs tree()=1
  collapsed child). Re-review → SATISFIED.
- **reliability — P2, fixed.** `_emit_tree` could `IndexError` on an empty non-forest
  result (unreachable today, latent R12 totality gap). Guarded `trees[0] if trees else
  None`.
- **arch — P2, fixed.** `INVERSE` is a hand-maintained second vocabulary that could
  drift from `_infer_rel`; added a test asserting INVERSE covers every emittable rel.
- **Proposed rules → tech-debt-tracker** (promote-if-repeated): (a) flat edge views
  mirror the link list 1:1 while tree/adjacency views collapse to one edge per node
  pair; (b) inference/relation tables are harness taste → code, not config; (c)
  read-only nav projection emitters must be total over empty inputs (R12 spirit).

## Outcomes & retrospective
Shipped the inference-only typed graph + derived-hierarchy renderer in `nav.py` with
**no format change**: `relations()` types the link graph from `(type, type)` + status
(unmatched → untyped `links`), and `tree` renders a directory-independent hierarchy
(`forward`/`--reverse`/`--rel`/`--json`, cycle-safe, `--type` forest). Gate GREEN
(454 tests); the R5 behavioral proof holds — one tree rooted in `exec-plans/` reaches
`product-specs/` (`implements`/`refines`) and `design-docs/` (`grounded-in`), three
directories in one derived tree.
- **What went well:** Approach B (projection over existing records) kept `build_index`
  untouched and made every inferred edge unit-testable; the gate + reviews caught a
  real coverage gap (`references`) and two latent totality/drift seams.
- **Surprises:** see the Surprises section (unused `root` param; duplicate children).
- **Follow-ups:** declared/authored typed edges (KF v1.1) remain the next frontier —
  only if a query needs a relationship inference cannot supply. Acting on the
  projection (file reorg, NG-5) is the later step. Proposed rules logged to the tracker.
