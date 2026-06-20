#!/usr/bin/env python3
"""Taste lints for the tiered docs knowledge base.

Every FAIL message includes a FIX instruction: lint output is injected into
agent context, so errors double as corrective signals (core-beliefs).
Self-host is strict; ported hosts keep machine-critical docs and
product-specs strict while additional project-specific docs stay host-owned
unless opted into governance.
Exit 0 = green; exit 1 = at least one FAIL.
"""
import re
import sys

import harness_lib as hl

STALE_DAYS = hl.STALE_DAYS  # the one default lives in harness_lib (shared with nav)
FM_REQUIRED = ("status", "last_verified", "owner")
INDEXED_DIRS = ("adr", "design-docs", "product-specs", "references")
HOST_INDEXED_DIRS = ("adr", "design-docs", "product-specs")
# Relaxed-mode content-governed roots. `generated/` is intentionally absent:
# generated pages are frontmatter-exempt and guarded from .harnessignore
# un-governance separately — cf. hl.MANAGED_ROOTS, which DOES include it.
HOST_MANAGED_ROOTS = ("adr", "design-docs", "exec-plans", "product-specs")
FM_EXEMPT = hl.DOC_EXEMPT  # the shared exempt set (one definition in harness_lib)
MACHINE_DOCS = (  # docs the machine reads — D10; scaffold.py seeds all of them
    "ARCHITECTURE.md", "docs/PLANS.md", "docs/DESIGN.md",
    "docs/KNOWLEDGE_FORMAT.md",
    "docs/QUALITY_SCORE.md", "docs/PRODUCT_SENSE.md", "docs/RELIABILITY.md",
    "docs/SECURITY.md", "docs/design-docs/agent-harness.md",
)
# Harness docs whose D4 staleness a host override may only TIGHTEN, never
# loosen (SECURITY T8/T9 — a host can't .harness.json its own critical docs into
# rot). Keyed by repo-relative PATH, not bare name, so it can't wrongly protect a
# host's unrelated docs/x/SECURITY.md.
PROTECTED_PATHS = frozenset("docs/" + n for n in hl.MANAGED_DOCS)
KEBAB = re.compile(r"^[a-z0-9][a-z0-9.-]*\.md$")
UPPER = re.compile(r"^[A-Z_]+\.md$")
# Canonical `phase` grammar (D12): `<initiative>` or `<initiative>/<NN>-<slug>`,
# NN numeric. nav tolerates looser values (sorts them last); the gate is canonical.
PHASE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*(/[0-9]+-[a-z0-9-]+)?$")
# Navigation keys promoted to checked rules at KF v2.0 (the governance flip):
# presence-required (blanket) + phase-required on this type.
NAV_REQUIRED = ("type", "description")
PHASE_REQUIRED_TYPES = ("product-spec",)
# LINK / staleness now live in harness_lib (the one definition shared with
# nav.py) — see hl.links_in / hl.is_stale.


def _fail(errors, rule, path, problem, fix):
    errors.append(f"FAIL {rule} {path}: {problem} FIX: {fix}")


def _rel(p, root):
    return p.relative_to(root).as_posix()


def _exempt(p, docs, parts):
    # Segment-boundary match (never bare substring) lives in harness_lib so the
    # gate and nav.py share one definition (core-belief 5 / S1).
    return hl.is_exempt(p.relative_to(docs).as_posix(), parts)


def _strict_doc_governance(root, cfg=None, plugin=None):
    cfg = cfg or {}
    return hl.is_self_host(root, plugin) or cfg.get("doc_governance") == "strict"


