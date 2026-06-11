---
status: stable
last_verified: 2026-06-12
owner: review-reliability
---
# RELIABILITY.md

Grounding document for the review-reliability persona. Rules are numbered;
cite them in findings.

- **R1 — Idempotent imprinting.** Hooks can fire more than once for one event.
  Every memory write-back is deduped by key `session_id:event[:bucket]`
  (imprint_guard). pre_compact adds a 10-minute time bucket (multiple
  compactions per session are legitimate).
- **R2 — Feeder degrades, never blocks.** On timeout/error the SessionStart
  feeder falls back to a deterministic minimal pack (MEMORY.md +
  progress/current.md inline). A session must always start.
- **R3 — Single-flight imprint worker.** Lock file in state dir; stale locks
  (>1h) are broken. Concurrent claude -p storms are forbidden.
- **R4 — At-least-once queue.** Enqueue appends; worker dedupes via processed
  log. Crash between enqueue and process = retry next run, never loss → hence
  R1 must hold.
- **R5 — Transcripts are transient.** transcript_path may be gone by the time
  the worker runs; skip-and-mark, don't crash.
- **R6 — Hooks fail open.** A hook script exception must never break the
  user's session: catch, log to `.claude/harness/`, exit 0.
- **R7 — Mark-seen before enrich.** feeder_firstprompt marks the session seen
  before spawning enrichment, so a failed enrichment cannot retry-storm on
  every subsequent prompt.
