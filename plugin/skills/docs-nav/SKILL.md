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
| Content pages nothing links to | `nav.py orphans` |
| Pages whose bound code moved since last_verified | `nav.py drift` |

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
  high count usually means index pages use prose, not markdown links.
- `drift` compares each page's `resource` to its code's last git-commit date;
  `unknown` means no git / missing path / a URL (fail-soft, never an error).

This is the consumer half of the knowledge format — the queryable axes come from
`docs/KNOWLEDGE_FORMAT.md` (`type`/`tags`/`description`/`resource`); see
`docs/design-docs/okf-comparison.md` for why navigation is agent-facing (query)
rather than a rendered graph.
