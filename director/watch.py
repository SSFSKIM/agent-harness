"""Event-wake emitter for the watched Director (tier-2 self-driving Director).

`python3 -m director.watch --kinds turnReview,mergeReview,runReport` tails the Director
queue AND the orchestration status snapshot, printing ONE compact JSON line per newly-
pending queue request (deduped by request_id) and per run-level terminal (a `runReport`,
deduped per run). Wired into a `Monitor`, each line becomes a session notification — so the
Director is woken EXACTLY when a worker needs input OR a run reaches a terminal it should
pull the human for, with no timer polling on the session itself (cf. ScheduleWakeup, which
burns a session turn per tick). The polling lives here, in a cheap subprocess, OFF the
session.

A request stays pending until answered, so the `seen` set guarantees each fires
exactly once. Only stdout is the event stream; we flush per line so the monitor sees
each event immediately.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import director.queue as dq
from director import status


def new_pending(pending: list[dict], seen: set, kinds: set | None = None) -> list[dict]:
    """The pending requests whose request_id is NEW (not in `seen`), filtered to
    `kinds` if given. Mutates `seen` to include the returned ids — so a request that
    stays pending across polls is emitted exactly once. Pure except for `seen`."""
    out = []
    for r in pending:
        rid = r.get("request_id")
        if rid is None or rid in seen:
            continue
        if kinds and r.get("kind") not in kinds:
            continue
        seen.add(rid)
        out.append(r)
    return out


def _emit_line(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()  # per-line flush so Monitor delivers each event without buffering


def _emit(req: dict) -> None:
    _emit_line({"request_id": req.get("request_id"), "kind": req.get("kind"),
                "ticket_id": req.get("ticket_id"), "payload": req.get("payload")})


def _run_summary(snapshot: dict | None) -> dict:
    """Compact run tally for the runReport notification line — recent outcomes by status +
    stuck/in-flight counts. The Director reads `director.status` for the full digest; this
    just makes the wake-up notification informative."""
    snap = snapshot or {}
    by_status: dict = {}
    for r in snap.get("recent", []):
        s = r.get("status") or "unknown"
        by_status[s] = by_status.get(s, 0) + 1
    return {"by_status": by_status, "stuck": len(snap.get("stuck", [])),
            "in_flight": len(snap.get("in_flight", []))}


def new_run_report(snapshot: dict | None, seen: set, kinds: set | None = None) -> dict | None:
    """A `runReport` event when the status snapshot shows a NEW run terminal, else None.

    Fires once per run: `run.stopped_reason` non-None (the orchestrator's `finished()` terminal —
    drained/stuck/max_passes/max_dispatched/poll_failed/pass_complete) AND `(started_at,
    stopped_reason)` not yet emitted. A new run (new `started_at`) re-emits; a re-poll of the same
    terminal does not. Honors the `--kinds` filter (None = all). Mutates `seen`. Tolerant: a
    None/empty snapshot (no run / unreadable, per read_status) yields None — never raises. This is
    the run-level PULL surface (the Director composes a digest + PushNotifications on it)."""
    if kinds is not None and "runReport" not in kinds:
        return None
    run = (snapshot or {}).get("run") or {}
    reason = run.get("stopped_reason")
    if not reason:
        return None
    key = (run.get("started_at"), reason)
    if key in seen:
        return None
    seen.add(key)
    return {"kind": "runReport", "reason": reason, "run": run,
            "summary": _run_summary(snapshot)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="director.watch")
    ap.add_argument("--kinds", default=None,
                    help="comma-separated request kinds to emit (default: all)")
    ap.add_argument("--queue-dir", default=None, help="Director queue dir override")
    ap.add_argument("--status-dir", default=None,
                    help="orchestration status dir to tail for run-level reports (runReport)")
    ap.add_argument("--poll", type=float, default=0.5, help="poll interval seconds")
    ap.add_argument("--once", action="store_true",
                    help="single pass then exit (tests); else loop forever")
    args = ap.parse_args(argv)
    kinds = {k.strip() for k in args.kinds.split(",") if k.strip()} if args.kinds else None
    seen: set = set()       # request_id dedupe (queue events)
    run_seen: set = set()   # (started_at, stopped_reason) dedupe (run-level reports)
    while True:
        try:
            pending = dq.read_pending(base=args.queue_dir)
        except Exception:  # a transient/missing queue read must not kill the watch
            pending = []
        for req in new_pending(pending, seen, kinds):
            _emit(req)
        try:
            snap = status.read_status(base=args.status_dir)
        except Exception:  # a transient/torn status read must not kill the watch
            snap = None
        ev = new_run_report(snap, run_seen, kinds)
        if ev is not None:
            _emit_line(ev)
        if args.once:
            return 0
        time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
