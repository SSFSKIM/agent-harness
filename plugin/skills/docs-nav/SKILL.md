---
name: docs-nav
description: Use when finding or orienting in existing docs — query the knowledge corpus by type/tag/status, follow backlinks before editing, or sweep for stale/orphan/drifted pages, instead of bulk-reading bodies.
---
# Docs navigation (query, don't bulk-read)

`docs-tree` decides *where a new page goes*; `docs-nav` finds *what already
exists* without opening every file. The engine is `nav.py` — a read-only
navigator that rebuilds a live index from frontmatter + the markdown link graph
on every call (nothing is persisted; results are always current). Invoke it from
the plugin's `scripts/` dir (the same location as the gate command recorded in
`docs/design-docs/agent-harness.md`):

    python3 <plugin>/scripts/nav.py <command> [args]

## When to reach for it

- **Orienting** in an unfamiliar area → `catalog --type adr` / `--tag gate` to
  see kinds and one-line descriptions without reading bodies.
- **Before editing a page** → `backlinks <path>` to learn what depends on it
  (the single most useful pre-edit safety check).
- **Gardening / GC pass** (doc-gardener) → `stale`, `orphans`, `drift` to find
  pages to re-verify, wire up, or reconcile against moved code.

## Intent → command

| You want… | Command |
|---|---|
| All pages of a kind, with descriptions | `nav.py catalog --type adr` |
| Pages tagged X (optionally AND a type/status) | `nav.py catalog --tag gate [--type … --status …]` |
| The whole corpus as JSON (agent code path) | `nav.py catalog --json` |
| What this page links to | `nav.py links docs/PLANS.md` |
| What links to this page (backlinks) | `nav.py backlinks docs/PLANS.md` |
| Pages past the staleness window | `nav.py stale` |
| Content pages nothing links to (optionally one type) | `nav.py orphans [--type knowledge]` |
| Pages whose bound code moved since last_verified | `nav.py drift` |
| Typed edges inferred from the link graph | `nav.py relations [--rel implements]` |
| A derived hierarchy, ignoring directories | `nav.py tree --type product-spec` |
| What a page is built on / what builds on it | `nav.py tree <path> [--reverse]` |
| A progress map: initiative → phase → status | `nav.py roadmap` |
| The whole picture: charter → initiatives → roadmap | `nav.py map` |

Every command takes `--json` for machine consumption; the library functions
(`build_index`, `catalog`, `backlinks`, `stale`, `drift`) are importable for the
code-execution path (`from nav import build_index, backlinks`).

## What the output means

- `catalog` reads **frontmatter only** — a page with an empty body still appears
  with its `type`/`tags`/`description`. It lists content pages; reserved spines
  (`index.md`, `MEMORY.md`) and the entry maps are excluded.
- `stale`/`orphans`/`drift` are **advisory** — never a gate failure. `stale`
  agrees with what lint D4 would flag. `orphans` is graph-based: a page reachable
  only by a bare-text mention (not a `[](…)` link) counts as an orphan, so a
  high count usually means index pages use prose, not markdown links. Terminal /
  historical tiers (exec-plans, session-digests) are orphaned by design — scope
  with `orphans --type knowledge` to surface only the *concerning* ones.
- `drift` compares each page's `resource` to its code's last git-commit date;
  `unknown` means no git / missing path / a URL (fail-soft, never an error).

## Inferred relationships & derived hierarchy

`relations` / `tree` add a **typed** layer over the link graph with **no new
frontmatter** — the edge kind is inferred from the endpoints' `type`:

| from → to | relation |
|---|---|
| exec-plan → product-spec | `implements` |
| product-spec → product-spec | `refines` |
| adr → archived adr | `supersedes` |
| adr/knowledge/spec/plan → design-doc | `grounded-in` |
| any → methodology / knowledge | `governed-by` / `references` |
| no rule (or page has no `type`) | `links` (untyped — graceful default) |

`tree` renders a hierarchy from frontmatter + links alone, **ignoring the
directory layout**: a spec, the plan that `implements` it, and the design-doc it is
`grounded-in` appear in one tree though they live in three directories — structure
is a projection of metadata, not of the file tree (`KNOWLEDGE_FORMAT.md` §2.2).
Default follows dependencies (what a page is built on); `--reverse` shows
dependents; `--rel a,b` restricts edge kinds; `--json` for machine use. `tree`
shows only **typed** relationships by default (the generic untyped `links` edges —
incidental mentions — are dropped so the hierarchy stays meaningful); pass `--all`
to include them. Inference only — authored/declared relationship keys remain a
future KF minor (not v1.1, which adds only `phase` + the `charter` type).

`roadmap` is the **derived progress map** — the methodology's long-promised
"roadmap is a derived view, not hand-maintained" (PLANS.md), delivered. It groups
the work tier (product-spec + exec-plan) by the optional `phase` frontmatter key
(`<initiative>/<NN>-<slug>`) into initiative → phase → `status:`, ordering phases
by `NN`. A plan with no `phase` inherits it from the spec it `implements`; a page
with neither lands in the advisory `(unphased)` bucket. Genuine design pivots show
inline (`[superseded-by …]` — a newer page retiring an archived one of its kind,
deduped) so the map doubles as the evolution view; a structural `refines` is not a
pivot and is not shown. The authored intent lives in `docs/CHARTER.md`
(`KNOWLEDGE_FORMAT.md` §2.2); the roadmap is its live projection. `--json` for
machine use.

`map` is the single **charter-rooted** view: it makes `docs/CHARTER.md` the graph
root (via the inferred `charters` edge: charter → the `product-spec` it links) and
hangs each initiative's `roadmap` branch under it — the Big Picture → initiatives →
phases → specs/plans + pivots in one descent. An initiative present in the roadmap
but anchored by no charter link renders flagged (`⚠ not anchored in charter`), so a
drift between the authored charter and the derived initiative set is visible rather
than silent. Start here to grasp the whole project at once; drop to `roadmap`/`tree`
for a slice.

This is the consumer half of the knowledge format — the queryable axes come from
`docs/KNOWLEDGE_FORMAT.md` (`type`/`tags`/`description`/`resource`); see
`docs/design-docs/okf-comparison.md` for why navigation is agent-facing (query)
rather than a rendered graph.
