---
status: stable
last_verified: 2026-06-16
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
  fingerprint that was already checked never blocks again (atomic
  `os.replace` write — a torn fingerprint must not re-block), so a session
  can always end even when the tree cannot be made green. Scope guards:
  harness-spawned headless recursion (HARNESS_HEADLESS) and an activation
  sentinel (no-op unless `docs/memory/MEMORY.md` exists — a plugin loaded
  into a non-harness repo must not judge it). Only lint FAILs block; the
  hook's own tooling crashes (child timeout/traceback) are logged and never
  block (R6). Runs only the deterministic lint subset with per-child
  timeouts that fit inside the hook's own budget. Untracked files are
  fingerprinted by name only (can under-block, never over-block). Two
  concurrent sessions in one repo may each block once for the same state
  (last-writer wins) — accepted.
- **R12 — Telemetry/instrumentation extractors are total.** Any function that
  parses an external or transient payload purely for observation (token usage,
  rate limits, status/snapshot fields) must be a TOTAL function: return
  `None`/`0`/empty on missing, wrong-shaped, or malformed input — never raise,
  never block the primary path. Instrumentation is read-only observation, never
  a gate: a producer whose real shape differs from the spec, or a torn read,
  must degrade to "absent telemetry", not a crash and not a wrong value. Prefer
  failing to *absent* over guessing, so an unverified boundary ships safe (the
  fix is then one localized extractor change, with nothing downstream corrupted).
  Canonical instances: `director/worker/app_server.py` `extract_usage` /
  `extract_rate_limits`, `director/status.py` `read_status`,
  `director/dashboard.py` `build_view` / `_read_pending`; mirrors the
  `agent_message_text` idiom.
- **R13 — Status/snapshot writers are lock-free single-writers.** The
  orchestration `StatusWriter` (`director/status.py`) accumulates state on the
  orchestrator's MAIN thread ONLY — claim/reconcile callbacks execute in the
  `wait(FIRST_COMPLETED)` loop, not in worker-pool threads — so it deliberately
  holds no lock. Its in-memory model must NEVER be mutated from a worker/pool
  thread: a cross-thread write would race the snapshot flush and tear state, and
  adding a lock to "fix" that trades the simple single-writer invariant for a
  contention surface. Any live mid-turn accrual (the deferred Layer-2
  in-flight-token follow-up) that wants per-event updates must MARSHAL them to
  the main thread (e.g. drain at a turn/dispatch boundary), never reach into the
  writer from an `on_event` callback.
