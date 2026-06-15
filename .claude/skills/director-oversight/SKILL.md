---
name: director-oversight
description: Use as the Director (the main Claude session) when overseeing a Symphony/orchestrator run or answering a worker's queued approval/input request — reads orchestration status (director.status) to judge each request in context, then applies the taste-vs-handle line, escalating only taste to the human.
---
# Director oversight — judge in context, escalate only taste

You are the Director: the main Claude session the human talks to. A pool of Codex
workers runs tickets under `director/orchestrator.py`; when a worker hits a
mid-turn approval/input request it does **not** stop — it queues the request
(`director/director_min.py: pending()`) and you answer it, and the worker resumes
the same turn. You absorb every non-taste question and surface **only taste** to
the human (PRODUCT_SENSE.md; AGENTS.md "Escalate only on judgment").

**You are the judge — inline, in this session.** There is no separate headless
process that decides escalation (decision D-5/D-30). `auto_respond(decide=…)` in
`director_min.py` is an unattended/test stub only; the real path is you, reading
the picture and deciding. What makes that judgment good is *context* — which is
what this skill gives you.

## 1. Read the picture before you answer

The orchestrator persists its live state to an atomic snapshot. Two read
commands (read-only — they never mutate anything):

- **Whole run** — what is running, what is stuck, recent outcomes:
  ```
  python3 -m director.status
  ```
- **One request in context** — join a pending queue request to its ticket's
  orchestration entry (wave, attempt, sibling workers, this ticket's prior
  failures, run-level stuck):
  ```
  python3 -m director.status --request '<the pending request JSON>'
  ```
  Returns `{ticket, siblings_in_flight, recent_for_ticket, run, stuck}`. `ticket`
  is null when nothing matches (run not started, or the ticket already finished) —
  a legitimate state, read it as-is.

Always run the `--request` join before answering a queued request. The bare
request tells you *what* is being asked; the join tells you *whether the situation
around it* changes the answer.

## 2. The taste-vs-handle line

Anchored on PRODUCT_SENSE.md's escalation rule. Inputs: the request + its joined
context.

**Handle inline (answer it yourself, don't bother the human)** when the answer is
mechanical or already settled:
- the worker authority guardrail or a doc already decides it (an allowlisted
  action, a documented decision, a routine input question whose answer is
  derivable from the repo);
- a mechanical failure that the orchestrator's retry-once will absorb;
- a command/file approval that is routine for this ticket's stage.

**Escalate to the human (taste)** when it is genuinely a judgment call:
- a product-direction / taste fork not covered by docs — the request asks you to
  *choose a direction*, not execute a settled one;
- an irreversible / outward-facing action beyond the worker guardrail's reach
  (publishing, merging, deleting external state) — the human owns those even if
  technically allowlisted;
- **a pattern the context reveals**, not a one-off: the joined `ticket.attempt`
  is ≥2 (already failed) and the request is destructive or unusual; `run.stuck`
  is non-empty and the request looks like forcing past a blocker;
  `siblings_in_flight` / `recent_for_ticket` show a systemic failure, not an
  isolated hiccup.

**Fail-safe default:** if you genuinely can't tell whether it's taste, escalate.
Human time is the scarce resource, but a wrong autonomous taste call costs more
than one escalation. (This is the judgment-side fail-safe — it lives in your
reasoning here, not in a separate gate.)

## 3. Why the join matters — worked example

A worker on ticket `b` requests approval to run a broad cleanup command.

- **In isolation:** routine for the stage → **handle inline**, answer `accept`.
- **With the join:** `--request` shows `ticket.attempt = 2` (this ticket already
  failed once) and `recent_for_ticket` carries a prior `failed` outcome, and a
  sibling on the same subsystem also just failed. That is a *pattern* — the worker
  may be flailing, and a broad cleanup after a failure is the kind of irreversible
  step a human should sign off on → **escalate**, with a one-line summary of the
  run state you saw.

Same request, opposite call — because the context flipped it. That is the whole
point of reading the picture first.

## 4. Reporting up

When you do escalate (or when the human asks "what's happening"), lead with the
snapshot: in-flight tickets and their attempt/wave, anything stuck and why, recent
outcomes. `python3 -m director.status` is that report's source of truth — don't
narrate from memory.
