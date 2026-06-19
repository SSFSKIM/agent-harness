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
    resource, phase, last_verified, links, catalog.
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
            "phase": (fm or {}).get("phase"),
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


def orphans(records, kind=None):
    """Catalog pages with no inbound markdown link (unreachable in the graph).

    Reserved spines (index.md/MEMORY.md) and the entry maps are not catalog
    pages, so they are never reported. A page linked only by a bare-text mention
    (not a `[](…)` link) still counts as an orphan — this mirrors the D5 graph.
    `kind` restricts the report to one `type` (e.g. only `knowledge`), useful
    because terminal/historical tiers like exec-plans are orphaned by design."""
    linked = set()
    for r in records:
        linked.update(r["links"])
    return sorted(r["path"] for r in records
                  if r["catalog"] and r["path"] not in linked
                  and (kind is None or r["type"] == kind))


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


# --- Inferred typed graph + derived hierarchy (spec 2026-06-19) -----------------
# The edge KIND is inferred from each link's (source type, target type) pair (plus
# the target status, for supersession) — NO new frontmatter key. A link matching no
# rule keeps the generic untyped relation "links", so a page with no `type` degrades
# gracefully. Precision over recall: only high-confidence pairs are typed.
EDGE_RULES = {  # exact (src_type, dst_type) -> forward relation
    ("exec-plan", "product-spec"): "implements",
    ("product-spec", "product-spec"): "refines",
    ("adr", "design-doc"): "grounded-in",
    ("knowledge", "design-doc"): "grounded-in",
    ("product-spec", "design-doc"): "grounded-in",
    ("exec-plan", "design-doc"): "grounded-in",
}
INVERSE = {  # forward relation -> reverse label (for `tree --reverse`)
    "implements": "implemented-by", "refines": "refined-by",
    "supersedes": "superseded-by", "grounded-in": "grounds",
    "governed-by": "governs", "references": "referenced-by", "links": "linked-by",
}
UNTYPED = ("links", "linked-by")  # the generic fallback edge (incidental mentions)


def _infer_rel(src_type, dst_type, dst_status):
    """Infer an edge kind, most-specific first; returns (relation, basis).

    basis names the rule that fired so the inference is auditable. Anything not
    matched stays ('links', 'untyped') — the existing undifferentiated edge."""
    if (src_type, dst_type) in EDGE_RULES:
        return EDGE_RULES[(src_type, dst_type)], f"{src_type}->{dst_type}"
    if src_type == "adr" and dst_type == "adr" and dst_status == "archived":
        return "supersedes", "adr->archived-adr"
    if dst_type == "methodology":
        return "governed-by", "*->methodology"
    if dst_type == "knowledge":
        return "references", "*->knowledge"
    return "links", "untyped"


def relations(records):
    """Type the link graph: one {src, dst, rel, basis} per intra-corpus link.

    A pure projection over build_index records (build_index is untouched; links
    are already repo-relative, so no root is needed). The relation is inferred via
    `_infer_rel` from the endpoints' `type`/`status`; a target not in the page
    graph (or a page without `type`) yields rel='links'."""
    by_path = {r["path"]: r for r in records}
    out = []
    for r in records:
        for dst in r["links"]:
            d = by_path.get(dst) or {}
            rel, basis = _infer_rel(r.get("type"), d.get("type"), d.get("status"))
            out.append({"src": r["path"], "dst": dst, "rel": rel, "basis": basis})
    return out


def _adjacency(records, reverse, rels, include_untyped):
    """Adjacency map {src: [(dst, rel), …]} from the typed edges, oriented by
    `reverse` (dependents vs dependencies).

    Filtering: if `rels` is given, keep exactly those relations; otherwise drop the
    generic untyped edges (links/linked-by — incidental markdown mentions) unless
    `include_untyped`, so a hierarchy shows real relationships by default.
    Collapses repeated links to the same target into one edge (a page that links a
    target twice is one relationship — the rel is deterministic per type-pair), so
    the hierarchy has no duplicate children."""
    adj, seen = {}, set()
    for e in relations(records):
        if reverse:
            src, dst, rel = e["dst"], e["src"], INVERSE.get(e["rel"], e["rel"])
        else:
            src, dst, rel = e["src"], e["dst"], e["rel"]
        if rels is not None:
            if rel not in rels:
                continue
        elif not include_untyped and rel in UNTYPED:
            continue
        if (src, dst) in seen:
            continue
        seen.add((src, dst))
        adj.setdefault(src, []).append((dst, rel))
    return adj


