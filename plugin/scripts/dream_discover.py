#!/usr/bin/env python3
"""Rollout discovery for the dreaming pipeline (Codex `claim_stage1_jobs_for_startup` port).

A *rollout* = one past Claude Code session transcript. Claude stores each repo's
sessions as `<claude_home>/projects/<slug>/<session-id>.jsonl`; the filename stem
is the session id (= our `thread_id`) and the file mtime is the last-activity
(age/idle) signal. Discovery is pure metadata — filename + mtime, no transcript
read (Codex works off its `threads` registry the same way; content filtering is
Phase 1's job in dream_phase1.py).

Faithful to Codex: SCAN the eligibility window most-recent-first up to a bound,
then CLAIM up to `max_rollouts_per_startup` of the scanned set that still need a
Phase-1 update (skip up-to-date) and aren't already leased. Each claim is a DB
lease (`memories_db.claim_stage1_job`); single-flight at our scale.

Eligibility window (Codex `MemoriesConfig`): not the current session, fresh
enough (`mtime >= now - max_rollout_age_days`) AND idle enough (`mtime <= now -
min_rollout_idle_hours`, so an active session is never summarized). The idle
bound alone already drops the still-warm current session; `exclude` is
belt-and-suspenders.

The CLI is read-only inspection (`--claim` to actually lease) — the orchestrator
(dream_run.py) imports `discover_rollouts`/`claim_rollouts` directly.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import harness_lib as hl
import memories_db as mdb

# Codex MemoriesConfig defaults (config/src/types.rs) — constants for v2; the
# dreaming-v2 design doc records these. Overridable via config later.
MAX_ROLLOUTS_PER_STARTUP = 2
MAX_ROLLOUT_AGE_DAYS = 10
MIN_ROLLOUT_IDLE_HOURS = 6
THREAD_SCAN_LIMIT = 64        # Codex stage_one::THREAD_SCAN_LIMIT (bounded scan)
JOB_LEASE_SECONDS = 3600      # Codex stage_one::JOB_LEASE_SECONDS
DAY = 86400
HOUR = 3600


def discover_rollouts(tdir, now, *, max_age_days=MAX_ROLLOUT_AGE_DAYS,
                      min_idle_hours=MIN_ROLLOUT_IDLE_HOURS,
                      scan_limit=THREAD_SCAN_LIMIT, exclude=()):
    """Eligible past-session transcripts, freshest-first, capped at `scan_limit`.

    Returns `[(thread_id, transcript_path, source_updated_at)]`. A rollout is
    eligible when it is not in `exclude` and its mtime falls inside the inclusive
    window `[now - max_age_days, now - min_idle_hours]` — fresh enough to still
    matter, idle enough to be finished (Codex: `updated_at >= max_age_cutoff AND
    updated_at <= idle_cutoff`). `source_updated_at` is integer-seconds mtime, to
    match the rest of the store.
    """
    tdir = Path(tdir)
    if not tdir.exists():
        return []
    age_cutoff = now - max(0, max_age_days) * DAY      # mtime must be >= this
    idle_cutoff = now - max(0, min_idle_hours) * HOUR  # mtime must be <= this
    exclude = set(exclude)
    rows = []
    for p in tdir.glob("*.jsonl"):
        tid = p.stem
        if tid in exclude:
            continue
        try:
            mtime = int(p.stat().st_mtime)
        except OSError:
            continue
        if mtime < age_cutoff or mtime > idle_cutoff:
            continue
        rows.append((tid, p, mtime))
    # freshest-first; thread_id breaks ties deterministically (Codex ORDER BY
    # updated_at DESC, then a stable id).
    rows.sort(key=lambda r: (r[2], r[0]), reverse=True)
    return rows[:max(0, scan_limit)]


def claim_rollouts(conn, rollouts, worker_id, now, *,
                   max_claimed=MAX_ROLLOUTS_PER_STARTUP,
                   lease_seconds=JOB_LEASE_SECONDS):
    """Claim up to `max_claimed` of the scanned `rollouts` that still need a
    Phase-1 update and aren't already leased (Codex: iterate freshest-first, skip
    up-to-date, lease each). Returns
    `[(thread_id, transcript_path, source_updated_at, ownership_token)]`."""
    claimed = []
    for tid, path, src_ts in rollouts:
        if len(claimed) >= max_claimed:
            break
        if not mdb.stage1_needs_update(conn, tid, src_ts):
            continue
        token = mdb.claim_stage1_job(conn, tid, worker_id, src_ts,
                                     lease_seconds, now)
        if token is not None:
            claimed.append((tid, path, src_ts, token))
    return claimed


def main():
    ap = argparse.ArgumentParser(
        description="Discover (and optionally claim) eligible dreaming rollouts.")
    ap.add_argument("--root", default=None, help="repo root (default: resolved)")
    ap.add_argument("--claim", action="store_true",
                    help="lease the claimable rollouts in the db (mutates state)")
    args = ap.parse_args()
    root = Path(args.root).resolve() if args.root else hl.repo_root()
    now = int(time.time())
    tdir = hl.project_transcripts_dir(root)
    rollouts = discover_rollouts(tdir, now)
    out = {
        "transcripts_dir": str(tdir),
        "eligible": [
            {"thread_id": t, "source_updated_at": ts,
             "idle_hours": round((now - ts) / HOUR, 1)}
            for t, _p, ts in rollouts],
    }
    if args.claim:
        conn = mdb.connect(root)
        try:
            claimed = claim_rollouts(conn, rollouts, f"dream-{os.getpid()}", now)
            out["claimed"] = [t for t, _p, _ts, _tok in claimed]
        finally:
            conn.close()
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
