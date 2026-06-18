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
import datetime
import json
import subprocess
from pathlib import Path

import harness_lib as hl

# docs subtrees nav never indexes — the shared exempt set (hl.DOC_EXEMPT, also
# lint's FM_EXEMPT), plus host .harnessignore roots at build time. Pure stdlib +
# harness_lib only — nav must not import lint_docs (lint S1, core-belief 7), so
# scope is derived here from frontmatter + harness_lib helpers rather than by
# reusing the gate's predicate. In self-host this set equals lint's governed
# content pages (every governed page carries frontmatter per D3); in relaxed
# hosts nav may show a few more frontmatter-bearing pages, which is fine for a
# read-only navigator.
EXEMPT = hl.DOC_EXEMPT
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
                try:
                    out.append(cand.resolve().relative_to(root.resolve()).as_posix())
                except ValueError:
                    pass  # exists but escapes the repo root — not an intra-corpus edge
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


def _norm(path, root):
    """Normalize a user-supplied path to repo-relative posix (accepts absolute
    or repo-relative; a leading ./ is stripped)."""
    root = Path(root).resolve()
    p = Path(path)
    cand = p if p.is_absolute() else root / p
    try:
        return cand.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.lstrip("./")


def links(records, path, root):
    """Forward `.md` link targets of `path` (sorted for stable CLI output; the
    record's stored `links` list preserves document order)."""
    target = _norm(path, root)
    rec = next((r for r in records if r["path"] == target), None)
    return sorted(rec["links"]) if rec else []


def backlinks(records, path, root):
    """Pages that markdown-link to `path` (the reverse of the link graph)."""
    target = _norm(path, root)
    return sorted(r["path"] for r in records if target in r["links"])


def orphans(records):
    """Catalog pages with no inbound markdown link (unreachable in the graph).

    Reserved spines (index.md/MEMORY.md) and the entry maps are not catalog
    pages, so they are never reported. A page linked only by a bare-text mention
    (not a `[](…)` link) still counts as an orphan — this mirrors the D5 graph."""
    linked = set()
    for r in records:
        linked.update(r["links"])
    return sorted(r["path"] for r in records
                  if r["catalog"] and r["path"] not in linked)


def stale(records, stale_days):
    """Catalog pages past `stale_days` (advisory view of D4) — a pure projection.

    Uses the shared `hl.is_stale`, so it agrees with what the gate's D4 would
    flag at the same window (main() resolves the window via `hl.stale_window`). A
    bad/missing date is a lint concern, not a staleness one, and is skipped."""
    out = []
    for r in records:
        if not r["catalog"] or not r["last_verified"]:
            continue
        try:
            if hl.is_stale(r["last_verified"], stale_days, r["status"]):
                out.append(r)
        except (ValueError, TypeError):
            continue
    return out


def _resource_state(root, resource, last_verified):
    """drift state for one resource: 'drifted' (code committed after the page's
    last_verified), 'current', or 'unknown' (no git / missing / bad date / URL).
    Fail-soft — never raises, never a non-zero exit."""
    if (not isinstance(resource, str) or not resource
            or resource.startswith(("http://", "https://"))):
        return "unknown"
    if not (root / resource).exists():
        return "unknown"
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%cI", "--", resource],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    iso = r.stdout.strip()
    if r.returncode != 0 or not iso:
        return "unknown"
    try:
        committed = datetime.date.fromisoformat(iso[:10])
        verified = datetime.date.fromisoformat(last_verified)
    except (ValueError, TypeError):
        return "unknown"
    return "drifted" if committed > verified else "current"


def drift(records, root):
    """Per resource-bound page, whether its code moved since last_verified.

    Returns rows {path, resource, last_verified, state} for every record that
    declares a `resource`. Advisory only — `resource` exists to enable exactly
    this check (spec / Phase-1 NG-3)."""
    root = Path(root).resolve()
    out = []
    for r in records:
        if not r["resource"]:
            continue
        out.append({"path": r["path"], "resource": r["resource"],
                    "last_verified": r["last_verified"],
                    "state": _resource_state(root, r["resource"], r["last_verified"])})
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


def _emit_paths(paths, as_json):
    if as_json:
        print(json.dumps(paths, ensure_ascii=False))
    else:
        for p in paths:
            print(p)
        print(f"# {len(paths)} page(s)")


def _emit_drift(rows, as_json):
    if as_json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        drifted = [r for r in rows if r["state"] == "drifted"]
        for r in drifted:
            print(f"{r['path']}  ->  {r['resource']}  (verified {r['last_verified']})")
        unknown = sum(1 for r in rows if r["state"] == "unknown")
        print(f"# {len(drifted)} drifted, {len(rows)} resource-bound "
              f"({unknown} unknown) — advisory")


def main(argv=None):
    root = hl.repo_root()
    ap = argparse.ArgumentParser(description="Knowledge navigator (read-only).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("catalog", help="list pages by type/tag/status with descriptions")
    c.add_argument("--type", dest="kind", help="filter by frontmatter type")
    c.add_argument("--tag", help="filter by a tag")
    c.add_argument("--status", help="filter by status")
    c.add_argument("--json", action="store_true", help="emit JSON records")
    for name, helptext in (("links", "pages this page links to"),
                           ("backlinks", "pages that link to this page")):
        g = sub.add_parser(name, help=helptext)
        g.add_argument("path", help="repo-relative page path (e.g. docs/PLANS.md)")
        g.add_argument("--json", action="store_true", help="emit JSON")
    for name, helptext in (("stale", "pages past the staleness window (advisory)"),
                           ("orphans", "catalog pages with no inbound link"),
                           ("drift", "resource-bound pages whose code moved")):
        h = sub.add_parser(name, help=helptext)
        h.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    records = build_index(root)
    if args.cmd == "catalog":
        _emit(catalog(records, args.kind, args.tag, args.status), args.json)
    elif args.cmd == "links":
        _emit_paths(links(records, args.path, root), args.json)
    elif args.cmd == "backlinks":
        _emit_paths(backlinks(records, args.path, root), args.json)
    elif args.cmd == "orphans":
        _emit_paths(orphans(records), args.json)
    elif args.cmd == "stale":
        _emit(stale(records, hl.stale_window(hl.gate_config(root))), args.json)
    elif args.cmd == "drift":
        _emit_drift(drift(records, root), args.json)


if __name__ == "__main__":
    main()
