---
status: draft
last_verified: {{TODAY}}
owner: review-reliability
type: methodology
description: The numbered reliability rules that ground the review-reliability persona.
---
# RELIABILITY.md

Grounding document for the review-reliability persona. Rules are numbered;
cite relevant ones in findings. This is a **seed** — grow it: every reliability lesson
this repo learns becomes the next numbered rule (feedback twice → promote).

- **R1 — Hooks fail open.** Harness hooks must never block a session or lose
  work on their own failure; they degrade, log, and let the session proceed.
- **R2 — Fresh-session recoverability.** Any in-flight work must be resumable
  by a fresh session from `docs/` (decisions in `docs/adr/`, deferred work in
  `docs/exec-plans/tech-debt-tracker.md`, living plans in `docs/exec-plans/`)
  plus Claude Code's native memory — if it is not, the durable knowledge was
  insufficiently recorded.
