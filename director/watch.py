"""Event-wake emitter for the watched Director (tier-2 self-driving Director).

`python3 -m director.watch --kinds turnReview` tails the Director queue and prints
ONE compact JSON line per newly-pending request (deduped by request_id). Wired into a
`Monitor`, each line becomes a session notification — so the Director is woken EXACTLY
when a worker needs input, with no timer polling on the session itself (cf.
ScheduleWakeup, which burns a session turn per tick). The polling lives here, in a
cheap subprocess, OFF the session.

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


def _emit(req: dict) -> None:
    line = json.dumps({"request_id": req.get("request_id"), "kind": req.get("kind"),
                       "ticket_id": req.get("ticket_id"), "payload": req.get("payload")},
                      ensure_ascii=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()  # per-line flush so Monitor delivers each event without buffering


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="director.watch")
    ap.add_argument("--kinds", default=None,
                    help="comma-separated request kinds to emit (default: all)")
    ap.add_argument("--queue-dir", default=None, help="Director queue dir override")
    ap.add_argument("--poll", type=float, default=0.5, help="poll interval seconds")
    ap.add_argument("--once", action="store_true",
                    help="single pass then exit (tests); else loop forever")
    args = ap.parse_args(argv)
    kinds = {k.strip() for k in args.kinds.split(",") if k.strip()} if args.kinds else None
    seen: set = set()
    while True:
        try:
            pending = dq.read_pending(base=args.queue_dir)
        except Exception:  # a transient/missing queue read must not kill the watch
            pending = []
        for req in new_pending(pending, seen, kinds):
            _emit(req)
        if args.once:
            return 0
        time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
