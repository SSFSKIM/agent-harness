#!/usr/bin/env python3
"""The deterministic commit gate. Green = commit allowed; that is the whole
contract (minimal blocking gates — everything else is fix-forward)."""
import subprocess
import sys
from pathlib import Path

import harness_lib as hl


def main():
    root = hl.repo_root()
    here = Path(__file__).resolve().parent
    steps = [
        ("structure", [sys.executable, str(here / "lint_structure.py")]),
        ("docs", [sys.executable, str(here / "lint_docs.py")]),
        ("generated", [sys.executable, str(here / "gen_inventory.py"), "--check"]),
        ("tests", [sys.executable, "-m", "unittest", "discover", "-s",
                   str(root / "tests")]),
    ]
    failed = []
    for name, cmd in steps:
        print(f"== {name} ==")
        if subprocess.run(cmd, cwd=root).returncode != 0:
            failed.append(name)
    if failed:
        print(f"check: FAIL ({', '.join(failed)}) — fix per the FIX instructions above, then rerun.")
        sys.exit(1)
    print("check: GREEN — commit allowed.")


if __name__ == "__main__":
    main()
