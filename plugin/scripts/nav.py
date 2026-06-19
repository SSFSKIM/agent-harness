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
            "supersedes": _resolve_links(p, root, _as_list((fm or {}).get("supersedes"))),
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
    ("charter", "product-spec"): "charters",
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
    "charters": "chartered-by",
}
UNTYPED = ("links", "linked-by")  # the generic fallback edge (incidental mentions)


def _infer_rel(src_type, dst_type, dst_status):
    """Infer an edge kind, most-specific first; returns (relation, basis).

    basis names the rule that fired so the inference is auditable. Anything not
    matched stays ('links', 'untyped') — the existing undifferentiated edge."""
    # Supersession is the most specific signal and the only genuine *pivot*: a page
    # pointing at an ARCHIVED page of its own kind (a newer adr/spec/plan retiring
    # the one it replaces). Checked before the generic same-type pair rule
    # (e.g. product-spec->product-spec=refines), which is structural, not a pivot.
    if src_type and src_type == dst_type and dst_status == "archived":
        return "supersedes", f"{src_type}->archived-{dst_type}"
    if (src_type, dst_type) in EDGE_RULES:
        return EDGE_RULES[(src_type, dst_type)], f"{src_type}->{dst_type}"
    if dst_type == "methodology":
        return "governed-by", "*->methodology"
    if dst_type == "knowledge":
        return "references", "*->knowledge"
    return "links", "untyped"


def relations(records):
    """Type the link graph: one {src, dst, rel, basis} per intra-corpus link.

    A pure projection over build_index records (links are already repo-relative, so
    no root is needed). The relation is inferred via `_infer_rel` from the
    endpoints' `type`/`status`; a target not in the page graph (or a page without
    `type`) yields rel='links'. Plus the one *declared* edge: each `supersedes`
    frontmatter target emits a `supersedes` edge (basis 'declared') that wins over
    the inferred edge for that same (src,dst) pair (KF v1.2)."""
    by_path = {r["path"]: r for r in records}
    out = []
    for r in records:
        # declared `supersedes` edges (KF v1.2) — the one authored relationship;
        # they win over the inferred edge for the same (src,dst) pair.
        declared = r.get("supersedes", [])
        dset = set(declared)
        for dst in declared:
            out.append({"src": r["path"], "dst": dst, "rel": "supersedes",
                        "basis": "declared"})
        for dst in r["links"]:
            if dst in dset:
                continue  # a declared supersedes already covers this edge
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


def _phase_key(phase):
    """Parse a `phase` value into (initiative, order, label) for the roadmap, or None.

    Convention `<initiative>/<NN>-<slug>` -> (initiative, NN, '<NN>-<slug>'); a
    non-numeric NN sorts last (order +inf). A bare `<initiative>` is the umbrella
    and sorts first (order -1). A blank/None phase yields None (unphased)."""
    if not phase or not str(phase).strip():
        return None
    phase = str(phase).strip()
    if "/" in phase:
        init, rest = phase.split("/", 1)
        head = rest.split("-", 1)[0]
        try:
            order = int(head)
        except ValueError:
            order = 10 ** 9
        return (init.strip(), order, rest.strip())
    return (phase, -1, "")


