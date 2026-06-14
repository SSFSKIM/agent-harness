#!/usr/bin/env python3
"""docs-sync applicator (M1 safety core): UPDATE/RETRACT curated docs safely.

The dreaming router only APPENDS; docs-sync adds EDIT/DELETE so the harness can
keep curated docs (AGENTS.md / ARCHITECTURE.md / design-docs) CURRENT and RETRACT
content a dropped session authored. Editing curated prose is the risky NEW
capability, so this module is the load-bearing safety core — built and proven in
isolation BEFORE the audit agent (M3) that proposes the edits exists.

Containment by construction (the whole safety story):
  - The audit agent (M3) only PROPOSES a maintenance plan (JSON); it writes nothing.
  - This DETERMINISTIC applicator is the ONLY writer. It RE-VALIDATES every item's
    risk itself (never trusting the agent's `risk` label) and AUTO-APPLIES ONLY the
    four MECHANICAL kinds, by matching each item's structured `change` against a
    fixed template:
      1. regenerate a generator-owned file  (run the registered generator)
      2. set an allowlisted frontmatter field (`last_verified` / `status`, pattern-checked)
      3. a verbatim token-rename swap         (old & new are plain symbols, old found exactly)
      4. a retract DELETE attributable to machine-authored content via journal
         `[routed]` provenance
    Everything else — any free-prose rewrite, an unattributable delete, an unknown
    op — is forced to the REPORT. The machine never auto-edits curated prose.
  - Every write target is a curated doc resolved through the shared symlink-safe
    within-repo guard (`harness_lib.within_repo_no_symlink`), so a symlinked doc
    cannot redirect a write outside the repo.
  - After applying, `check.py` is re-run; a RED gate rolls the WHOLE batch back to
    its pre-edit bytes. An applied edit can never leave the repo un-green.

A plan item (emitted by the M3 audit agent) is:
    {"target": "docs/...md", "kind": "missing|outdated|retract|structural",
     "evidence": "file:line proving the gap", "change": {<structured op>},
     "risk": "mechanical|semantic"}   # risk is the agent's label — UNTRUSTED here
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import harness_lib as hl

# Generated files docs-sync may regenerate: repo-relative target -> generator
# argv (script name in scripts/, plus any args). The content comes from the
# deterministic generator, NEVER the agent — so "regenerate" carries no prose risk.
GENERATED_TARGETS = {
    "docs/generated/component-inventory.md": ["gen_inventory.py"],
}
# Frontmatter fields the machine may set, each with the only value shape allowed.
SAFE_FRONTMATTER = {
    "last_verified": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    "status": re.compile(r"^(stub|draft|stable)$"),
}
# A plain symbol/path token — a rename swaps these, never prose. No whitespace.
SYMBOL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_./-]{0,79}$")
ROOT_DOCS = ("AGENTS.md", "ARCHITECTURE.md")     # root map docs docs-sync maintains
JOURNAL_DIR = "docs/journal"
# A journal provenance line: `[routed] <type> "<snippet>" -> docs/X`
ROUTED_RE = re.compile(r"\[routed\]\s+.*?\"([^\"]*)\".*?->\s*(\S+)")


def _scripts_dir():
    return Path(__file__).resolve().parent


# ---- the docs allowlist + structured-change helpers ------------------------

def resolve_doc_target(root, target):
    """The docs allowlist: an EXISTING `.md` under docs/ (or a root map doc),
    symlink-safe and inside the repo. Returns the path or None."""
    if not target or not isinstance(target, str):
        return None
    rel = os.path.normpath(target)
    if os.path.isabs(rel) or rel.startswith(".."):
        return None
    if not rel.endswith(".md"):
        return None
    first = rel.split(os.sep, 1)[0]
    if not (first == "docs" or rel in ROOT_DOCS):
        return None
    p = hl.within_repo_no_symlink(root, rel)
    return p if (p is not None and p.is_file()) else None


def _boundary_re(tok):
    """Match `tok` only as a whole token (not inside a larger identifier/path), so
    a rename of `docs/memory` can never corrupt `docs/memory-architecture`."""
    return re.compile(r"(?<![A-Za-z0-9_./-])" + re.escape(tok) + r"(?![A-Za-z0-9_./-])")


def _rename_count(text, old):
    return len(_boundary_re(old).findall(text))


def _line_present(text, line):
    want = line.strip()
    return any(l.strip() == want for l in text.splitlines())


def _set_frontmatter(text, field, value):
    """Return `text` with frontmatter `field` set to `value`, or None if there is
    no `---`…`---` block. Only ever touches the frontmatter, never the body."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return None
    for i in range(1, end):
        if ":" in lines[i] and lines[i].split(":", 1)[0].strip() == field:
            lines[i] = f"{field}: {value}"
            break
    else:
        lines.insert(end, f"{field}: {value}")
    out = "\n".join(lines)
    return out + "\n" if text.endswith("\n") else out


