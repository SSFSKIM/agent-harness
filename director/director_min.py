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
    reading the turn-end (final_message + outcome) per .claude/DIRECTOR.md §4 —
    the FREE-FORM equivalent of `answer` for the multi-turn turn-end seam (D-45)."""
    dq.write_answer({"request_id": request_id, "answered_by": answered_by,
                     "answered_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     "disposition": disposition}, base=base)


def merge_reviews(base=None) -> list[dict]:
    """Pending merge-escalations the serialized PR-merger raised (R6) — the merge half
    of the Director's inbox (cf. `pending()` for approvals, `turnReview` for turn-ends).
    Each payload carries {pr, branch, result, reason, disposition, attempt}; the Director
    reads these per .claude/DIRECTOR.md §7 and resolves each (requeue+guidance / abandon /
    human)."""
    return [r for r in dq.read_pending(base=base) if r.get("kind") == "mergeReview"]


def answer_merge_review(request_id: str, disposition: dict, *, base=None,
                        answered_by: str = "director") -> None:
    """Mark a `mergeReview` HANDLED (removes it from the inbox). `disposition` records
    how the Director resolved the failed merge for the audit trail, e.g.
    {"action": "requeue"|"abandon"|"human", "note": "…"}. For a guided retry use
    `requeue_merge` (it calls this AND re-enqueues); use this directly for
    abandon / human (.claude/DIRECTOR.md §7)."""
    dq.write_answer({"request_id": request_id, "answered_by": answered_by,
                     "answered_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     "merge_review_disposition": disposition}, base=base)


def requeue_merge(review: dict, *, note: str, base=None, max_attempts: int = 3,
                  preservation_override: bool = False,
                  answered_by: str = "director") -> dict:
    """Re-enqueue an escalated PR WITH the Director's guidance — the re-enqueue loop (D-48).

    The Director, having read a `mergeReview` and decided the fix is mechanical/settled,
    calls this: it marks the review handled (`action=requeue`) and posts a FRESH
    `mergeRequest` at `attempt+1` carrying `note` as the land agent's guidance (rendered
    into the land prompt by `merger.land_prompt`), so the next attempt follows the
    directive that should resolve the escalation. pr/branch/workspace are read off the
    review. Capped at `max_attempts` (default 3): beyond it this REFUSES — it returns
    `{"requeued": False, "reason": "max_attempts", ...}` and leaves the review OPEN so the
    Director explicitly abandons or escalates to the human, never a silent infinite retry.
    Returns `{"requeued": bool, "attempt": <next or current>, ...}`."""
    payload = review.get("payload") or {}
    attempt = payload.get("attempt", 1)
    next_attempt = attempt + 1
    if next_attempt > max_attempts:
        return {"requeued": False, "reason": "max_attempts", "attempt": attempt,
                "max_attempts": max_attempts}
    # Enqueue the retry FIRST, THEN answer/consume the review (review fix): if the enqueue
    # raises, the review stays OPEN (retryable) — never consumed-without-a-retry. A dedup
    # (the attempt+1 request already exists from a prior requeue) is an idempotent no-op:
    # don't rewrite the review's recorded guidance to diverge from the queued retry.
    queued = dq.append_merge_request(
        review.get("ticket_id"), pr=payload.get("pr"), branch=payload.get("branch"),
        workspace_path=review.get("workspace_path"), guidance=note,
        attempt=next_attempt, preservation_override=preservation_override, base=base)
    if not queued:
        return {"requeued": False, "reason": "already_queued", "attempt": next_attempt}
    answer_merge_review(review["request_id"], {"action": "requeue", "note": note},
                        base=base, answered_by=answered_by)
    return {"requeued": True, "attempt": next_attempt}


# Kinds the fixed-policy responder must NOT touch: `turnReview` needs a free-form
# disposition (answer_turn); `mergeRequest` is the serialized merger's worklist
# (answering it would silently consume the merge); `mergeReview` is a merge-escalation
# the live Director resolves with judgment (answer_merge_review), never a fixed accept.
_NON_APPROVAL_KINDS = ("turnReview", "mergeRequest", "mergeReview")


def auto_respond(base=None, decide: Callable[[dict], str] = lambda req: "accept",
                 stop: threading.Event | None = None, poll_s: float = 0.02) -> None:
    """Answer pending APPROVAL/INPUT requests with decide(req) until `stop` is set
    (unattended/tests). Skips `turnReview`/`mergeRequest` requests — those are not
    approval decisions a fixed-policy responder may answer (see _NON_APPROVAL_KINDS)."""
    stop = stop or threading.Event()
    while not stop.is_set():
        for req in pending(base=base):
            if req.get("kind") in _NON_APPROVAL_KINDS:
                continue
            answer(req["request_id"], decide(req), base=base)
        time.sleep(poll_s)
