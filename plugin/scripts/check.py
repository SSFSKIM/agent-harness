#!/usr/bin/env python3
"""The deterministic commit gate. Green = commit allowed; that is the whole
contract (minimal blocking gates — everything else is fix-forward)."""
import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

import harness_lib as hl


def resolve_cmd(cfg, key, env_name):
    """Argv for a host gate step, or None. The unversioned env var wins over the
    versioned .harness.json value. A non-str / blank / unparseable value yields
    None — fail-open like the rest of the harness (gate_config, exempt_roots): a
    malformed command skips its step rather than crashing the gate, and the
    absent step in the gate output is the visible signal. Returns a shlex-split
    argv ready for subprocess (run without a shell, so no shell injection)."""
    val = os.environ.get(env_name) or cfg.get(key)
    if not (isinstance(val, str) and val.strip()):
        return None
    try:
        return shlex.split(val)
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser(description="Run the commit gate.")
    ap.add_argument("--root", default=None,
                    help="repo root to check (default: detected via harness_lib)")
    args = ap.parse_args()
    root = Path(args.root).resolve() if args.root else hl.repo_root()
    cfg = hl.gate_config(root)  # optional per-repo .harness.json
    here = Path(__file__).resolve().parent
    steps = [
        ("structure", [sys.executable, str(here / "lint_structure.py")]),
        ("docs", [sys.executable, str(here / "lint_docs.py")]),
        ("generated", [sys.executable, str(here / "gen_inventory.py"), "--check"]),
    ]
    # Host-authored structural lint (the setter axis): a host wires its own
    # app-code invariant checks here, with no harness-side hardcoded rule.
    lint_cmd = resolve_cmd(cfg, "lint_cmd", "HARNESS_LINT_CMD")
    if lint_cmd:
        steps.append(("host-lint", lint_cmd))
    test_cmd = resolve_cmd(cfg, "test_cmd", "HARNESS_TEST_CMD")
    if test_cmd:  # hosts wire their real suite (env or .harness.json)
        steps.append(("tests", test_cmd))
    elif (root / "tests").is_dir():  # harness-init hosts may have no tests yet
        steps.append(("tests", [sys.executable, "-m", "unittest", "discover",
                                "-s", str(root / "tests")]))
    failed = []
    env = hl.project_env(root)
    for name, cmd in steps:
        print(f"== {name} ==")
        if subprocess.run(cmd, cwd=root, env=env).returncode != 0:
            failed.append(name)
    if failed:
        print(f"check: FAIL ({', '.join(failed)}) — fix per the FIX instructions above, then rerun.")
        sys.exit(1)
    print("check: GREEN — commit allowed.")


if __name__ == "__main__":
    main()
