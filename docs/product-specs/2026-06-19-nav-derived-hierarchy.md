---
status: stable
last_verified: 2026-06-19
owner: harness
phase: knowledge-format/03-derived-hierarchy
type: product-spec
tags: [knowledge-format, navigation, graph, hierarchy, inference, tooling]
description: A directory-independent navigation layer in nav.py that infers typed relationships from existing (type, type, link-direction) metadata — no new frontmatter — and renders a derived hierarchy tree, demonstrating that corpus structure is a projection of metadata rather than of the file tree.
---
# Derived hierarchy — inferred typed graph + `nav.py tree` (structure as projection)

## Problem

Phase 2 ([nav spec](2026-06-18-knowledge-navigation-tool.md)) made the corpus
*queryable* but only in **flat** views: `catalog` groups by `type`/`tag`/`status`,
and `links`/`backlinks` walk a **single, untyped** link graph. Two capabilities
the format already has the data for are still missing:

1. **Typed relationships.** `backlinks docs/X.md` answers "what *mentions* X" — not
   "what *implements* X", "what *supersedes* X", "what is X *grounded in*". The
   edges are real and already in the corpus (an exec-plan links the spec it builds;
   an ADR links the one it replaces; a spec links its design-doc), but nav reads
   them all as the same undifferentiated edge.
2. **Hierarchy.** There is no view that assembles a *tree* — a spec, the plans that
   implement it, the design-docs they rest on — as one connected structure. The
   only hierarchy available is the **directory tree**, which is a single fixed
   projection (physical location), and which `KNOWLEDGE_FORMAT.md` §2.2 explicitly
   says is *not* authoritative: "`type` is authoritative for machine routing; the
   directory is location." That thesis — **structure is a projection of metadata,
   not of the file tree** — is asserted but never *demonstrated*. Nothing renders an
   alternative hierarchy computed purely from frontmatter + links, ignoring where
   files physically live.

