#!/usr/bin/env python3
"""Stop-hook tidy: lint the tree at session boundaries (upstream A3 pattern).

When the working tree changed since the last check, runs the fast
deterministic gate subset (lint_structure, lint_docs, gen_inventory --check)
and, on FAIL, blocks the stop (exit 2) with FAIL/FIX lines on stderr so the
agent fixes them immediately. Blocks at most ONCE per distinct dirty-tree
fingerprint (RELIABILITY R11) — a session can always end. Fails open (R6).
"""
import hashlib
import subprocess
import sys

import harness_lib as hl

CHECKS = (("lint_structure.py", ()), ("lint_docs.py", ()),
          ("gen_inventory.py", ("--check",)))
MAX_LINES = 30


def fingerprint(root):
    """Hash of the dirty tree, or None when git is unavailable (fail open)."""
    h = hashlib.sha256()
    for cmd in (("git", "status", "--porcelain"), ("git", "diff", "HEAD")):
        r = subprocess.run(cmd, cwd=root, capture_output=True, text=True,
                           timeout=30)
        if r.returncode != 0:
            return None
        h.update(r.stdout.encode("utf-8"))
    return h.hexdigest()


def run_checks(root, plugin):
    fails = []
    for name, args in CHECKS:
        r = subprocess.run(
            [sys.executable, str(plugin / "scripts" / name), *args],
            cwd=root, env=hl.project_env(root), capture_output=True,
            text=True, timeout=120)
        if r.returncode != 0:
            fails.append(r.stdout.strip())
    return fails


def main():
    if hl.is_headless():  # Stop fires in -p sessions too — recursion guard
        return 0
    try:
        sys.stdin.read()  # drain the hook payload (content unused)
        root = hl.repo_root()
        fp = fingerprint(root)
        if fp is None:
            return 0
        state = hl.state_dir(root) / "tidy-fingerprint.txt"
        last = state.read_text(encoding="utf-8").strip() if state.exists() else ""
        if fp == last:
            return 0  # this exact state was already checked — block once only
        fails = run_checks(root, hl.plugin_root())
        state.write_text(fp + "\n", encoding="utf-8")
        if fails:
            lines = "\n".join(fails).splitlines()[:MAX_LINES]
            sys.stderr.write(
                "harness tidy (Stop hook): gate subset FAILED on the current tree.\n"
                + "\n".join(lines)
                + "\nApply each FIX above, rerun the gate, then finish.\n")
            return 2
        return 0
    except Exception as e:  # R6: never break the session on our own failure
        try:
            log = hl.state_dir(hl.repo_root()) / "tidy.log"
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"{hl.today().isoformat()} tidy_stop error: {e!r}\n")
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
