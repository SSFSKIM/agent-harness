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