def roadmap(records):
    """Derived progress map: initiatives -> phase-ordered specs/plans with status.

    A pure projection over build_index — the unkept "roadmap is a derived view"
    promise (PLANS.md; product-design skill). The phase comes from the `phase`
    frontmatter key; a row with none inherits the phase of the spec it
    `implements` (the inferred edge, earliest phase if it implements several), else
    falls into the advisory '(unphased)' bucket. Each row carries any pivot
    (superseded-by — supersession is the only genuine pivot, not a structural
    refines) inferred from the graph, so it shows inline. Row universe =
    product-spec + exec-plan
    (the work tier); design-docs/ADRs surface only as pivot annotations, never
    rows. Nothing persisted; live per call.

    Returns {initiatives: [{initiative, phases: [{phase, order, items}]}], unphased}
    where each item is {path, type, status, phase, pivots}."""
    by_path = {r["path"]: r for r in records}
    implements, pivots = {}, {}
    for e in relations(records):
        if e["rel"] == "implements":
            implements.setdefault(e["src"], []).append(e["dst"])
        elif e["rel"] == "supersedes":  # the only genuine pivot (not structural refines)
            pivots.setdefault(e["dst"], set()).add((INVERSE[e["rel"]], e["src"]))

    def phase_of(r):
        if r.get("phase"):
            return r["phase"]
        # no own phase -> inherit from the spec(s) it implements; if it implements
        # several, pick the earliest phase deterministically (lowest initiative/NN),
        # never the link-order-dependent first edge
        cand = [by_path[s]["phase"] for s in implements.get(r["path"], [])
                if by_path.get(s, {}).get("phase")]
        return min(cand, key=lambda p: _phase_key(p) or ("", 0, "")) if cand else None

    inits, unphased = {}, []
    for r in records:
        if not r["catalog"] or r["type"] not in ("product-spec", "exec-plan"):
            continue
        row = {"path": r["path"], "type": r["type"], "status": r["status"],
               "phase": phase_of(r), "pivots": sorted(pivots.get(r["path"], []))}
        key = _phase_key(row["phase"])
        if key is None:
            unphased.append(row)
            continue
        init, order, label = key
        ph = inits.setdefault(init, {}).setdefault(label, {"order": order, "items": []})
        ph["items"].append(row)

    def item_sort(x):  # specs before the plans that implement them, then by path
        return (x["type"] != "product-spec", x["path"])

    out = []
    for init in sorted(inits):
        phases = [{"phase": label, "order": blk["order"],
                   "items": sorted(blk["items"], key=item_sort)}
                  for label, blk in sorted(inits[init].items(),
                                           key=lambda kv: (kv[1]["order"], kv[0]))]
        out.append({"initiative": init, "phases": phases})
    return {"initiatives": out, "unphased": sorted(unphased, key=item_sort)}


def charter_map(records, followup_counts=None):
    """Charter-rooted unified map: the Big Picture (the `charter` page) -> each
    initiative it anchors -> that initiative's roadmap (phases -> specs/plans ->
    pivots). It composes `roadmap()` (phase grouping) with the charter's outbound
    `charters` edges (the initiative anchors): an initiative is *anchored* when the
    charter links a `product-spec` whose `phase` initiative it is. Initiatives in
    the roadmap that no charter link anchors are surfaced separately (so a drift
    between the authored charter and the derived initiative set is visible, not
    hidden). Pure projection, fail-soft (no charter -> everything unanchored).

    `followup_counts` (optional {node_path: count}) annotates each item with a
    `followups` count for the map's drill-down badge (the rows live behind
    `followups`, never inlined here).

    Returns {charter, initiatives: [{…roadmap block…, anchored, anchor}], unphased}."""
    fc = followup_counts or {}
    rm = roadmap(records)
    by_path = {r["path"]: r for r in records}
    charter = next((r for r in records if r.get("type") == "charter"), None)
    anchor = {}  # initiative name -> the charter-linked product-spec anchoring it
    if charter:
        for dst in charter["links"]:
            d = by_path.get(dst, {})
            key = _phase_key(d.get("phase")) if d.get("type") == "product-spec" else None
            if key:
                anchor.setdefault(key[0], dst)
    for b in rm["initiatives"]:
        for ph in b["phases"]:
            for it in ph["items"]:
                it["followups"] = fc.get(it["path"], 0)
    for it in rm["unphased"]:
        it["followups"] = fc.get(it["path"], 0)
    inits = [{**b, "anchored": b["initiative"] in anchor,
              "anchor": anchor.get(b["initiative"])} for b in rm["initiatives"]]
    inits.sort(key=lambda b: (not b["anchored"], b["initiative"]))  # anchored first
    return {"charter": charter["path"] if charter else None,
            "initiatives": inits, "unphased": rm["unphased"]}


def _emit_map(m, as_json):
    if as_json:
        print(json.dumps(m, indent=2, ensure_ascii=False))
        return
    print(f"charter: {_slug(m['charter']) if m['charter'] else '(none)'}")
    for b in m["initiatives"]:
        flag = "" if b["anchored"] else "   (⚠ not anchored in charter)"
        print(f"  # {b['initiative']}{flag}")
        for ph in b["phases"]:
            print(f"    {ph['phase'] or '(umbrella)'}")
            for row in ph["items"]:
                print(f"      {_map_row(row)}")
    if m["unphased"]:
        print("  # (unphased)")
        for row in m["unphased"]:
            print(f"      {_map_row(row)}")
    anchored = sum(1 for b in m["initiatives"] if b["anchored"])
    print(f"# {anchored}/{len(m['initiatives'])} initiative(s) anchored in the "
          f"charter — derived, advisory")


