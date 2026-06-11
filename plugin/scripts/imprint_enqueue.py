#!/usr/bin/env python3
"""SessionEnd / PreCompact hook: enqueue an imprint job, spawn the worker.

Usage (from hooks.json): imprint_enqueue.py <session_end|pre_compact>
At-least-once append (R4); pre_compact keys get a 10-minute bucket so repeated
compactions in one session each imprint once (R1)."""
import json
import subprocess
import sys
import time
from pathlib import Path

import harness_lib as hl
import imprint_guard as guard


def main():
    if hl.is_headless():
        return
    try:
        event = sys.argv[1] if len(sys.argv) > 1 else "session_end"
        data = json.load(sys.stdin)
        root = hl.repo_root()
        if not (root / "docs" / "memory" / "MEMORY.md").exists():
            return
        bucket = str(int(time.time() // 600)) if event == "pre_compact" else ""
        entry = {"key": guard.key(data.get("session_id", ""), event, bucket),
                 "transcript_path": data.get("transcript_path", ""),
                 "event": event}
        with open(hl.state_dir(root) / "imprint-queue.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        worker = Path(__file__).resolve().parent / "imprint_run.py"
        log = open(hl.state_dir(root) / "imprint.log", "a")
        subprocess.Popen([sys.executable, str(worker)], cwd=root,
                         stdout=log, stderr=subprocess.STDOUT,
                         start_new_session=True)
    except Exception as e:  # R6
        try:
            with open(hl.state_dir(hl.repo_root()) / "hook-errors.log", "a") as f:
                f.write(f"imprint_enqueue: {e}\n")
        except OSError:
            pass


if __name__ == "__main__":
    main()