This matters beyond a nicety. It is the concrete first step of the larger question
the format raises: *if every page carries frontmatter, an agent can organize an
arbitrary corpus by code execution, independent of its on-disk layout.* A tool that
infers typed edges and renders a directory-independent tree is the smallest honest
proof of that claim — and the entry point to typed relationships
([OKF comparison](../design-docs/okf-comparison.md), adoption #4) **without** a
format change.

Two facts constrain the solution:

- **Inference, not declaration.** The relationships listed above are derivable from
  data we already have — the pair `(source.type, target.type)` plus link direction
  (and, for supersession, the target's `status`). So this phase needs **no new
  frontmatter key**. Declared/authored typed edges (a `supersedes:` frontmatter
  key) are a later *format* change (KF v1.1) and are a non-goal here. Starting with
  inference is free, reversible, and validates whether typed traversal is even
  wanted before any format commitment.
- **Read-only, live, consistent with Phase 2.** This is another projection over the
  same live-built index — no persisted artifact, no gate step, no `docs/generated/`
  output. It reuses Phase 2's `build_index` records as-is.

## Requirements

Each is independently checkable by a human.

- **R1 — An inference layer turns the untyped graph into typed edges.**
  `nav.py` gains `relations(records, root)` returning one typed edge per intra-corpus
  link: `{src, dst, rel, basis}`, where `rel` is the inferred relationship and
  `basis` names *why* it was inferred (the rule that fired, e.g.
  `"exec-plan→product-spec"`). A `nav.py relations [--rel R] [--json]` CLI surfaces
  it. **No frontmatter key is added**; `read_frontmatter` and `KNOWLEDGE_FORMAT.md`
  are unchanged.
- **R2 — The rule table is small, explicit, and precision-first.** Inference is a
  hardcoded `EDGE_RULES` table keyed on `(src_type, dst_type)` (plus the
  archived-target condition for `supersedes`). Any link not matching a rule keeps
  the generic relation `links` (the existing untyped edge) — nothing is lost, and a
  page with no `type` degrades gracefully to untyped. A wrong inferred type is worse
  than none, so the table favors high-confidence pairs and leaves the rest `links`.
- **R3 — `nav.py tree <path>` renders a derived subtree.** Following typed edges
  from a page, it prints an indented ASCII tree of `type: name  [relation]` nodes.
  Default direction is **forward** (what the page is built *on* — its dependencies);
  `--reverse` flips to **dependents** (what is built on it). `--rel a,b` restricts
  to chosen edge kinds; `--json` emits the nested structure. It is **cycle-safe**
  (a visited node renders once, marked `(↑ seen)`) and depth-bounded.
- **R4 — `nav.py tree --type <T>` renders a forest.** Rooted at every page of type
  `T` (e.g. `--type product-spec`), so one command shows all specs and what hangs
  off each.
- **R5 — Directory-independence is demonstrable (the proof).** For the real corpus,
  a single rendered tree contains pages that live in **≥2 different directories**
  grouped under one root by relationship (e.g. an `exec-plans/` plan, the
  `product-specs/` spec it implements, and the `design-docs/` doc that grounds it,
  in one tree). This visibly shows structure ≠ directory layout.
- **R6 — The skill teaches it.** `docs-nav/SKILL.md` gains the new intents
  (`relations`, `tree`) and a compact statement of the inference rule table, and
  cross-links `KNOWLEDGE_FORMAT.md` + `okf-comparison.md`.
- **R7 — Tested and gate-green.** `tests/test_nav.py` covers each inferred edge
  type, tree rendering (forward + reverse), cycle safety, the directory-independence
  case, and graceful degradation (missing `type` → `links`). `check.py` is GREEN.

## Design

### Components (all in `plugin/scripts/nav.py`)

Built on Phase 2's existing records — each already carries `path`, `type`, and the
resolved `links` list. No change to `build_index`.

**1. `EDGE_RULES` — the inference table.** A small dict keyed on `(src_type,
dst_type)` → forward-relation label, with the inverse used for reverse traversal:

| `src.type` | `dst.type` | forward `rel` | reverse (`--reverse`) |
|---|---|---|---|
| `exec-plan` | `product-spec` | `implements` | `implemented-by` |
| `product-spec` | `product-spec` | `refines` | `refined-by` |
| `adr` | `adr` *(dst `status` archived)* | `supersedes` | `superseded-by` |
| `adr`/`knowledge`/`product-spec`/`exec-plan` | `design-doc` | `grounded-in` | `grounds` |
| *(any)* | `methodology` | `governed-by` | `governs` |
| *(any)* | `knowledge` | `references` | `referenced-by` |
| *(fallback — no rule)* | | `links` | `linked-by` |

The table is **code, not config** — it is harness taste, the same call DESIGN/lint
rules make (precedent: declarative-config D-56 keeps methodology in code). Precision
over recall: only high-confidence pairs are typed; everything else stays `links`.

**2. `relations(records, root)`** → `list[{src, dst, rel, basis}]`. For each
record and each entry in its resolved `links`, look up `(src.type, dst.type)` in
`EDGE_RULES` (consulting `dst.status` for the supersedes condition), emit the typed
edge with `basis` = the rule key (or `"untyped"`). Targets outside the page graph
(e.g. a `resource` code path) are **not** page-graph edges and are out of scope for
the tree; `relations` may surface `documents` (page→`resource`) edges as a flat
extra for completeness, but `tree` walks page→page only (keeps the hierarchy clean).

**3. `tree(records, root, start, *, reverse, rels, max_depth)`** → a nested dict
`{path, type, rel, children:[…]}`. Build an adjacency map from `relations()`
(forward, or inverted when `reverse`), filtered to `rels` if given; DFS from
`start`, carrying a `visited` set so a re-encountered node is emitted once with a
`seen=True` marker and not re-expanded (handles cycles + diamonds). `_render_tree`
turns the dict into indented ASCII (`├─`/`└─`/`│` guides) with
`type: <slug>  [<rel>]` labels; `--json` prints the dict.

### CLI

```
nav.py relations [--rel implements] [--json]
nav.py tree <path> [--reverse] [--rel implements,grounded-in] [--json]
nav.py tree --type product-spec [--reverse] [--json]
```

Example (forward from an exec-plan — three directories, one tree):

```
exec-plan: 2026-06-18-knowledge-navigation-tool   (docs/exec-plans/completed/)
└─[implements] product-spec: 2026-06-18-knowledge-navigation-tool   (docs/product-specs/)
   └─[grounded-in] design-doc: okf-comparison   (docs/design-docs/)
```

The parenthetical source dirs are shown only to make the proof legible in this
spec; the renderer labels nodes by `type: slug` and never consults the directory to
*build* the tree — directory is incidental, not structural.

### Edge cases & integration

- **Missing `type`** (un-backfilled or host page): no rule matches → edge stays
  `links`; the page still appears as an untyped node. Inference never crashes on
  absent metadata (mirrors Phase 2's defensive `_as_list`).
- **Cycles / diamonds:** visited-set + `seen` marker; `max_depth` backstop.
- **Empty result:** `tree` on a page with no typed edges prints just the root node;
  `relations --rel X` with no matches prints the `0 edge(s)` footer (Phase 2 style).
- **Consistency:** `relations` is a pure projection of the same `links` D5 walks, so
  the typed graph can never name an edge the lint graph lacks.

### Files

- `plugin/scripts/nav.py` — add `EDGE_RULES`, `relations()`, `tree()`,
  `_render_tree()`, and the `relations` / `tree` subcommands. No change to
  `build_index` or `harness_lib`.
- `plugin/skills/docs-nav/SKILL.md` — new intents + rule-table summary.
- `tests/test_nav.py` — new `TestNavRelations` / `TestNavTree` classes.

## Non-goals

- **NG-1 — No new frontmatter / declared edges.** No `supersedes:` (or any)
  relationship key. Authored typed edges are a *format* change (KF v1.1) and are
  deferred; this phase is inference-only over existing metadata.
- **NG-2 — No `viz.html` / rendered graph.** Output is ASCII + JSON, agent-facing
  (the standing Phase-2 decision; a human-browsing graph view remains deferred).
- **NG-3 — No lint / gate enforcement.** Relationships are advisory and read-only,
  like the rest of nav. No "every spec must have an implementing plan" rule.
- **NG-4 — No persistence.** Live-computed per call; nothing written to
  `docs/generated/`.
- **NG-5 — No file reorganization.** The tool *renders* the derived hierarchy; it
  does not move files or propose a directory restructure (a later, separate step —
  the "act on the projection" frontier).
- **NG-6 — Not a general graph-query language.** Fixed subcommands, a fixed rule
  table — not arbitrary path/pattern queries over the graph.

## Acceptance criteria

1. `nav.py relations --json` emits typed edges with `basis`; manual inspection
   confirms the real `exec-plan→product-spec` links are typed `implements`, a
   `product-spec→product-spec` link is `refines`, and a link to a `design-doc` is
   `grounded-in`. (R1, R2)
2. `nav.py tree --type product-spec` prints an indented forest; at least one root's
   subtree contains a page from a **different directory** than the root, with a
   relation label other than `links`. (R3, R4, R5)
3. `nav.py tree <path>` renders the subtree; a corpus with a deliberate cycle does
   **not** loop (the second visit shows `(↑ seen)`). (R3)
4. No new frontmatter key exists; `docs/KNOWLEDGE_FORMAT.md` and `read_frontmatter`
   are unchanged by this work; `python3 plugin/scripts/check.py` is GREEN. (R1, R7)
5. `docs-nav/SKILL.md` documents `relations` + `tree` and the rule table;
   `tests/test_nav.py` covers each edge type, both tree directions, the cycle case,
   directory-independence, and missing-`type` degradation. (R6, R7)

## Relationship to prior work

- Builds directly on [Knowledge navigation tool (Phase 2)](2026-06-18-knowledge-navigation-tool.md)
  — same `build_index`, same live-query/read-only stance — and on the
  [Phase-1 format](2026-06-18-knowledge-format-evolution.md) whose `type` key is what
  makes inference possible.
- Realizes the **inference half** of OKF adoption #4 (a typed graph / "cited-by"
  hierarchy) from [`okf-comparison.md`](../design-docs/okf-comparison.md), and is the
  concrete demonstration of the "`type` is authoritative, directory is location"
  thesis in [`KNOWLEDGE_FORMAT.md`](../KNOWLEDGE_FORMAT.md) §2.2.
- Is **Step 1 of the two-tier typed-link plan**: *inferred* edges now (no format
  change), *declared* edges later (KF v1.1, the deferred "Typed link relationships"
  roadmap item in the Phase-1 spec) only if a query needs a relationship inference
  cannot supply. This spec is also the smallest concrete probe of the larger
  "frontmatter ⇒ agent-organizable corpus" direction: it proves structure is a
  computable projection before any investment in acting on that projection.
