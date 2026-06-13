---
status: draft
last_verified: {{TODAY}}
owner: review-reliability
---
# RELIABILITY.md

Grounding document for the review-reliability persona. Rules are numbered;
cite relevant ones in findings. This is a **seed** — grow it: every reliability lesson
this repo learns becomes the next numbered rule (feedback twice → promote).

- **R1 — Hooks fail open.** Harness hooks must never block a session or lose
  work on their own failure; they degrade, log, and let the session proceed.
- **R2 — Memory writes are idempotent.** Imprint write-backs are deduped by
  session/event key; re-running a write-back must not duplicate pages or
  index entries.
- **R3 — Fresh-session recoverability.** Any in-flight work must be resumable
  by a fresh session from `docs/memory/` + `docs/exec-plans/` alone — if it
  is not, the write-back was insufficient.
