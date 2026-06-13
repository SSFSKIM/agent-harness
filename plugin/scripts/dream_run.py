#!/usr/bin/env python3
"""Dreaming orchestrator: Phase 1 (extract) → Phase 2 (consolidate), single-flight.

Manual entry point for the Codex-faithful memory pipeline (the `dream-rollouts`
skill). Phase 1 discovers + claims eligible idle past sessions and extracts a raw
memory each (Haiku); Phase 2 consolidates the selected outputs into the workspace
`MEMORY.md` + `memory_summary.md` (Sonnet, locked-down). At most one dream runs at
a time, via a lock file with stale-lock recovery (the imprint worker's R3 pattern;
Phase 2 also holds the global DB lock — defense in depth).

Parallel to the docs/memory loop: writes ONLY under `.claude/harness/memories/`
(gitignored runtime). The docs/memory `dream` skill is untouched.
"""
import json
import os
import sys
import time
from pathlib import Path

import dream_discover as dd
import dream_phase1 as p1
import dream_phase2 as p2
import harness_lib as hl
import memories_db as mdb

LOCK_STALE = 3 * 3600   # a dream can take a while (several Haiku + one Sonnet run)


def run(conn, root, now, *, phase1_model=None, phase2_model=None,
        phase1_spawn=p1.spawn_phase1, phase2_spawn=p2.spawn_phase2):
    """Phase 1 → Phase 2 over one repo. `*_spawn` are injectable so the chaining
    is testable without a live model. Returns `{phase1, phase2}`."""
    phase1_model = phase1_model or os.environ.get(
        "HARNESS_DREAM_PHASE1_MODEL", p1.DEFAULT_MODEL)
    phase2_model = phase2_model or os.environ.get(
        "HARNESS_DREAM_PHASE2_MODEL", p2.DEFAULT_MODEL)
    worker = f"dream-{os.getpid()}"

    rollouts = dd.discover_rollouts(hl.project_transcripts_dir(root), now)
    claimed = dd.claim_rollouts(conn, rollouts, worker, now)
    p1_results = p1.extract_rollouts(conn, root, claimed, phase1_model, now,
                                     spawn=phase1_spawn)
    p2_result = p2.consolidate(conn, root, now, model=phase2_model,
                               spawn=phase2_spawn, worker_id=worker)
    return {"phase1": {"claimed": len(claimed), "results": p1_results},
            "phase2": p2_result}


def acquire_lock(lock, stale=LOCK_STALE):
    """Single-flight (best-effort): return an open fd, or None if a fresh lock is
    held. A lock older than `stale` is reclaimed (a crashed prior run). This is an
    optimization, not the authority — Phase 2's global DB lock + 6h cooldown is
    the real single-flight guarantee, so a rare reclaim race at worst starts a
    second process that the DB lock then short-circuits. Crash-safe: never raises
    on a vanished/contended lock; yields (returns None) to the winner."""
    lock = Path(lock)
    try:
        return os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            if time.time() - lock.stat().st_mtime < stale:
                return None
        except FileNotFoundError:
            pass                                   # vanished between EEXIST and stat
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
        try:
            return os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return None                            # another process reclaimed first


def main():
    root = hl.repo_root()
    now = int(time.time())
    lock = hl.state_dir(root) / "dream.lock"
    fd = acquire_lock(lock)
    if fd is None:
        json.dump({"status": "skipped", "reason": "another dream is running"},
                  sys.stdout)
        sys.stdout.write("\n")
        return
    conn = mdb.connect(root)
    try:
        result = run(conn, root, now)
    finally:
        conn.close()
        os.close(fd)
        Path(lock).unlink(missing_ok=True)
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
