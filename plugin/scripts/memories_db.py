#!/usr/bin/env python3
"""SQLite store for the dreaming pipeline (Codex `codex-memories` port).

`stage1_outputs` = per-rollout extracted memory + the usage curation columns;
`jobs` = lease/retry bookkeeping for Phase 1 (per thread) and the global Phase 2
lock. Schema and the selection / prune / usage queries are translated faithfully
from `codex-rs/state/src/runtime/memories.rs`; the multi-worker lease-contention
SQL is simplified (single-flight via the orchestrator's process lock — see
docs/design-docs/dreaming-v2.md).

Pure stdlib sqlite3. The db lives in gitignored runtime state
(`.claude/harness/memories.db`) — never under docs/ (ARCHITECTURE invariant 5).
"""
import os
import sqlite3

import harness_lib as hl

STAGE1 = "memory_stage1"
PHASE2 = "memory_consolidate_global"
PHASE2_KEY = "global"
DEFAULT_RETRIES = 3
PHASE2_COOLDOWN = 6 * 3600  # Codex: 6h cooldown between successful consolidations
DAY = 86400

SCHEMA = """
CREATE TABLE IF NOT EXISTS stage1_outputs (
    thread_id TEXT PRIMARY KEY,
    source_updated_at INTEGER NOT NULL,
    raw_memory TEXT NOT NULL,
    rollout_summary TEXT NOT NULL,
    rollout_slug TEXT,
    generated_at INTEGER NOT NULL,
    usage_count INTEGER,
    last_usage INTEGER,
    selected_for_phase2 INTEGER NOT NULL DEFAULT 0,
    selected_for_phase2_source_updated_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_stage1_source_updated
    ON stage1_outputs(source_updated_at DESC, thread_id DESC);
CREATE TABLE IF NOT EXISTS jobs (
    kind TEXT NOT NULL,
    job_key TEXT NOT NULL,
    status TEXT NOT NULL,
    worker_id TEXT,
    ownership_token TEXT,
    started_at INTEGER,
    finished_at INTEGER,
    lease_until INTEGER,
    retry_at INTEGER,
    retry_remaining INTEGER NOT NULL DEFAULT 3,
    last_error TEXT,
    input_watermark INTEGER,
    last_success_watermark INTEGER,
    PRIMARY KEY (kind, job_key)
);
CREATE INDEX IF NOT EXISTS idx_jobs_kind_status
    ON jobs(kind, status, retry_at, lease_until);
"""


def connect(root):
    """Open (creating) the dreaming db under gitignored runtime state."""
    db = hl.state_dir(root) / "memories.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _token():
    return os.urandom(16).hex()


# ---- stage1_outputs --------------------------------------------------------

def upsert_stage1_output(conn, thread_id, source_updated_at, raw_memory,
                         rollout_summary, rollout_slug, generated_at):
    """Insert/refresh a Phase-1 output; replaces only when the source is at
    least as new (Codex: `WHERE excluded.source_updated_at >= existing`)."""
    conn.execute(
        """INSERT INTO stage1_outputs
             (thread_id, source_updated_at, raw_memory, rollout_summary,
              rollout_slug, generated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(thread_id) DO UPDATE SET
             source_updated_at = excluded.source_updated_at,
             raw_memory = excluded.raw_memory,
             rollout_summary = excluded.rollout_summary,
             rollout_slug = excluded.rollout_slug,
             generated_at = excluded.generated_at
           WHERE excluded.source_updated_at >= stage1_outputs.source_updated_at""",
        (thread_id, source_updated_at, raw_memory, rollout_summary,
         rollout_slug, generated_at))
    conn.commit()


def select_phase2_inputs(conn, n, max_unused_days, now):
    """Top-N stage-1 outputs (Codex `get_phase2_input_selection`): eligible if
    used within the window, else (never used) fresh within the window; ranked by
    usage then recency; returned stable-sorted by thread_id ascending."""
    cutoff = now - max_unused_days * DAY
    rows = conn.execute(
        """SELECT thread_id, source_updated_at, raw_memory, rollout_summary,
                  rollout_slug, generated_at, usage_count, last_usage
             FROM stage1_outputs
            WHERE (length(trim(raw_memory)) > 0 OR length(trim(rollout_summary)) > 0)
              AND ((last_usage IS NOT NULL AND last_usage >= ?)
                   OR (last_usage IS NULL AND source_updated_at >= ?))
            ORDER BY COALESCE(usage_count, 0) DESC,
                     COALESCE(last_usage, source_updated_at) DESC,
                     source_updated_at DESC,
                     thread_id DESC
            LIMIT ?""",
        (cutoff, cutoff, max(1, min(n, 4096)))).fetchall()
    return sorted(rows, key=lambda r: r["thread_id"])