def _managed_roots(cfg=None):
    """Docs-relative roots governed in relaxed host mode.

    The harness owns the minimum substrate by default. Additional
    host/project-specific roots (for example `business/` or `marketing/`)
    become governed only when the host opts them in through `.harness.json`
    `managed_doc_roots`.
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


def check_entrypoints(root, errors):
    agents = root / "AGENTS.md"
    if not agents.exists():
        _fail(errors, "D1", "AGENTS.md", "missing.",
              "Create AGENTS.md: a ~100-line map (operating model + docs/ pointers).")


def check_frontmatter(root, errors, host=(), stale_days=STALE_DAYS, cfg=None):
    docs = root / "docs"
    for p in hl.iter_md(docs):
        if _exempt(p, docs, FM_EXEMPT + host):
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
            sd = stale_days
            if p.relative_to(root).as_posix() in PROTECTED_PATHS:
                sd = min(sd, STALE_DAYS)  # override may only tighten managed docs
            try:
                if hl.is_stale(lv, sd, fm.get("status")):
                    _fail(errors, "D4", _rel(p, root),
                          f"stale: last_verified {lv} is over {sd} days old.",
                          "Re-read the page against reality; fix or retire content, then bump last_verified.")
            except (ValueError, TypeError):
                # TypeError: a required key authored as a YAML list (the
                # list-aware parser returns a list) — degrade to a clean D4 FAIL,
                # never crash the gate. str() keeps the message safe for non-str lv.
                _fail(errors, "D4", _rel(p, root), f"bad last_verified `{str(lv)[:40]}`.",
                      "Use a scalar ISO date YYYY-MM-DD (not a list).")
        # Navigation keys (D11/D12) govern CONTENT pages, not reserved spines: an
        # index.md is itself a listing (not a navigable concept-page) — it still
        # gets D3/D4/D8, but not the nav-key contract. Mirrors nav.py RESERVED.
        if p.name == "index.md":
            continue
        # D11 — required navigation keys (KF v2.0 governance flip): type +
        # description blanket; phase required on the work-tier anchor (product-spec
        # — plans inherit phase via the `implements` edge, so it is not required
        # on exec-plans).
        for k in NAV_REQUIRED:
            v = fm.get(k)
            if not (isinstance(v, str) and v.strip()):
                _fail(errors, "D11", _rel(p, root),
                      f"frontmatter lacks a non-empty `{k}` (required navigation key).",
                      f"Add `{k}:` — every governed page declares its kind and a one-line summary (KF v2.0).")
        if fm.get("type") in PHASE_REQUIRED_TYPES and not (
                isinstance(fm.get("phase"), str) and fm["phase"].strip()):
            _fail(errors, "D11", _rel(p, root), f"`{fm.get('type')}` lacks `phase`.",
                  "Add `phase: <initiative>/<NN>-<slug>` — it anchors the roadmap (plans inherit; KF v2.0).")
        # D12 — validate-if-present (never presence-required): resource path exists,
        # supersedes targets resolve (D5-style), phase is well-formed.
        res = fm.get("resource")
        if isinstance(res, str) and res and not res.startswith(("http://", "https://")):
            if not ((p.parent / res).exists() or (root / res).exists()):
                _fail(errors, "D12", _rel(p, root), f"`resource` path `{res}` does not exist.",
                      "Point `resource` at a real repo-relative path (or a URL), or remove it.")
        sup = fm.get("supersedes")
        for t in (sup if isinstance(sup, list) else [sup]):
            if not (isinstance(t, str) and t) or t.startswith(("http://", "https://")):
                continue
            if not ((p.parent / t).exists() or (root / t).exists()):
                _fail(errors, "D12", _rel(p, root), f"`supersedes` target `{t}` does not resolve.",
                      "Point `supersedes` at a real .md page, or remove it.")
        ph = fm.get("phase")
        if isinstance(ph, str) and ph.strip() and not PHASE_RE.match(ph.strip()):
            _fail(errors, "D12", _rel(p, root), f"malformed `phase` `{ph}`.",
                  "Use `<initiative>` or `<initiative>/<NN>-<slug>` (NN numeric).")


def check_links(root, errors, host=(), cfg=None):
    docs = root / "docs"
    targets = [p for p in hl.iter_md(docs)
               if not _exempt(p, docs, FM_EXEMPT + host)
               and _governed_doc(p, root, docs, cfg)]
    for name in ("AGENTS.md", "ARCHITECTURE.md"):
        if (root / name).exists():
            targets.append(root / name)
    docs_abs = docs.resolve()
    for p in targets:
        text = p.read_text(encoding="utf-8")
        for t in hl.links_in(text):
            if t.startswith(("http://", "https://")):
                continue
            if (p.parent / t).exists() or (root / t).exists():
                continue
            # A broken link whose target resolves UNDER a `.harnessignore`'d (exempt)
            # docs tree is EXTERNAL to the gate, not a broken-corpus link: that tree is
            # deliberately unmanaged (e.g. the vendored, .gitignored `symphony-original/`
            # oracle), so it is absent in any fresh clone. Checking links into it would
            # fail the gate on every clone/ported host (use-all shakedown F8). Total over
            # an unresolvable path (resolve/relative_to wrapped) — R22.
            if any(_under_exempt(cand, docs_abs, host)
                   for cand in (p.parent / t, root / t)):
                continue
            _fail(errors, "D5", _rel(p, root), f"broken link `{t}`.",
                  "Fix the relative path or create the target page.")


def _under_exempt(cand, docs_abs, exempt) -> bool:
    """True iff `cand` resolves to a path under the `docs/` tree that `is_exempt`
    (a `.harnessignore`'d subtree). Total: any unresolvable/out-of-docs path → False."""
    try:
        rel = cand.resolve().relative_to(docs_abs).as_posix()
    except (ValueError, OSError):
        return False
    return hl.is_exempt(rel, exempt)


def check_naming(root, errors, host=(), cfg=None):
    docs = root / "docs"
    for p in hl.iter_md(docs):
        if _exempt(p, docs, FM_EXEMPT + host):
            continue
        if not _governed_doc(p, root, docs, cfg):
            continue
        ok = (KEBAB.match(p.name)
              or (p.parent == docs and UPPER.match(p.name)))
        if not ok:
            _fail(errors, "D6", _rel(p, root), "filename is not kebab-case.",
                  "Rename to lowercase-kebab-case.md (top-level docs/ taste docs may be UPPERCASE.md).")


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
    stale_days = _int_or(cfg.get("stale_days"), STALE_DAYS)
    errors = []
    check_entrypoints(root, errors)
    check_machine_refs(root, errors)
    check_frontmatter(root, errors, host, stale_days, cfg)
    check_links(root, errors, host, cfg)
    check_naming(root, errors, host, cfg)
    check_indexes(root, errors, cfg)
    check_coverage(root, errors, hl.plugin_root(), cfg)
    for e in errors:
        print(e)
    print(f"lint_docs: {'OK' if not errors else str(len(errors)) + ' FAIL'}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
