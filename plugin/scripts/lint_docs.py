#!/usr/bin/env python3
"""Taste lints for the tiered docs knowledge base.

Every FAIL message includes a FIX instruction: lint output is injected into
agent context, so errors double as corrective signals (core-beliefs).
Self-host is strict; ported hosts keep machine-critical docs strict while
project-specific docs stay host-owned unless opted into governance.
Exit 0 = green; exit 1 = at least one FAIL.
"""
import datetime
import re
import sys

import harness_lib as hl

STALE_DAYS = 30
FM_REQUIRED = ("status", "last_verified", "owner")
INDEXED_DIRS = ("design-docs", "product-specs", "references",
                "memory/adr", "memory/knowledge", "memory/openq",
                "memory/limitations")
HOST_INDEXED_DIRS = ("design-docs", "memory/adr", "memory/knowledge",
                     "memory/openq", "memory/limitations")
# Relaxed-mode content-governed roots. `generated/` is intentionally absent: it
# is content-lint-exempt (FM_EXEMPT/SIZE_EXEMPT) and guarded from .harnessignore
# un-governance separately — cf. hl.MANAGED_ROOTS, which DOES include it. Do not
# "reconcile" the two tuples; the one-element divergence is by design.
HOST_MANAGED_ROOTS = ("design-docs", "exec-plans", "memory")
SIZE_LIMITS = {"AGENTS.md": 120, "MEMORY.md": 60}
DEFAULT_LIMIT = 400
FM_EXEMPT = ("generated/", "superpowers/")
SIZE_EXEMPT = ("generated/", "superpowers/", "exec-plans/", "references/")
MACHINE_DOCS = (  # docs the machine reads — D10; scaffold.py seeds all of them
    "ARCHITECTURE.md", "docs/PLANS.md", "docs/DESIGN.md",
    "docs/QUALITY_SCORE.md", "docs/PRODUCT_SENSE.md", "docs/RELIABILITY.md",
    "docs/SECURITY.md", "docs/design-docs/agent-harness.md",
)
# Harness docs whose D7 cap / D4 staleness a host override may only TIGHTEN,
# never loosen (SECURITY T8/T9 — a host can't .harness.json its own critical
# docs into rot/bloat). Keyed by repo-relative PATH, not bare name: the memory
# bootloader lives at docs/memory/MEMORY.md (not docs/ top level), and keying by
# name would also wrongly protect a host's unrelated docs/x/SECURITY.md.
PROTECTED_PATHS = frozenset(
    ["docs/" + n for n in hl.MANAGED_DOCS] + ["docs/memory/MEMORY.md"])
KEBAB = re.compile(r"^[a-z0-9][a-z0-9.-]*\.md$")
UPPER = re.compile(r"^[A-Z_]+\.md$")
LINK = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)\s]*)?\)")


def _fail(errors, rule, path, problem, fix):
    errors.append(f"FAIL {rule} {path}: {problem} FIX: {fix}")


def _rel(p, root):
    return p.relative_to(root).as_posix()


def _exempt(p, docs, parts):
    # Match on path-segment boundaries, never bare substring: an entry `business`
    # exempts the `business/` tree and the file `business`, but NOT a sibling
    # `business-plan.md`. This is what stops a partial prefix (`mem`) from
    # reaching `memory/…` and what makes the trailing `/` optional/forgiving.
    rel = p.relative_to(docs).as_posix()
    return any(rel == x or rel.startswith(x.rstrip("/") + "/") for x in parts)


def _strict_doc_governance(root, cfg=None, plugin=None):
    cfg = cfg or {}
    return hl.is_self_host(root, plugin) or cfg.get("doc_governance") == "strict"


def _managed_roots(cfg=None):
    """Docs-relative roots governed in relaxed host mode.

    The harness owns the minimum substrate by default. Host/project-specific
    roots (for example `business/` or `marketing/`) become governed only when
    the host opts them in through `.harness.json` `managed_doc_roots`.
    """
    cfg = cfg or {}
    roots = list(HOST_MANAGED_ROOTS)
    extra = cfg.get("managed_doc_roots")
    if isinstance(extra, list):
        for item in extra:
            if not isinstance(item, str):
                continue
            segs = [seg for seg in item.split("/") if seg and seg != "."]
            norm = "/".join(segs)
            if norm and norm not in roots:
                roots.append(norm)
    return tuple(roots)


