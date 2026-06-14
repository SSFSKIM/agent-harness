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


def _is_specific_symbol(tok):
    """A rename target must be a SPECIFIC code symbol/path, not a plain prose word.
    It must carry identifier structure (`_ . / -` or a digit) or mixed case, so a
    common English word ('set', 'run', 'state') can never trigger a global prose
    rewrite. (Renaming a real symbol like `feeder_sessionstart` / `docs/memory` /
    `MAX_RETRIES` still qualifies; an ambiguous bare word falls to the report.)"""
    return bool(isinstance(tok, str) and SYMBOL_RE.match(tok)) and (
        any(c in tok for c in "_./-") or any(c.isdigit() for c in tok)
        or tok != tok.lower())


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


# Strip the router's append framing (`- `, an optional `- <date>: `, or a `| `
# table-cell lead) so attribution can anchor the snippet at the START of the line's
# CONTENT — a substring-anywhere match would let a short routed phrase authorize
# deleting an unrelated human line that merely contains it.
_ROUTER_PREFIX = re.compile(r"^(?:[-*]\s+(?:\d{4}-\d{2}-\d{2}:\s+)?|\|\s*)")
MIN_ATTRIB_SNIPPET = 8     # a trivially short snippet can't attribute a line


def _attributable(root, target, line):
    """True iff the line was machine-authored INTO `target` by the router — so
    deleting it REVERSES a router append, never edits human prose. Requires a
    journal `[routed] "snippet" -> target` whose snippet PREFIXES the line's content
    (after stripping the router's `- `/`- <date>: `/`| ` framing). Prefix-anchored
    (not substring-anywhere) so a short routed phrase can't authorize deleting an
    unrelated human line that merely contains it. The journal tree is read through
    the symlink-safe guard so a symlinked `docs/journal` can't manufacture provenance."""
    rel = os.path.normpath(str(target))
    core = _ROUTER_PREFIX.sub("", re.sub(r"\s+", " ", line).strip(), count=1)
    base = hl.within_repo_no_symlink(root, JOURNAL_DIR)
    if base is None or not base.exists():
        return False
    for jf in sorted(base.rglob("*.md")):
        if jf.is_symlink():
            continue
        try:
            jtext = jf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for jl in jtext.splitlines():
            m = ROUTED_RE.search(jl)
            if not m:
                continue
            snippet = re.sub(r"\s+", " ", m.group(1)).strip()
            if (os.path.normpath(m.group(2)) == rel
                    and len(snippet) >= MIN_ATTRIB_SNIPPET
                    and core.startswith(snippet)):
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
        # `old` must be a SPECIFIC code symbol (not a bare prose word — that would
        # globally rewrite prose); `new` need only be symbol-SHAPED.
        if not (_is_specific_symbol(old) and isinstance(new, str)
                and SYMBOL_RE.match(new) and old != new):
            return ("report", "rename `old` is not a specific code symbol "
                              "(a bare prose word can't be a global rename)")
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
        if data["op"] == "regenerate":
            path = hl.within_repo_no_symlink(root, data["target"])
            if path is None:                     # symlinked generated target → refuse
                report.append(_report_item(item, "regenerate target failed the symlink guard"))
                continue
        else:
            path = data["path"]
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


# ---- M2: change-driven scope builder (pure git/text, no agent) -------------

# The "public surface" docs describe: a change to one of these is what makes a
# doc go stale. Deterministic regexes (no model) — the audit agent (M3) reasons
# about the surface this names; this just locates it with file:line evidence.
SURFACE = [
    (re.compile(r"\bdef\s+([A-Za-z_]\w*)"), "function"),
    (re.compile(r"\bclass\s+([A-Za-z_]\w*)"), "class"),
    (re.compile(r"^([A-Z][A-Z0-9_]{2,})\s*[:=]"), "constant"),   # module-level CONST/default
    (re.compile(r"--([a-z][a-z0-9-]+)"), "flag"),                # CLI flag
]
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _surface_tokens(content):
    out = []
    for rx, kind in SURFACE:
        for m in rx.finditer(content):
            out.append((m.group(1), kind))
    return out


