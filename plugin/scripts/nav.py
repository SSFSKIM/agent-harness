#!/usr/bin/env python3
"""Knowledge navigator — live query over the docs corpus (Phase 2).

Read-only, on-demand: every invocation rebuilds the index from frontmatter +
the markdown link graph, so results are always fresh and nothing is persisted
(no committed catalog, no generated index.md — see
docs/product-specs/2026-06-18-knowledge-navigation-tool.md). NOT wired into the
commit gate; this is an aid the agent (or doc-gardener) runs to navigate the
corpus without bulk-reading bodies.

Library: `build_index(root)` -> list[record]; query helpers project over it.
CLI: `python3 plugin/scripts/nav.py <catalog|links|backlinks|stale|orphans|drift>`.
"""
import argparse
import json
from pathlib import Path

import harness_lib as hl

# docs subtrees nav never indexes (mirrors lint's FM_EXEMPT). Pure stdlib +
# harness_lib only — nav must not import lint_docs (lint S1, core-belief 7), so
# scope is derived here from frontmatter + harness_lib helpers rather than by
# reusing the gate's predicate. In self-host this set equals lint's governed
# content pages (every governed page carries frontmatter per D3); in relaxed
# hosts nav may show a few more frontmatter-bearing pages, which is fine for a
# read-only navigator.
EXEMPT = ("generated/", "superpowers/")
# Reserved spine files: indexed as link roots, never catalog rows or orphans.
RESERVED = ("index.md", "MEMORY.md")


def _as_list(v):
    """Coerce a frontmatter `tags` value to list[str] defensively.

    read_frontmatter returns a list for the canonical/block forms, but a
    malformed authoring (scalar) must not crash a `--tag` filter — degrade a
    non-empty scalar to a single-item list, empty/None to []."""
    if isinstance(v, list):
        return v
    if v is None or v == "":
        return []
    return [v]


def _resolve_links(p, root, raw):
    """Map raw markdown targets to repo-relative posix paths (http(s) dropped).

    Mirrors lint D5 resolution: a target resolves against the page's own dir
    first, then the repo root. Unresolvable/external targets are skipped, so an
    edge always names a real repo path that can match a record's `path`."""
    out = []
    for t in raw:
        if t.startswith(("http://", "https://")):
            continue
        for base in (p.parent, root):
            cand = base / t
            if cand.exists():
                out.append(cand.resolve().relative_to(root.resolve()).as_posix())
                break
    return out


def build_index(root):
    """One record per indexed page, built live from frontmatter + link scan.

    Indexed set = non-exempt docs/ pages + the entry maps (AGENTS.md,
    ARCHITECTURE.md), the latter as link roots. A record is `catalog`-eligible
    when it carries frontmatter and is not a reserved spine file (index.md /
    MEMORY.md) — that is the content corpus the `catalog`/`orphans` queries act
    on. Bodies are read only for the link scan; catalog columns come from
    frontmatter alone. Record keys: path, type, tags, status, description,
    resource, last_verified, links, catalog.
    """
    root = Path(root).resolve()
    docs = root / "docs"
    exempt = EXEMPT + hl.exempt_roots(root)
    paths = [p for p in hl.iter_md(docs)
             if not hl.is_exempt(p.relative_to(docs).as_posix(), exempt)]
    for name in ("AGENTS.md", "ARCHITECTURE.md"):
        q = root / name
        if q.exists():
            paths.append(q)
    records = []
    for p in paths:
        fm = hl.read_frontmatter(p)
        text = p.read_text(encoding="utf-8", errors="replace")
        records.append({
            "path": p.relative_to(root).as_posix(),
            "type": (fm or {}).get("type"),
            "tags": _as_list((fm or {}).get("tags")),
            "status": (fm or {}).get("status"),
            "description": (fm or {}).get("description"),
            "resource": (fm or {}).get("resource"),
            "last_verified": (fm or {}).get("last_verified"),
            "links": _resolve_links(p, root, hl.links_in(text)),
            "catalog": fm is not None and p.name not in RESERVED,
        })
    return records


def catalog(records, kind=None, tag=None, status=None):
    """Catalog-eligible content pages, optionally filtered by type/tag/status (AND)."""
    out = [r for r in records if r["catalog"]]
    if kind:
        out = [r for r in out if r["type"] == kind]
    if tag:
        out = [r for r in out if tag in r["tags"]]
    if status:
        out = [r for r in out if r["status"] == status]
    return out


def _public(rec):
    """A record without the internal `catalog` flag, for JSON output."""
    return {k: v for k, v in rec.items() if k != "catalog"}


def _fmt_row(r):
    tags = ",".join(r["tags"])
    desc = r["description"] or ""
    return f"{r['path']}  {r['type'] or '-'}  [{tags}]  — {desc}"


def _emit(rows, as_json):
    if as_json:
        print(json.dumps([_public(r) for r in rows], indent=2, ensure_ascii=False))
    else:
        for r in rows:
            print(_fmt_row(r))
        print(f"# {len(rows)} page(s)")


def main(argv=None):
    root = hl.repo_root()
    ap = argparse.ArgumentParser(description="Knowledge navigator (read-only).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("catalog", help="list pages by type/tag/status with descriptions")
    c.add_argument("--type", dest="kind", help="filter by frontmatter type")
    c.add_argument("--tag", help="filter by a tag")
    c.add_argument("--status", help="filter by status")
    c.add_argument("--json", action="store_true", help="emit JSON records")
    args = ap.parse_args(argv)

    records = build_index(root)
    if args.cmd == "catalog":
        _emit(catalog(records, args.kind, args.tag, args.status), args.json)


if __name__ == "__main__":
    main()