def _machine_doc(p, root):
    try:
        rel = p.relative_to(root).as_posix()
    except ValueError:
        return False
    return rel in MACHINE_DOCS or rel in PROTECTED_PATHS


def _governed_doc(p, root, docs, cfg=None, plugin=None):
    """Whether content-style lints should block on this docs/ page."""
    if _strict_doc_governance(root, cfg, plugin):
        return True
    if _machine_doc(p, root):
        return True
    rel = p.relative_to(docs).as_posix()
    return any(rel == x or rel.startswith(x.rstrip("/") + "/")
               for x in _managed_roots(cfg))


def check_entrypoints(root, errors, limits=None):
    limits = limits or SIZE_LIMITS
    cap = limits.get("AGENTS.md", SIZE_LIMITS["AGENTS.md"])
    agents = root / "AGENTS.md"
    if not agents.exists():
        _fail(errors, "D1", "AGENTS.md", "missing.",
              "Create AGENTS.md: a ~100-line map (operating model + docs/ pointers).")
        return
    n = len(agents.read_text(encoding="utf-8").splitlines())
    if n > cap:
        _fail(errors, "D1", "AGENTS.md",
              f"{n} lines (max {cap}).",
              "AGENTS.md is a map, not an encyclopedia: move detail into docs/ and link it.")


def check_frontmatter(root, errors, host=(), stale_days=STALE_DAYS, cfg=None):
    docs = root / "docs"
    for p in hl.iter_md(docs):
        if _exempt(p, docs, FM_EXEMPT + host) or p.name == "MEMORY.md":
            continue
        if not _governed_doc(p, root, docs, cfg):
            continue
        fm = hl.read_frontmatter(p)
        if fm is None:
            _fail(errors, "D3", _rel(p, root), "missing or unterminated frontmatter.",
                  "Add `---` frontmatter with status, last_verified (YYYY-MM-DD), owner.")
            continue
        for k in FM_REQUIRED:
            if k not in fm:
                _fail(errors, "D3", _rel(p, root), f"frontmatter lacks `{k}`.",
                      f"Add `{k}:` to the frontmatter block.")
        lv = fm.get("last_verified", "")
        if "last_verified" in fm:
            try:
                d = datetime.date.fromisoformat(lv)
                sd = stale_days
                if p.relative_to(root).as_posix() in PROTECTED_PATHS:
                    sd = min(sd, STALE_DAYS)  # override may only tighten managed docs
                stale = (hl.today() - d).days > sd
                if stale and fm.get("status") not in ("archived", "completed"):
                    _fail(errors, "D4", _rel(p, root),
                          f"stale: last_verified {lv} is over {sd} days old.",
                          "Re-read the page against reality; fix or retire content, then bump last_verified.")
            except ValueError:
                _fail(errors, "D4", _rel(p, root), f"bad last_verified `{lv[:40]}`.",
                      "Use ISO format YYYY-MM-DD.")


def check_links(root, errors, host=(), cfg=None):
    docs = root / "docs"
    targets = [p for p in hl.iter_md(docs)
               if not _exempt(p, docs, FM_EXEMPT + host)
               and _governed_doc(p, root, docs, cfg)]
    for name in ("AGENTS.md", "ARCHITECTURE.md"):
        if (root / name).exists():
            targets.append(root / name)
    for p in targets:
        text = p.read_text(encoding="utf-8")
        for m in LINK.finditer(text):
            t = m.group(1)
            if t.startswith(("http://", "https://")):
                continue
            if not ((p.parent / t).exists() or (root / t).exists()):
                _fail(errors, "D5", _rel(p, root), f"broken link `{t}`.",
                      "Fix the relative path or create the target page.")


def check_naming(root, errors, host=(), cfg=None):
    docs = root / "docs"
    for p in hl.iter_md(docs):
        if _exempt(p, docs, FM_EXEMPT + host):
            continue
        if not _governed_doc(p, root, docs, cfg):
            continue
        ok = (KEBAB.match(p.name) or p.name == "MEMORY.md"
              or (p.parent == docs and UPPER.match(p.name)))
        if not ok:
            _fail(errors, "D6", _rel(p, root), "filename is not kebab-case.",
                  "Rename to lowercase-kebab-case.md (top-level docs/ taste docs may be UPPERCASE.md).")


