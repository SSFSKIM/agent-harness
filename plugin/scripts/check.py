#!/usr/bin/env python3
"""The deterministic commit gate. Green = commit allowed; that is the whole
contract (minimal blocking gates — everything else is fix-forward)."""
import argparse
import subprocess
import sys
from pathlib import Path

import harness_lib as hl


def _host_step(cfg, key, env_name):
    """(argv, error): resolve a host gate command via harness_lib. A present
    but unparseable command yields an error string (fail closed — the gate goes
    RED) rather than a silent skip; an absent command yields (None, None)."""
    try:
        return hl.gate_command(cfg, key, env_name), None
    except ValueError as e:
        return None, (f"FAIL gate {key}: not a parseable command ({e}). "
                      f"FIX: fix the quoting in .harness.json {key} (or remove it).")


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
        ("base", [sys.executable, str(here / "lint_base.py")]),  # base/ drift-check (self-host; no-op elsewhere)
    ]
    failed = []
    # Host-authored structural lint (the setter axis) + the host test suite,
    # wired via .harness.json/env (resolution lives in harness_lib). A
    # present-but-broken command fails the gate; an absent one is a no-op.
    lint_argv, err = _host_step(cfg, "lint_cmd", "HARNESS_LINT_CMD")
    if err:
        print(err); failed.append("host-lint")
    elif lint_argv:
        steps.append(("host-lint", lint_argv))
    test_argv, err = _host_step(cfg, "test_cmd", "HARNESS_TEST_CMD")
    if err:
        print(err); failed.append("tests")
    elif test_argv:  # hosts wire their real suite (env or .harness.json)
        steps.append(("tests", test_argv))
    elif (root / "tests").is_dir():  # harness-init hosts may have no tests yet
        steps.append(("tests", [sys.executable, "-m", "unittest", "discover",
                                "-s", str(root / "tests")]))
    env = hl.project_env(root)
    for name, cmd in steps:
        print(f"== {name} ==")
        try:
            rc = subprocess.run(cmd, cwd=root, env=env).returncode
        except OSError as e:  # missing/non-executable command must not crash the gate
            print(f"FAIL gate {name}: cannot run ({e}). "
                  f"FIX: ensure the command exists and is executable.")
            rc = 1
        if rc != 0:
            failed.append(name)
    if failed:
        print(f"check: FAIL ({', '.join(sorted(set(failed)))}) — "
              f"fix per the FIX instructions above, then rerun.")
        sys.exit(1)
    print("check: GREEN — commit allowed.")


if __name__ == "__main__":
    main()
