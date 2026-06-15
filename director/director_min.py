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


def answer_turn(request_id: str, disposition: dict, *, base=None,
                answered_by: str = "director") -> None:
    """Answer a `turnReview` request with a drive disposition
    ({"kind": "terminal"|"reply"|"escalate", ...}). The main session calls this after
    reading the turn-end (final_message + outcome) per docs/DIRECTOR.md §4 —
    the FREE-FORM equivalent of `answer` for the multi-turn turn-end seam (D-45)."""
    dq.write_answer({"request_id": request_id, "answered_by": answered_by,
                     "answered_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     "disposition": disposition}, base=base)


def auto_respond(base=None, decide: Callable[[dict], str] = lambda req: "accept",
                 stop: threading.Event | None = None, poll_s: float = 0.02) -> None:
    """Answer pending APPROVAL/INPUT requests with decide(req) until `stop` is set
    (unattended/tests). Skips `turnReview` requests — those need a free-form
    disposition (answer_turn), not a decision string, so a fixed-policy responder
    must not touch them."""
    stop = stop or threading.Event()
    while not stop.is_set():
        for req in pending(base=base):
            if req.get("kind") == "turnReview":
                continue
            answer(req["request_id"], decide(req), base=base)
        time.sleep(poll_s)