def _attributable(root, target, line):
    """True iff a journal `[routed] ... "snippet" -> target` line exists whose
    snippet is contained in `line` — i.e. the content being deleted was machine-
    authored INTO this target, so deleting it reverses a router append rather than
    editing human prose. Ties the delete to the specific routed content, not just
    the file (the router records a truncated snippet, which is a prefix of the line
    it appended)."""
    rel = os.path.normpath(str(target))
    norm_line = re.sub(r"\s+", " ", line).strip()
    base = Path(root) / JOURNAL_DIR
    if not base.exists():
        return False
    for jf in sorted(base.rglob("*.md")):
        try:
            jtext = jf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for jl in jtext.splitlines():
            m = ROUTED_RE.search(jl)
            if not m:
                continue
            snippet = re.sub(r"\s+", " ", m.group(1)).strip()
            if os.path.normpath(m.group(2)) == rel and snippet and snippet in norm_line:
                return True
    return False


# ---- the deterministic risk re-validator (the safety crux) -----------------

def classify(root, item):
    """Re-validate one item's risk WITHOUT trusting its `risk` label. Returns
    ("mechanical", prepared_op) if the structured `change` matches a mechanical
    template exactly, else ("report", reason). This is the only place that decides
    what auto-applies — so a prose rewrite mislabeled `mechanical` cannot slip
    through."""
    change = item.get("change")
    if not isinstance(change, dict):
        return ("report", "no structured change — needs a human edit")
    op = change.get("op")
    target = item.get("target")

    if op == "regenerate":
        if target in GENERATED_TARGETS:
            return ("mechanical", {"op": "regenerate", "target": target})
        return ("report", "regenerate target is not a registered generated file")

    path = resolve_doc_target(root, target)
    if path is None:
        return ("report", f"unresolved or out-of-allowlist target {target!r}")
    text = path.read_text(encoding="utf-8", errors="replace")

    if op == "set_frontmatter":
        field, value = change.get("field"), change.get("value")
        pat = SAFE_FRONTMATTER.get(field) if isinstance(field, str) else None
        if pat is None or not isinstance(value, str) or not pat.match(value):
            return ("report", "frontmatter field/value not in the mechanical allowlist")
        if _set_frontmatter(text, field, value) is None:
            return ("report", "no frontmatter block to set the field in")
        return ("mechanical", {"op": "set_frontmatter", "path": path,
                               "field": field, "value": value})

    if op == "rename":
        old, new = change.get("old"), change.get("new")
        if not (isinstance(old, str) and isinstance(new, str)
                and SYMBOL_RE.match(old) and SYMBOL_RE.match(new) and old != new):
            return ("report", "rename old/new are not plain symbols")
        if _rename_count(text, old) == 0:
            return ("report", f"rename old {old!r} not found verbatim in target")
        return ("mechanical", {"op": "rename", "path": path, "old": old, "new": new})

    if op == "retract":
        line = change.get("line")
        if not isinstance(line, str) or not line.strip():
            return ("report", "retract needs the exact line to delete")
        if not _line_present(text, line):
            return ("report", "retract line not found verbatim in target")
        if not _attributable(root, target, line):
            return ("report", "retract has no journal [routed] provenance — not machine-authored")
        return ("mechanical", {"op": "retract", "path": path, "line": line})

    return ("report", f"unknown or non-mechanical op {op!r}")