def prune_stage1_outputs(conn, max_unused_days, now, limit=256):
    """Delete dead rows: not in the last Phase-2 baseline AND stale past the
    window (Codex `prune_stage1_outputs_for_retention`). Returns count."""
    cutoff = now - max(0, max_unused_days) * DAY
    cur = conn.execute(
        """DELETE FROM stage1_outputs
            WHERE thread_id IN (
              SELECT thread_id FROM stage1_outputs
               WHERE selected_for_phase2 = 0
                 AND COALESCE(last_usage, source_updated_at) < ?
               ORDER BY COALESCE(last_usage, source_updated_at) ASC,
                        source_updated_at ASC, thread_id ASC
               LIMIT ?)""",
        (cutoff, limit))
    conn.commit()
    return cur.rowcount


def record_usage(conn, thread_ids, now):
    """Citation feedback: bump usage_count + last_usage (Codex
    `record_stage1_output_usage`). No live source until the read path returns;
    the schema is ready for it."""
    for tid in thread_ids:
        conn.execute(
            "UPDATE stage1_outputs SET usage_count = COALESCE(usage_count, 0) + 1, "
            "last_usage = ? WHERE thread_id = ?", (now, tid))
    conn.commit()


def mark_phase2_selected(conn, selected):
    """On Phase-2 success: clear the old baseline, mark the consumed rows
    (Codex sets selected_for_phase2 = 1 + the snapshot timestamp). `selected` is
    an iterable of (thread_id, source_updated_at)."""
    conn.execute(
        "UPDATE stage1_outputs SET selected_for_phase2 = 0, "
        "selected_for_phase2_source_updated_at = NULL "
        "WHERE selected_for_phase2 != 0 "
        "OR selected_for_phase2_source_updated_at IS NOT NULL")
    for tid, ts in selected:
        conn.execute(
            "UPDATE stage1_outputs SET selected_for_phase2 = 1, "
            "selected_for_phase2_source_updated_at = ? "
            "WHERE thread_id = ? AND source_updated_at = ?", (ts, tid, ts))
    conn.commit()


# ---- jobs: Phase 1 (per thread) --------------------------------------------

def stage1_needs_update(conn, thread_id, source_updated_at):
    """False if this thread's output and its last successful job are already at
    least as new as the source (Codex skip-up-to-date)."""
    o = conn.execute(
        "SELECT source_updated_at FROM stage1_outputs WHERE thread_id = ?",
        (thread_id,)).fetchone()
    if o and o["source_updated_at"] >= source_updated_at:
        return False
    j = conn.execute(
        "SELECT last_success_watermark FROM jobs WHERE kind = ? AND job_key = ?",
        (STAGE1, thread_id)).fetchone()
    if j and j["last_success_watermark"] is not None \
            and j["last_success_watermark"] >= source_updated_at:
        return False
    return True


def claim_stage1_job(conn, thread_id, worker_id, source_updated_at,
                     lease_seconds, now):
    """Lease a Phase-1 job for a thread, or None if already running / backing
    off / retry-exhausted. Single-flight scale: the orchestrator lock means no
    concurrent workers, so Codex's running-count subquery is dropped; lease +
    retry-backoff are kept."""
    row = conn.execute(
        "SELECT status, lease_until, retry_at, retry_remaining FROM jobs "
        "WHERE kind = ? AND job_key = ?", (STAGE1, thread_id)).fetchone()
    if row is not None:
        if row["status"] == "running" and (row["lease_until"] or 0) > now:
            return None
        if (row["retry_at"] or 0) > now:
            return None
        if row["status"] != "running" and (row["retry_remaining"] or 0) <= 0:
            return None
    token = _token()
    conn.execute(
        """INSERT INTO jobs (kind, job_key, status, worker_id, ownership_token,
                started_at, finished_at, lease_until, retry_at, retry_remaining,
                last_error, input_watermark, last_success_watermark)
           VALUES (?, ?, 'running', ?, ?, ?, NULL, ?, NULL, ?, NULL, ?, NULL)
           ON CONFLICT(kind, job_key) DO UPDATE SET
             status='running', worker_id=excluded.worker_id,
             ownership_token=excluded.ownership_token, started_at=excluded.started_at,
             finished_at=NULL, lease_until=excluded.lease_until, retry_at=NULL,
             last_error=NULL, input_watermark=excluded.input_watermark""",
        (STAGE1, thread_id, worker_id, token, now, now + lease_seconds,
         DEFAULT_RETRIES, source_updated_at))
    conn.commit()
    return token


