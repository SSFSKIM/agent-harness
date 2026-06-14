---
status: draft
last_verified: {{TODAY}}
owner: review-reliability
---
# RELIABILITY.md

Grounding document for the review-reliability persona. Rules are numbered;
cite them in findings. This is a **seed** — grow it: every reliability lesson
this repo learns becomes the next numbered rule (feedback twice → promote).

- **R1 — Hooks fail open.** Harness hooks must never block a session or lose
  work on their own failure; they degrade, log, and let the session proceed.
- **R2 — Memory writes are idempotent.** The dreaming router dedupes routed
  claims (sqlite provenance + a content check); re-running a dream must not
  duplicate tracker rows, decision-log lines, or index entries.
- **R3 — Fresh-session recoverability.** Any in-flight work must be resumable
  by a fresh session from the docs tree alone (active `docs/exec-plans/`, the
  design-docs, the latest `docs/journal/`) — if it is not, the write-back was
  insufficient.