def _tracker_rows(text):
    """Yield (source_cell, summary, severity, status) for each data row of the
    tech-debt table. A data row is a `|`-delimited line with >=5 cells that is not
    the header or the `---` separator. Tolerant — a non-table line is skipped."""
    rows = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 5:
            continue
        item = cells[0]
        if item == "Item" or set(item) <= set("-: "):  # header / separator
            continue
        rows.append((cells[3], item, cells[1], cells[4]))  # Source, Item, Severity, Status
    return rows


def followups(records, root, node=None):
    """Tech-debt rows grouped by the source node they derive from (the drill-down
    layer for the high-volume follow-up tier — kept out of the overview, surfaced
    here on demand). Parses the `tech-debt-tracker.md` table; the source is the
    first `.md` link in a row's Source cell, resolved to a repo path. A row with no
    source link lands in `(unsourced)`. With `node`, returns only that node's
    group. Pure read; fail-soft (no tracker / unparseable row -> skipped)."""
    root = Path(root).resolve()
    tracker = next((r for r in records if r.get("type") == "tracker"
                    or r["path"].endswith("tech-debt-tracker.md")), None)
    groups = {}
    if tracker:
        tpath = root / tracker["path"]
        text = tpath.read_text(encoding="utf-8", errors="replace")
        for source_cell, summary, severity, status in _tracker_rows(text):
            srcs = _resolve_links(tpath, root, hl.links_in(source_cell))
            key = srcs[0] if srcs else "(unsourced)"
            groups.setdefault(key, []).append(
                {"source": None if key == "(unsourced)" else key,
                 "summary": summary[:80], "severity": severity, "status": status})
    if node is not None:
        nkey = _norm(node, root)
        return {nkey: groups.get(nkey, [])}
    return groups


def _emit_followups(groups, as_json):
    if as_json:
        print(json.dumps(groups, indent=2, ensure_ascii=False))
        return
    total = 0
    for src in sorted(groups):
        rows = groups[src]
        total += len(rows)
        print(f"# {src if src == '(unsourced)' else _slug(src)}  ({len(rows)})")
        for r in rows:
            print(f"    [{r['status']}] {r['summary']}")
    print(f"# {total} follow-up(s) — advisory")


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


def _roadmap_row(row):
    s = f"[{row['status'] or '-'}]  {row['type']}: {_slug(row['path'])}"
    for rel, other in row["pivots"]:
        s += f"  [{rel} {_slug(other)}]"
    return s


def _map_row(row):
    """A roadmap row plus the follow-up count badge (map only — a sparse glanceable
    signal; the rows themselves stay behind `followups <node>`)."""
    s = _roadmap_row(row)
    n = row.get("followups", 0)
    return s + (f"  [{n} follow-up{'s' if n != 1 else ''}]" if n else "")


def _emit_roadmap(rm, as_json):
    if as_json:
        print(json.dumps(rm, indent=2, ensure_ascii=False))
        return
    for blk in rm["initiatives"]:
        print(f"# {blk['initiative']}")
        for ph in blk["phases"]:
            print(f"  {ph['phase'] or '(umbrella)'}")
            for row in ph["items"]:
                print(f"    {_roadmap_row(row)}")
        print()
    if rm["unphased"]:
        print("# (unphased)")
        for row in rm["unphased"]:
            print(f"  {_roadmap_row(row)}")
        print()
    total = (sum(len(p["items"]) for b in rm["initiatives"] for p in b["phases"])
             + len(rm["unphased"]))
    print(f"# {len(rm['initiatives'])} initiative(s), {total} page(s) — derived, advisory")


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
    mp = sub.add_parser("roadmap",
                        help="derived progress map: initiative -> phase -> status")
    mp.add_argument("--json", action="store_true", help="emit JSON")
    cm = sub.add_parser("map",
                        help="charter-rooted unified map: charter -> initiatives -> roadmap")
    cm.add_argument("--json", action="store_true", help="emit JSON")
    fp = sub.add_parser("followups",
                        help="tech-debt rows grouped by the source node they derive from")
    fp.add_argument("node", nargs="?", help="repo-relative node path (omit for all)")
    fp.add_argument("--json", action="store_true", help="emit JSON")
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
    elif args.cmd == "roadmap":
        _emit_roadmap(roadmap(records), args.json)
    elif args.cmd == "map":
        fups = followups(records, root)
        counts = {k: len(v) for k, v in fups.items() if k != "(unsourced)"}
        _emit_map(charter_map(records, counts), args.json)
    elif args.cmd == "followups":
        _emit_followups(followups(records, root, args.node), args.json)


if __name__ == "__main__":
    main()
