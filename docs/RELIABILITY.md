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
- **R8 — Per-entry exception isolation in queue workers.** Any loop that
  processes queue entries must catch per-entry exceptions (including
  `subprocess.TimeoutExpired`, `OSError`, `KeyError`, `ValueError`) and
  continue to the next entry rather than aborting the drain. The dedupe mark
  must land regardless of whether the subprocess succeeded, was skipped, or
  failed — never let one entry poison the rest of the queue.
- **R9 — Atomic mark-before-act writes.** Any "mark-before-act" guard (R7
  extension) must use an O_APPEND atomic write (one line appended) rather
  than a read-modify-write cycle. Read-modify-write is safe only under a
  pre-existing exclusive lock; append is atomic for short writes on Linux/macOS.
- **R10 — Lock liveness refresh.** A lock-holding process that runs longer
  than the stale threshold must refresh the lock's mtime at least once per
  `stale_threshold / 2` interval (e.g. `os.utime(lock, None)` per drain loop
  iteration) to prevent a live worker being reaped as stale.
- **R11 — Stop-tidy blocks at most once per state.** The Stop tidy hook
  (`tidy_stop.py`) fingerprints the dirty tree (status+diff SHA256); a
  fingerprint that was already checked never blocks again, so a session can
  always end even when the tree cannot be made green. It runs only the
  deterministic lint subset (no unittest — latency), is headless-guarded
  (Stop fires in `-p` sessions), and fails open per R6. Two concurrent
  sessions in one repo may each block once for the same state (last-writer
  wins on the fingerprint file) — accepted.