# ---- the applicator (the only writer) --------------------------------------

def run_check(root):
    """Re-run the deterministic gate against `root`. True iff GREEN. Injectable in
    tests (the synthetic fixtures are not full harness repos)."""
    proc = subprocess.run(
        [sys.executable, str(_scripts_dir() / "check.py"), "--root", str(root)],
        cwd=str(root), env=hl.project_env(root), capture_output=True, text=True)
    return proc.returncode == 0


def run_generator(root, target):
    """Re-run the registered generator that owns `target`. True iff it ran clean.
    Content comes from the generator, not the agent."""
    argv = GENERATED_TARGETS.get(target)
    if not argv:
        return False
    proc = subprocess.run(
        [sys.executable, str(_scripts_dir() / argv[0]), *argv[1:]],
        cwd=str(root), env=hl.project_env(root), capture_output=True, text=True)
    return proc.returncode == 0


def _apply_one(prep, root, gen):
    op = prep["op"]
    if op == "regenerate":
        return gen(root, prep["target"])
    path = prep["path"]
    text = path.read_text(encoding="utf-8", errors="replace")
    if op == "set_frontmatter":
        new = _set_frontmatter(text, prep["field"], prep["value"])
    elif op == "rename":
        new = _boundary_re(prep["old"]).sub(prep["new"], text)
    elif op == "retract":
        want, removed, keep = prep["line"].strip(), False, []
        for l in text.splitlines():
            if not removed and l.strip() == want:
                removed = True
                continue
            keep.append(l)
        new = "\n".join(keep) + ("\n" if text.endswith("\n") else "")
    else:
        return False
    if new is None or new == text:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def _snapshot(touched, path):
    if path not in touched:
        touched[path] = path.read_bytes() if path.exists() else None


def _restore(touched):
    for path, original in touched.items():
        if original is None:
            if path.exists():
                path.unlink()
        else:
            path.write_bytes(original)


def _report_item(item, reason):
    return {"target": item.get("target"), "kind": item.get("kind"),
            "evidence": item.get("evidence"), "change": item.get("change"),
            "reason": reason}


def _applied_item(item, prep):
    return {"target": item.get("target"), "op": prep["op"],
            "kind": item.get("kind"), "evidence": item.get("evidence")}


def apply_plan(root, plan, now, run_check=run_check, run_generator=run_generator):
    """Apply a maintenance plan: auto-apply ONLY the mechanical kinds (re-validated
    deterministically), report everything else, then re-run the gate and roll the
    whole batch back on red. Returns {applied, report, rolled_back}."""
    root = Path(root)
    applied, report, touched = [], [], {}
    for item in plan if isinstance(plan, list) else []:
        verdict, data = classify(root, item)
        if verdict != "mechanical":
            report.append(_report_item(item, data))
            continue
        assert isinstance(data, dict)            # narrowed: mechanical => prepared op
        path = (root / data["target"]) if data["op"] == "regenerate" else data["path"]
        _snapshot(touched, path)
        if _apply_one(data, root, run_generator):
            applied.append(_applied_item(item, data))
        else:
            report.append(_report_item(item, "mechanical apply produced no change"))
    if applied and not run_check(root):
        _restore(touched)
        return {"applied": [], "report": report, "rolled_back": True,
                "rollback_reason": "check.py RED after edits — batch reverted"}
    return {"applied": applied, "report": report, "rolled_back": False}


def main():
    ap = argparse.ArgumentParser(description="Apply a docs-sync maintenance plan (JSON on stdin).")
    ap.add_argument("--root", default=None)
    args = ap.parse_args()
    root = Path(args.root).resolve() if args.root else hl.repo_root()
    plan = json.loads(sys.stdin.read() or "[]")
    if isinstance(plan, dict):
        plan = plan.get("plan", [])
    result = apply_plan(root, plan, int(time.time()))
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