def _dedupe(rows):
    """Keep one row per (symbol, kind, file) — the first (lowest-line) sighting."""
    seen, out = set(), []
    for r in rows:
        key = (r["symbol"], r["kind"], r["file"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def parse_diff_surface(diff_text):
    """Parse `git diff --no-color -U0` output into the changed public surface.
    Pure function (no git) so the extraction is unit-testable from text. Returns
    {changed_files, changed_symbols, removed} — symbols carry file:line evidence;
    `removed` is the NET-removed surface (a symbol still present on a `+` line is a
    change, not a removal)."""
    files, added, removed_raw = [], [], []
    cur, a_raw, new_line, old_line, status = None, "", 0, 0, "modified"
    for raw in diff_text.splitlines():
        if raw.startswith("diff --git "):
            cur, status = None, "modified"
        elif raw.startswith("new file"):
            status = "added"
        elif raw.startswith("deleted file"):
            status = "deleted"
        elif raw.startswith("--- "):
            a_raw = raw[4:].strip()
        elif raw.startswith("+++ "):
            b_raw = raw[4:].strip()
            if a_raw == "/dev/null":
                cur, status = b_raw[2:], "added"
            elif b_raw == "/dev/null":
                cur, status = a_raw[2:], "deleted"
            else:
                cur = b_raw[2:]
            files.append({"path": cur, "status": status})
        elif raw.startswith("@@"):
            m = _HUNK_RE.match(raw)
            if m:
                old_line, new_line = int(m.group(1)), int(m.group(2))
        elif cur and raw.startswith("+") and not raw.startswith("+++"):
            for sym, kind in _surface_tokens(raw[1:]):
                added.append({"symbol": sym, "kind": kind, "file": cur, "line": new_line})
            new_line += 1
        elif cur and raw.startswith("-") and not raw.startswith("---"):
            for sym, kind in _surface_tokens(raw[1:]):
                removed_raw.append({"symbol": sym, "kind": kind, "file": cur, "line": old_line})
            old_line += 1
        elif cur and raw.startswith(" "):       # context line (only if not -U0) — keep counters honest
            old_line += 1
            new_line += 1
    added = _dedupe(added)
    added_keys = {(r["symbol"], r["kind"], r["file"]) for r in added}
    removed = _dedupe([r for r in removed_raw
                       if (r["symbol"], r["kind"], r["file"]) not in added_keys])
    return {"changed_files": files, "changed_symbols": added, "removed": removed}


def _git_diff(root, base):
    proc = subprocess.run(
        ["git", "-C", str(root), "diff", "--no-color", "-U0", f"{base}...HEAD"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git diff failed: {proc.stderr.strip()[:200]}")
    return proc.stdout


def build_change_scope(root, base="main", run_diff=_git_diff):
    """The change-driven audit input: the public surface this branch changed vs
    `base` (three-dot = since the merge-base). `run_diff` is injectable for tests."""
    return parse_diff_surface(run_diff(root, base))


# ---- M3: the read-only audit agent + maintenance-plan parsing --------------
#
# The agent only PROPOSES (it has Read/Glob/Grep/LS, no Write/Edit/Bash). Its
# output is a maintenance plan (JSON) that M1's deterministic applicator
# re-validates and applies — so the agent can never itself edit a curated doc
# (the same containment-by-construction shape as the dreaming router).

AUDIT_MODEL = "sonnet"
AUDIT_TIMEOUT = 1200
MAX_PLAN_ITEMS = 64


def load_audit_templates():
    d = hl.plugin_root() / "skills" / "docs-sync" / "templates"
    return (d / "audit_system.md").read_text(encoding="utf-8"), \
           (d / "audit_input.md").read_text(encoding="utf-8")


def render_audit_prompt(system_tmpl, input_tmpl, scope):
    """System (raw) + input (.format-substituted). Only the input template is
    formatted, and the scope is inserted as a single value, so its braces are not
    re-scanned (same framing guarantee as the dreaming prompts)."""
    filled = input_tmpl.format(scope=json.dumps(scope, ensure_ascii=False, indent=2))
    return system_tmpl + "\n\n" + filled


def spawn_audit(prompt, model, cwd, timeout=AUDIT_TIMEOUT):
    """Spawn the READ-ONLY audit agent (Read/Glob/Grep/LS only, cwd = repo so it
    can compare the change scope against the docs, prompt via stdin). It writes
    NOTHING — it returns a maintenance plan as stdout JSON. Raises on nonzero/timeout."""
    proc = subprocess.run(
        ["claude", "-p", "--model", model, "--allowedTools", "Read,Glob,Grep,LS"],
        input=prompt, capture_output=True, text=True,
        cwd=str(cwd), env=hl.headless_env(), timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p exit {proc.returncode}: {proc.stderr[:300]}")
    return proc.stdout


def parse_maintenance_plan(text):
    """Extract the outermost JSON object and return its `plan` list (dict items,
    capped). Raises ValueError on empty/non-object/no-plan output. Unknown item
    shapes are KEPT — M1's classify() routes anything non-mechanical to the report,
    so a malformed item is surfaced, never silently dropped."""
    if not text or not text.strip():
        raise ValueError("empty audit output")
    s = text.strip()
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in audit output")
    obj = json.loads(s[start:end + 1])
    if not isinstance(obj, dict) or not isinstance(obj.get("plan"), list):
        raise ValueError("audit output lacks a `plan` list")
    return [it for it in obj["plan"] if isinstance(it, dict)][:MAX_PLAN_ITEMS]


def audit(scope, root, spawn=spawn_audit, templates=None, model=AUDIT_MODEL,
          timeout=AUDIT_TIMEOUT):
    """Render the audit prompt from the change scope, spawn the read-only agent,
    and parse its maintenance plan. `spawn`/`templates` are injectable for tests."""
    system_tmpl, input_tmpl = templates or load_audit_templates()
    prompt = render_audit_prompt(system_tmpl, input_tmpl, scope)
    out = spawn(prompt, model, cwd=root, timeout=timeout)
    return parse_maintenance_plan(out)


def _scope_is_empty(scope):
    return not (scope.get("changed_symbols") or scope.get("removed")
                or scope.get("changed_files") or scope.get("forgetting_targets"))


# ---- M5 (v1.1): provenance-driven forgetting scope -------------------------

_SESSIONS_RE = re.compile(r"\(sessions:\s*([^)]*)\)")


def build_provenance_scope(root, dropped_threads):
    """The forgetting audit input: the docs that now-dropped sessions authored,
    located via journal `[routed] … -> docs/X` provenance. Returns a scope whose
    `forgetting_targets` name those docs (empty if none of the dropped threads
    routed anything — the common case, so the forgetting pass usually no-ops without
    ever spawning an agent). Same engine as change-driven; only the scope differs."""
    empty = {"forgetting_targets": [], "changed_files": [], "changed_symbols": [],
             "removed": []}
    prefixes = {str(t)[:8] for t in dropped_threads}
    if not prefixes:
        return empty
    base = Path(root) / JOURNAL_DIR
    if not base.exists():
        return empty
    targets, seen = [], set()
    for jf in sorted(base.rglob("*.md")):
        cur = set()
        try:
            lines = jf.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if line.startswith("## "):
                m = _SESSIONS_RE.search(line)
                cur = {s.strip() for s in m.group(1).split(",")} if m else set()
                continue
            rm = ROUTED_RE.search(line)
            hit = cur & prefixes
            if rm and hit:
                snippet, target = rm.group(1).strip(), os.path.normpath(rm.group(2))
                key = (target, snippet)
                if key not in seen:
                    seen.add(key)
                    targets.append({"target": target, "thread": sorted(hit)[0],
                                    "routed_snippet": snippet})
    empty["forgetting_targets"] = targets
    return empty


def forgetting_pass(root, dropped_threads, spawn=spawn_audit, now=None,
                    run_check=run_check, run_generator=run_generator):
    """v1.1 forgetting: retract the docs a now-dropped session authored. Builds the
    provenance scope and runs the SAME audit→apply engine; the applicator DELETEs
    only the journal-attributable lines and reports the rest. No-op (no agent spawn)
    when no dropped thread has journal provenance."""
    scope = build_provenance_scope(root, dropped_threads)
    if _scope_is_empty(scope):
        return {"applied": [], "report": [], "rolled_back": False, "plan": [],
                "forgetting_targets": 0}
    result = run(root, scope=scope, spawn=spawn, now=now,
                 run_check=run_check, run_generator=run_generator)
    result["forgetting_targets"] = len(scope["forgetting_targets"])
    return result


# ---- M4: the completion-gate orchestration (scope -> audit -> apply) --------

def run(root, scope=None, base="main", spawn=spawn_audit, now=None,
        run_check=run_check, run_generator=run_generator):
    """One docs-sync pass, wired into the completion gate. Build (or accept) the
    change scope -> read-only audit -> deterministic apply. An empty scope is a
    no-op (the audit agent is never spawned). Returns {applied, report,
    rolled_back, plan}; `applied` are committed mechanical fixes, `report` is the
    semantic findings surfaced for the review. NEVER hard-blocks (the caller
    treats `report` like any P2 — only check.py blocks a commit)."""
    if scope is None:
        scope = build_change_scope(root, base)
    if _scope_is_empty(scope):
        return {"applied": [], "report": [], "rolled_back": False, "plan": []}
    plan = audit(scope, root, spawn=spawn)
    now = now if now is not None else int(time.time())
    result = apply_plan(root, plan, now, run_check=run_check, run_generator=run_generator)
    result["plan"] = plan
    return result


def main():
    ap = argparse.ArgumentParser(
        description="docs-sync: keep curated docs current (run) / apply a plan (apply).")
    ap.add_argument("mode", nargs="?", choices=("run", "apply"), default="apply")
    ap.add_argument("--root", default=None)
    ap.add_argument("--base", default="main")
    args = ap.parse_args()
    root = Path(args.root).resolve() if args.root else hl.repo_root()
    if args.mode == "run":
        result = run(root, base=args.base)
    else:
        plan = json.loads(sys.stdin.read() or "[]")
        if isinstance(plan, dict):
            plan = plan.get("plan", [])
        result = apply_plan(root, plan, int(time.time()))
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
