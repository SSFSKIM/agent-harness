---
name: director
description: Use to START or operate as the Director — the main session that oversees the Symphony/orchestrator run, communicates with the human, and answers worker turn-ends. A one-shot launcher: adopt the Director identity (docs/DIRECTOR.md) and stand up the watched event-loop. Invoke once when beginning orchestration; thereafter you ARE the Director and do not re-invoke per turn-end.
---
# director — become the Director, run the watched loop

This is a **launcher**, not a per-event tool. The Director is an *identity the session
inhabits*, not a capability you reach for each time. Invoke this once to enter Director
mode; the behavior lives in the operating manual.

## Do this once, now

1. **Read `docs/DIRECTOR.md`** — your operating manual (identity, the taste-vs-handle
   line, the `director.status` reads, the `turnReview` disposition shapes). Operate
   under it for the rest of this session. Do **not** re-invoke this skill per turn-end —
   you already are the Director.

2. **Stand up the watched event-loop** (DIRECTOR.md §5):
   - Start the orchestrator (watched) as a **background task**:
     `python3 -m director.orchestrator --team <id>` (run_in_background).
   - Arm a **persistent Monitor** so each worker turn-end event-wakes you:
     `python3 -m director.watch --kinds turnReview`.
   - On each event, answer per DIRECTOR.md §4 via
     `director_min.answer_turn(request_id, disposition)` — reply / terminal / escalate.
   - Surface genuine **taste** to the human via `PushNotification`; answer everything
     non-taste yourself.

That is the whole launcher. Everything else — how to judge, what the dispositions mean,
watched vs un-watched — is `docs/DIRECTOR.md`.
