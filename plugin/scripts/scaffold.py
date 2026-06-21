#!/usr/bin/env python3
"""Bootstrap the harness docs-tree convention into a host repo (harness-init).

Idempotent: never overwrites an existing file; prints CREATE/SKIP per path.
Renders seed templates from skills/harness-init/templates/ and regenerates
the component inventory so a fresh host starts lint-GREEN.
"""
import argparse
import shlex
import subprocess
import sys
from pathlib import Path

import harness_lib as hl
# SEEDS / TOP_INDEXES / render / components_table are the seed-layout primitives —
# promoted to the core module so lint_base.py can share them (ARCHITECTURE invariant
# 8). Re-exported here so `scaffold.SEEDS` etc. and this module's internal use both work.
from harness_lib import SEEDS, TOP_INDEXES, components_table, render

DIRS = (
    "docs/adr", "docs/design-docs", "docs/exec-plans/active",
    "docs/exec-plans/completed", "docs/generated", "docs/product-specs",
    "docs/references",
)
GITIGNORE_LINES = (".claude/harness/",)
# Forms by which a host may already blanket-ignore all of .claude/ — then
# .claude/harness/ runtime state is covered, but instance skills under
# .claude/skills/ won't travel without `git add -f`.
CLAUDE_IGNORE_FORMS = frozenset(
    {".claude", ".claude/", "/.claude", "/.claude/", ".claude/*"})
HOOK_MARKER = "# agent-harness gate"


def seed(templates, template, target, rel, subs, log):
    if target.exists():
        log(f"SKIP   {rel} (exists)")
        return
    text = render((templates / template).read_text(encoding="utf-8"), subs)
    target.write_text(text, encoding="utf-8")
    log(f"CREATE {rel}")


def scaffold(root, plugin, log):
    root = Path(root)
    templates = plugin / "skills" / "harness-init" / "templates"
    subs = {"PROJECT": root.name, "TODAY": hl.today().isoformat(),
            "COMPONENTS": components_table(plugin)}
    for d in DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
    for template, dest in SEEDS:
        seed(templates, template, root / dest, dest, subs, log)
    for cat in TOP_INDEXES:
        rel = f"docs/{cat}/index.md"
        seed(templates, "category-index.md", root / rel, rel,
             {**subs, "CATEGORY": cat}, log)
    gitignore(root, log)
    git_hook(root, plugin, log)
    inventory(root, plugin, log)


def git_hook(root, plugin, log):
    """Install/refresh .git/hooks/pre-commit running the check gate.

    The hook IS the recorded gate command for this repo (machine-local
    absolute paths, unversioned). Ours-marked hooks are rewritten on every
    run so paths refresh after a repo/plugin move; foreign hooks are never
    touched.
    """
    hooks_dir = root / ".git" / "hooks"
    if not hooks_dir.is_dir():
        log("SKIP   .git/hooks/pre-commit (not a git repo)")
        return
    hook = hooks_dir / "pre-commit"
    existed = hook.exists()
    if existed and HOOK_MARKER not in hook.read_text(encoding="utf-8",
                                                     errors="ignore"):
        log("SKIP   .git/hooks/pre-commit (foreign hook exists)")
        return
    gate = (Path(plugin) / "scripts" / "check.py").resolve()
    hook.write_text(
        "#!/bin/sh\n"
        f"{HOOK_MARKER} — rerun scaffold.py to refresh after a repo/plugin move\n"
        f"exec python3 {shlex.quote(str(gate))} --root {shlex.quote(str(root.resolve()))}\n",
        encoding="utf-8")
    hook.chmod(0o755)
    log(("REWRITE" if existed else "CREATE") + " .git/hooks/pre-commit")


def gitignore(root, log):
    gi = root / ".gitignore"
    existing = gi.read_text(encoding="utf-8") if gi.exists() else ""
    lines = {l.strip() for l in existing.splitlines()}
    if lines & CLAUDE_IGNORE_FORMS:
        # Host already ignores all of .claude/: runtime state is covered, but
        # instance skills (.claude/skills/) then need `git add -f` to travel.
        # Surface it at port time; don't append a redundant ignore line.
        log("NOTE   host ignores .claude/ — `git add -f` instance skills under "
            ".claude/skills/ so they travel (.claude/harness/ already covered)")
        return
    missing = [l for l in GITIGNORE_LINES if l not in lines]
    if not missing:
        return
    if existing and not existing.endswith("\n"):
        existing += "\n"
    gi.write_text(existing + "\n".join(missing) + "\n", encoding="utf-8")
    log("APPEND .gitignore")


def inventory(root, plugin, log):
    r = subprocess.run(
        [sys.executable, str(plugin / "scripts" / "gen_inventory.py")],
        cwd=root, env=hl.project_env(root), capture_output=True, text=True)
    if r.returncode == 0:
        log("GEN    docs/generated/component-inventory.md")
    else:
        log(f"WARN   gen_inventory failed: {(r.stderr or r.stdout).strip()}")


def main():
    ap = argparse.ArgumentParser(
        description="Bootstrap the harness docs tree into a host repo.")
    ap.add_argument("--root", default=None,
                    help="host repo root (default: detected via harness_lib)")
    args = ap.parse_args()
    root = Path(args.root).resolve() if args.root else hl.repo_root()
    scaffold(root, hl.plugin_root(), print)
    print(f"scaffold: done — fill the FILL markers, then run check.py "
          f"against {root} (harness-init skill, steps 3-9).")


if __name__ == "__main__":
    main()
