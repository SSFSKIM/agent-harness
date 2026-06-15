"""Turn-end deciders for the multi-turn drive loop (multi-turn-ticket-execution
slice, D-45).

A *decider* is `decide(ctx) -> disposition`: given a turn-end context
(`{ticket, turn_index, status, final_message, outcome}`) it returns what to do
next. It is the injected judge that makes watched and un-watched two implementations
of one interface — `director.run.drive` routes on the disposition `kind` without
knowing which world it is in:

  {"kind": "terminal", "outcome": {...}}        -> board transition (orchestrator)
  {"kind": "escalate", "reason": str, ...}      -> human (taste)
  {"kind": "reply",    "reply": str}            -> feed as the next turn's input

`outcome` in the context is the worker's PROPOSED terminal signal from the
`report_outcome` tool (`{status, reason, spawned_ticket_ids}`), or None when the
turn ended without one (the common prose case — "A 일 수도 B 일 수도").

This module ships the **un-watched (autonomous) code decider**. The **watched**
decider (the main session answering free-form via the Director queue) is wired in
the orchestrator slice (M3).
"""
from __future__ import annotations

import datetime

import director.queue as dq

# Queue request kind for a turn-end the watched Director must answer (free-form).
TURN_REVIEW_KIND = "turnReview"

# The un-watched default reply for a non-terminal prose turn-end. NOT a fixed
# "continue": it is a content-bearing directive that generalizes "self-resolve and
# continue" — the worker is an LLM, so at a fork it decides rather than stops
# (spec R5/D-45). A watched run would instead get a bespoke human/Director answer.
CONTINUE_REPLY = (
    "Continue with your best judgment. If you reached a fork (e.g. approach A vs B), "
    "pick the most reasonable option, briefly note the choice and why, and proceed — "
    "do not stop to ask. Call report_outcome only when the ticket is truly done, you "
    "are blocked, or a human product/taste decision is genuinely required."
)


def autonomous_decide(ctx: dict) -> dict:
    """Un-watched decider — pure code, no LLM, no human (spec R5).

    Trust the worker's terminal *proposal*; for a non-terminal turn-end there is no
    bespoke Director to answer, so the default is "self-resolve and continue" (a
    content-bearing directive, D-45). `needs_human` is the one thing code cannot
    resolve — it escalates (a watched run parks + notifies a human async)."""
    outcome = ctx.get("outcome")
    if outcome:
        status = outcome.get("status")
        if status in ("done", "blocked"):
            return {"kind": "terminal", "outcome": outcome}
        if status == "needs_human":
            return {"kind": "escalate",
                    "reason": outcome.get("reason") or "worker requested a human decision",
                    "outcome": outcome}
    # No terminal signal → non-terminal turn-end → keep working (self-resolve).
    return {"kind": "reply", "reply": CONTINUE_REPLY}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def disposition_from_answer(answer: dict | None) -> dict:
    """Map a Director's turn-review answer to a drive disposition. The Director writes
    `{"disposition": {"kind": "terminal"|"reply"|"escalate", ...}}` (via
    director_min.answer_turn). A missing answer (timeout) or a malformed one →
    escalate: in a watched run a no-answer should SURFACE to the human, never
    fabricate progress or silently burn turns (mirrors the approval seam's
    surface-the-default discipline)."""
    if isinstance(answer, dict):
        disp = answer.get("disposition")
        if isinstance(disp, dict) and disp.get("kind") in ("terminal", "reply", "escalate"):
            return disp
    return {"kind": "escalate", "reason": "turn review unanswered or malformed"}


def make_queue_decider(base=None, timeout_s: float = 300.0, now=_now_iso):
    """Watched decider (spec R5): post each turn-end to the Director queue and block
    for the main session's FREE-FORM answer. The Director reads `final_message` +
    `outcome` (director-oversight skill) and writes a disposition — terminal
    (review+execute), a content-bearing reply ("A 로 해라"), or escalate. Same
    request/answer channel as the approval seam — no new transport, no headless
    Director (the recurring anti-pattern this design refuses, [[no-headless-director-codex-owns-approval]])."""
    def decide(ctx: dict) -> dict:
        ticket = ctx.get("ticket") or {}
        tid = str(ticket.get("id"))
        turn_index = ctx.get("turn_index")
        rid = f"{tid}|turn|{turn_index}"
        dq.append_request({
            "request_id": rid,
            "ticket_id": tid,
            "session_id": f"{tid}-turn{turn_index}",
            "kind": TURN_REVIEW_KIND,
            "payload": {"final_message": ctx.get("final_message"),
                        "outcome": ctx.get("outcome"),
                        "turn_index": turn_index},
            "workspace_path": ticket.get("workspace"),
            "created_at": now(),
        }, base=base)
        answer = dq.wait_for_answer(rid, base=base, timeout_s=timeout_s)
        return disposition_from_answer(answer)
    return decide
