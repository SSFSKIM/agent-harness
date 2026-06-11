#!/usr/bin/env python3
"""SessionStart hook: compile and inject a context pack (INJECT stage 1).

Spawns a headless large-context feeder agent that READS structured memory and
COMPILES a pack ("injection is compilation, not retrieval"). Degrades to a
deterministic minimal pack on any failure (RELIABILITY R2); never blocks the
session (R6).
"""
import json
import os
import subprocess
import sys

import harness_lib as hl

TIMEOUT = 150
PROMPT = """You are the context feeder for this repo. Compile a context pack for a fresh session.

Read, in this order:
1. docs/memory/MEMORY.md
2. docs/memory/progress/current.md
3. every file in docs/exec-plans/active/
4. docs/memory/openq/index.md
5. the 3 most recent files in docs/memory/archive/sessions/ (by filename)

Then output ONLY the context pack (no preamble, no meta-commentary):
## Where we are
## Active plans & immediate next actions
## Open questions that matter now
## Landmines / limitations
## Pointers (exact paths worth reading for likely work today)

Hard limit 150 lines. Compile what a fresh session needs; do not paste whole files."""


def fallback_pack(root):
    parts = []
    for rel in ("docs/memory/MEMORY.md", "docs/memory/progress/current.md"):
        p = root / rel
        if p.exists():
            parts.append(f"### {rel}\n" + p.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


def compile_pack(root):
    model = os.environ.get("HARNESS_FEEDER_MODEL", "sonnet[1m]")
    try:
        r = subprocess.run(
            ["claude", "-p", PROMPT, "--model", model,
             "--allowedTools", "Read,Grep,Glob"],
            cwd=root, env=hl.headless_env(), capture_output=True, text=True,
            timeout=TIMEOUT)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return fallback_pack(root)


def main():
    if hl.is_headless():
        return
    try:
        json.load(sys.stdin)
        root = hl.repo_root()
        if not (root / "docs" / "memory" / "MEMORY.md").exists():
            return
        pack = compile_pack(root)
        if not pack:
            return
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "[context pack — compiled by harness feeder]\n" + pack}}))
    except Exception as e:  # R6: hooks fail open, never break the session
        try:
            with open(hl.state_dir(hl.repo_root()) / "hook-errors.log", "a") as f:
                f.write(f"feeder_sessionstart: {e}\n")
        except OSError:
            pass


if __name__ == "__main__":
    main()