def tree(records, start, reverse=False, rels=None, include_untyped=False,
         max_depth=20):
    """Derived hierarchy rooted at `start`, following inferred typed edges.

    Built from frontmatter + links only — never the directory layout (that is the
    'structure = projection' proof). By default follows only typed relationships
    (the generic untyped `links` edges are dropped — pass include_untyped, CLI
    `--all`, to keep them, or name them in `rels`). Cycle-safe: a node is expanded
    once; a re-encountered node renders with seen=True and is not re-expanded.
    Depth-bounded. Returns a nested {path, type, rel, seen, children}."""
    adj = _adjacency(records, reverse, rels, include_untyped)
    by_path = {r["path"]: r for r in records}
    visited = set()

    def node(path, rel, depth):
        n = {"path": path, "type": by_path.get(path, {}).get("type"),
             "rel": rel, "seen": path in visited, "children": []}
        if path in visited or depth >= max_depth:
            n["seen"] = True
            return n
        visited.add(path)
        for dst, r in sorted(adj.get(path, [])):
            n["children"].append(node(dst, r, depth + 1))
        return n

    return node(start, None, 0)


def _slug(path):
    name = path.rsplit("/", 1)[-1]
    return name[:-3] if name.endswith(".md") else name


def _tree_lines(node, prefix="", is_last=True, is_root=True):
    """Render a tree() dict as indented ASCII lines (type: slug [rel] (↑ seen))."""
    label = f"{node['type'] or '-'}: {_slug(node['path'])}"
    if node["rel"]:
        label += f"  [{node['rel']}]"
    if node["seen"]:
        label += "  (↑ seen)"
    if is_root:
        lines, child_prefix = [label], ""
    else:
        lines = [prefix + ("└─ " if is_last else "├─ ") + label]
        child_prefix = prefix + ("   " if is_last else "│  ")
    kids = node["children"]
    for i, c in enumerate(kids):
        lines += _tree_lines(c, child_prefix, i == len(kids) - 1, False)
    return lines


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


def _emit_relations(edges, as_json):
    if as_json:
        print(json.dumps(edges, indent=2, ensure_ascii=False))
    else:
        for e in edges:
            print(f"{e['src']}  --{e['rel']}-->  {e['dst']}  ({e['basis']})")
        typed = sum(1 for e in edges if e["rel"] != "links")
        print(f"# {len(edges)} edge(s), {typed} typed")


def _emit_tree(trees, as_json, forest):
    if as_json:
        out = trees if forest else (trees[0] if trees else None)
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        for i, tr in enumerate(trees):
            if i:
                print()
            for line in _tree_lines(tr):
                print(line)


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
                           ("drift", "resource-bound pages whose code moved")):
        h = sub.add_parser(name, help=helptext)
        h.add_argument("--json", action="store_true", help="emit JSON")
    op = sub.add_parser("orphans", help="catalog pages with no inbound link")
    op.add_argument("--type", dest="kind", help="restrict to a frontmatter type")
    op.add_argument("--json", action="store_true", help="emit JSON")
    rp = sub.add_parser("relations", help="typed edges inferred from the link graph")
    rp.add_argument("--rel", help="filter to one relation kind (e.g. implements)")
    rp.add_argument("--json", action="store_true", help="emit JSON edges")
    tp = sub.add_parser("tree", help="derived hierarchy from inferred typed edges")
    tp.add_argument("path", nargs="?", help="root page (repo-relative); omit with --type")
    tp.add_argument("--type", dest="kind", help="root at every page of this type (forest)")
    tp.add_argument("--reverse", action="store_true",
                    help="follow dependents instead of dependencies")
    tp.add_argument("--rel", help="comma-separated relation kinds to include")
    tp.add_argument("--all", dest="include_untyped", action="store_true",
                    help="include generic untyped 'links' edges (default: typed only)")
    tp.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    records = build_index(root)
    if args.cmd == "catalog":
        _emit(catalog(records, args.kind, args.tag, args.status), args.json)
    elif args.cmd == "links":
        _emit_paths(links(records, args.path, root), args.json)
    elif args.cmd == "backlinks":
        _emit_paths(backlinks(records, args.path, root), args.json)
    elif args.cmd == "orphans":
        _emit_paths(orphans(records, args.kind), args.json)
    elif args.cmd == "stale":
        _emit(stale(records, hl.stale_window(hl.gate_config(root))), args.json)
    elif args.cmd == "drift":
        _emit_drift(drift(records, root), args.json)
    elif args.cmd == "relations":
        edges = relations(records)
        if args.rel:
            edges = [e for e in edges if e["rel"] == args.rel]
        _emit_relations(edges, args.json)
    elif args.cmd == "tree":
        rels = set(args.rel.split(",")) if args.rel else None
        if args.kind:
            roots = [r["path"] for r in records if r["type"] == args.kind]
        elif args.path:
            roots = [_norm(args.path, root)]
        else:
            ap.error("tree needs a <path> or --type")
        trees = [tree(records, s, reverse=args.reverse, rels=rels,
                      include_untyped=args.include_untyped)
                 for s in roots]
        _emit_tree(trees, args.json, forest=bool(args.kind))


if __name__ == "__main__":
    main()
