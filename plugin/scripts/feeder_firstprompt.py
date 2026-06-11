#!/usr/bin/env python3
"""UserPromptSubmit hook, first prompt only: purpose-aware enrichment
(INJECT stage 2). SessionStart cannot know the session's purpose; this hook
sees the actual task and injects targeted memory. Marks the session seen
BEFORE spawning enrichment (RELIABILITY R7)."""
import json
import os
import subprocess
import sys

import harness_lib as hl

TIMEOUT = 120
PROMPT_TMPL = """You are the second-stage context feeder. The session's first user prompt:

<task>
{task}
</task>

Read docs/memory/MEMORY.md, then navigate ONLY what is relevant to this task
via the index.md files in docs/memory/knowledge/, docs/memory/adr/,
docs/memory/limitations/ (and docs/ if clearly relevant).

Output ONLY a targeted addendum (max 60 lines): relevant decisions, known
landmines, exact paths worth reading. If nothing is relevant, output exactly:
NO_RELEVANT_MEMORY"""


def mark_if_new(root, session_id):
    """True iff this session was not seen before; records it either way."""
    seen = hl.state_dir(root) / "seen-sessions.txt"
    ids = set(seen.read_text(encoding="utf-8").split()) if seen.exists() else set()
    if session_id in ids:
        return False
    ids.add(session_id)
    seen.write_text("\n".join(sorted(ids)), encoding="utf-8")
    return True


def main():
    if hl.is_headless():
        return
    try:
        data = json.load(sys.stdin)
        root = hl.repo_root()
        if not (root / "docs" / "memory" / "MEMORY.md").exists():
            return
        sid = data.get("session_id", "")
        if not sid or not mark_if_new(root, sid):
            return
        prompt = PROMPT_TMPL.format(task=data.get("prompt", "")[:4000])
        model = os.environ.get("HARNESS_FEEDER_MODEL", "sonnet[1m]")
        r = subprocess.run(
            ["claude", "-p", prompt, "--model", model,
             "--allowedTools", "Read,Grep,Glob"],
            cwd=root, env=hl.headless_env(), capture_output=True, text=True,
            timeout=TIMEOUT)
        out = r.stdout.strip()
        if r.returncode != 0 or not out or "NO_RELEVANT_MEMORY" in out:
            return
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "[memory addendum for this task]\n" + out}}))
    except Exception as e:  # R6
        try:
            with open(hl.state_dir(hl.repo_root()) / "hook-errors.log", "a") as f:
                f.write(f"feeder_firstprompt: {e}\n")
        except OSError:
            pass


if __name__ == "__main__":
    main()
