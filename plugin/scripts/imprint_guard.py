#!/usr/bin/env python3
"""Idempotency guard for memory write-back (RELIABILITY R1).

Dedupe key = session_id:event[:bucket]. Hooks may fire twice for one event;
the queue is at-least-once (R4); this guard makes processing exactly-once.
"""
import harness_lib as hl


def _log(root):
    return hl.state_dir(root) / "imprint-processed.txt"


def key(session_id, event, bucket=""):
    return f"{session_id}:{event}:{bucket}" if bucket else f"{session_id}:{event}"


def already_processed(root, k):
    p = _log(root)
    return p.exists() and k in p.read_text(encoding="utf-8").split()


def mark_processed(root, k):
    with open(_log(root), "a", encoding="utf-8") as f:
        f.write(k + "\n")