def finish_stage1_job(conn, thread_id, token, source_updated_at, now, ok=True,
                      error=None, retry_delay=3600):
    """Mark a leased Phase-1 job done (advances last_success_watermark) or
    failed (record error, decrement retry, schedule backoff)."""
    if ok:
        conn.execute(
            "UPDATE jobs SET status='done', finished_at=?, lease_until=NULL, "
            "last_error=NULL, last_success_watermark=? "
            "WHERE kind=? AND job_key=? AND ownership_token=?",
            (now, source_updated_at, STAGE1, thread_id, token))
    else:
        conn.execute(
            "UPDATE jobs SET status='error', finished_at=?, lease_until=NULL, "
            "last_error=?, retry_at=?, retry_remaining=MAX(0, retry_remaining-1) "
            "WHERE kind=? AND job_key=? AND ownership_token=?",
            (now, error, now + retry_delay, STAGE1, thread_id, token))
    conn.commit()


# ---- jobs: Phase 2 (global lock) -------------------------------------------

def claim_phase2(conn, worker_id, lease_seconds, now):
    """Claim the single global Phase-2 lock, or None (running / 6h cooldown /
    retry backoff). Codex `try_claim_global_phase2_job`."""
    row = conn.execute(
        "SELECT status, lease_until, retry_at, finished_at, last_error FROM jobs "
        "WHERE kind=? AND job_key=?", (PHASE2, PHASE2_KEY)).fetchone()
    if row is not None:
        if (row["retry_at"] or 0) > now:
            return None
        if row["status"] == "running" and (row["lease_until"] or 0) > now:
            return None
        if row["last_error"] is None and row["finished_at"] is not None \
                and row["finished_at"] > now - PHASE2_COOLDOWN:
            return None
    token = _token()
    conn.execute(
        """INSERT INTO jobs (kind, job_key, status, worker_id, ownership_token,
                started_at, finished_at, lease_until, retry_at, retry_remaining,
                last_error, input_watermark, last_success_watermark)
           VALUES (?, ?, 'running', ?, ?, ?, NULL, ?, NULL, ?, NULL, 0, NULL)
           ON CONFLICT(kind, job_key) DO UPDATE SET
             status='running', worker_id=excluded.worker_id,
             ownership_token=excluded.ownership_token, started_at=excluded.started_at,
             finished_at=NULL, lease_until=excluded.lease_until, retry_at=NULL,
             last_error=NULL""",
        (PHASE2, PHASE2_KEY, worker_id, token, now, now + lease_seconds,
         DEFAULT_RETRIES))
    conn.commit()
    return token


def heartbeat_phase2(conn, token, lease_seconds, now):
    """Extend the Phase-2 lease while the agent runs; False if we no longer own
    it (Codex heartbeats every 90s)."""
    cur = conn.execute(
        "UPDATE jobs SET lease_until=? WHERE kind=? AND job_key=? "
        "AND status='running' AND ownership_token=?",
        (now + lease_seconds, PHASE2, PHASE2_KEY, token))
    conn.commit()
    return cur.rowcount > 0


def finish_phase2(conn, token, now, ok=True, error=None, retry_delay=3600):
    if ok:
        conn.execute(
            "UPDATE jobs SET status='done', finished_at=?, lease_until=NULL, "
            "last_error=NULL WHERE kind=? AND job_key=? AND status='running' "
            "AND ownership_token=?", (now, PHASE2, PHASE2_KEY, token))
    else:
        conn.execute(
            "UPDATE jobs SET status='error', finished_at=?, lease_until=NULL, "
            "last_error=?, retry_at=? WHERE kind=? AND job_key=? "
            "AND status='running' AND ownership_token=?",
            (now, error, now + retry_delay, PHASE2, PHASE2_KEY, token))
    conn.commit()
