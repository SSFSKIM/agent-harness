"""Minimal Director responder (Phase 1, M4): the main session's hands on the queue.

Decision D-5: the Director is the main Claude session you talk to — it lists
pending requests and answers the non-taste ones (escalating only taste to the
human). These helpers are that surface. `auto_respond` answers with a fixed policy
so an unattended run or a test can let the worker resume; the real main session
calls `pending`/`answer` itself and applies judgment per request.
"""
from __future__ import annotations

import datetime
import threading
import time
from typing import Callable

import director.queue as dq


def pending(base=None) -> list[dict]:
    """Requests waiting for a Director decision."""
    return dq.read_pending(base=base)


def answer(request_id: str, decision: str | None = None, *, answers=None,
           base=None, answered_by: str = "director") -> None:
    """Write one answer. `decision` for approvals, `answers` for input requests."""
    payload = {"request_id": request_id, "answered_by": answered_by,
               "answered_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    if decision is not None:
        payload["decision"] = decision
    if answers is not None:
        payload["answers"] = answers
    dq.write_answer(payload, base=base)


def auto_respond(base=None, decide: Callable[[dict], str] = lambda req: "accept",
                 stop: threading.Event | None = None, poll_s: float = 0.02) -> None:
    """Answer pending requests with decide(req) until `stop` is set (unattended/tests)."""
    stop = stop or threading.Event()
    while not stop.is_set():
        for req in pending(base=base):
            answer(req["request_id"], decide(req), base=base)
        time.sleep(poll_s)