def check_sizes(root, errors, host=(), limits=None, default_limit=DEFAULT_LIMIT,
                cfg=None):
    limits = limits or SIZE_LIMITS
    default_limit = _int_or(default_limit, DEFAULT_LIMIT)  # robust to direct calls
    docs = root / "docs"
    for p in hl.iter_md(docs):
        if _exempt(p, docs, SIZE_EXEMPT + host):
            continue
        if not _governed_doc(p, root, docs, cfg):
            continue
        limit = _int_or(limits.get(p.name, default_limit), default_limit)
        if p.relative_to(root).as_posix() in PROTECTED_PATHS:
            limit = min(limit, SIZE_LIMITS.get(p.name, DEFAULT_LIMIT))  # tighten-only
        n = len(p.read_text(encoding="utf-8").splitlines())
        if n > limit:
            _fail(errors, "D7", _rel(p, root), f"{n} lines (max {limit}).",
                  "Split the page or move detail to a linked sub-page; bootloaders stay terse.")


def check_indexes(root, errors, cfg=None):
    docs = root / "docs"
    cats = INDEXED_DIRS if _strict_doc_governance(root, cfg) else HOST_INDEXED_DIRS
    for cat in cats:
        d = docs / cat
        if not d.is_dir() or not any(d.glob("*.md")):
            continue
        idx = d / "index.md"
        if not idx.exists():
            _fail(errors, "D8", f"docs/{cat}/", "category lacks index.md.",
                  f"Create docs/{cat}/index.md cataloguing every page in the category.")
            continue
        text = idx.read_text(encoding="utf-8")
        for f in sorted(d.glob("*.md")):
            if f.name != "index.md" and f.name not in text:
                _fail(errors, "D8", _rel(f, root), "not registered in its index.md.",
                      f"Add `{f.name}` (with a one-line description) to docs/{cat}/index.md.")


def check_coverage(root, errors, plugin, cfg=None):
    cfg = cfg or {}
    if not (_strict_doc_governance(root, cfg, plugin)
            or cfg.get("component_coverage") == "strict"):
        return
    names = []
    for sk in sorted((plugin / "skills").glob("*/SKILL.md")):
        names.append(sk.parent.name)
    for ag in sorted((plugin / "agents").glob("*.md")):
        names.append(ag.stem)
    hay = ""
    if (root / "AGENTS.md").exists():
        hay += (root / "AGENTS.md").read_text(encoding="utf-8")
    docs = root / "docs"
    for p in hl.iter_md(docs):
        if not _exempt(p, docs, ("generated/", "superpowers/")):
            hay += p.read_text(encoding="utf-8")
    for name in names:
        if name not in hay:
            _fail(errors, "D9", f"plugin component `{name}`",
                  "not mentioned anywhere in AGENTS.md or docs/.",
                  f"Document `{name}` (at minimum: one line in AGENTS.md map or docs/DESIGN.md).")


def check_machine_refs(root, errors):
    for rel in MACHINE_DOCS:
        if not (root / rel).exists():
            _fail(errors, "D10", rel,
                  "missing — the machine reads this doc (execplan gate / review personas / doc-gardener).",
                  "Seed it: run scaffold.py (harness-init skill), or create the page from its template in the skill's templates/.")


def _int_or(value, default):
    # bool is an int subclass — exclude it so `true` in JSON can't pass as 1.
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def main():
    root = hl.repo_root()
    host = hl.exempt_roots(root)  # host-declared legacy doc roots (docs/.harnessignore)
    cfg = hl.gate_config(root)  # per-repo threshold overrides (.harness.json)
    limits = dict(SIZE_LIMITS)
    ov = cfg.get("size_limits")
    if isinstance(ov, dict):
        for k, v in ov.items():
            if isinstance(k, str):
                limits[k] = _int_or(v, limits.get(k, DEFAULT_LIMIT))
    default_limit = _int_or(cfg.get("default_size_limit"), DEFAULT_LIMIT)
    stale_days = _int_or(cfg.get("stale_days"), STALE_DAYS)
    errors = []
    check_entrypoints(root, errors, limits)
    check_machine_refs(root, errors)
    check_frontmatter(root, errors, host, stale_days, cfg)
    check_links(root, errors, host, cfg)
    check_naming(root, errors, host, cfg)
    check_sizes(root, errors, host, limits, default_limit, cfg)
    check_indexes(root, errors, cfg)
    check_coverage(root, errors, hl.plugin_root(), cfg)
    for e in errors:
        print(e)
    print(f"lint_docs: {'OK' if not errors else str(len(errors)) + ' FAIL'}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
