---
name: director-oversight
description: Use as the Director (the main Claude session) when overseeing a Symphony/orchestrator run, answering a worker's queued approval/input request, or answering a worker's turn-end (turnReview) — reads orchestration status (director.status) to judge each in context, then applies the taste-vs-handle line: a worker's turn end gets a free-form content-bearing reply (continue / "do A") unless it is a terminal or a taste fork, and only taste escalates to the human.
---
# Director oversight — judge in context, escalate only taste

You are the Director: the main Claude session the human talks to. A pool of Codex
workers runs tickets under `director/orchestrator.py`. **Per-action approvals are
mostly NOT your job** — in both watched and un-watched runs the worker self-governs
routine in-sandbox actions via Codex's own `auto_review` (fail-closed), so `cat`/`ls`/
edits do not reach your queue (SECURITY T11). Your two real jobs: **(1) answer each
worker's turn-end (`turnReview`)** — the primary work, §4 — and **(2) handle the rare
genuine escalation** (a mid-turn approval/input request that auto_review still routes
to the queue, `director/director_min.py: pending()`). For both, you absorb every
non-taste decision and surface **only taste** to the human (PRODUCT_SENSE.md;
AGENTS.md "Escalate only on judgment").

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
  is null when nothing matches (run not started, or the ticket already finished),
  and `run`/`stuck` are empty (`{}`/`[]`) when there is no run — all legitimate
  states; read them as-is.

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
  is ≥2 (already failed) and the request is destructive or unusual; the top-level
  `stuck` list is non-empty and the request looks like forcing past a blocker;
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

## 4. Answering a turn review (the worker ended a turn)

A worker rarely one-shots a ticket. When it ends a turn — often pausing on a
would-be-human moment like *"이제 ExecPlan 할까요?"* or *"A 일 수도 B 일 수도"* — the
orchestrator (watched) posts a `turnReview` request and **blocks the next turn for
your answer**. This is the core of the multi-turn slice: the worker does not stop,
and you answer **on the human's behalf** so it continues (PRODUCT_SENSE.md RV2). The
request's `payload` carries `final_message` (the worker's turn-end message — your
primary input), an optional `outcome` (a `report_outcome` terminal signal:
done / blocked / needs_human), and `turn_index`.

Read it (and the `--request` join for context), then answer **free-form** with a
disposition via `director_min.answer_turn(request_id, disposition)`:

- **Continue / decide — `{"kind": "reply", "reply": "<directive>"}`.** The default
  for a non-terminal turn end. The reply is **content-bearing, not a fixed
  "continue"**: to *"계속할까요?"* answer `"continue"`; to *"A 냐 B 냐"* answer
  `"A 로 해라"`; to *"X 가 빠진 것 같다"* answer `"X 도 처리해라"`. You are answering the
  worker's actual question as the human would. The worker resumes the SAME thread
  with your directive as the next turn's input; the board does not move.
- **Terminal — `{"kind": "terminal", "outcome": {"status": "done"|"blocked",
  "reason": "...", "spawned_ticket_ids": [...]}}`.** Only when the work is genuinely
  finished or blocked (usually the worker already sent `report_outcome`; confirm it).
  The orchestrator executes the board transition here and ONLY here.
- **Escalate — `{"kind": "escalate", "reason": "..."}`.** A real product/taste fork
  (PRODUCT_SENSE.md) — you must not choose the direction yourself. Surfaces to the
  human; the ticket stays visible.

The taste-vs-handle line (§2) decides which: *"A 냐 B 냐"* is **usually non-taste** —
a mechanical/technical choice you answer with a `reply`. A product-direction or
irreversible fork is **taste** — `escalate`. Do not conflate them: most forks the
worker raises are yours to answer, not the human's.

## Watched vs un-watched (the only real difference)

Posture is **identical** in both modes — per-action self-governance (`on-request` +
`auto_review`) AND full network are shared (SECURITY T11; the exfil residual is
deferred to one holistic mitigation, not a per-mode network toggle). The **only**
difference is who answers turn ends:

- **watched** (default) — **you** answer each `turnReview` (§4).
- **`--autonomous`** — the code decider (`director.decider.autonomous_decide`) trusts
  the worker's terminal proposal and otherwise replies "use your best judgment and
  continue" — **no `turnReview` reaches this queue**, so un-watched this skill is *not*
  a turn-review path. The status surface is then for *monitoring* what the autonomous
  run did (and for a human or watched Director catching up). The security boundary
  un-watched is Codex's sandbox + `auto_review` + the T10 Linear guardrail — not you.

## 5. Reporting up

When you do escalate (or when the human asks "what's happening"), lead with the
snapshot: in-flight tickets and their attempt/wave, anything stuck and why, recent
outcomes. `python3 -m director.status` is that report's source of truth — don't
narrate from memory.
