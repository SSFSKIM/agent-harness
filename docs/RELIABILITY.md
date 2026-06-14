---
status: stable
last_verified: 2026-06-14
owner: review-reliability
---
# RELIABILITY.md

Grounding document for the review-reliability persona. Rules are numbered;
cite them in findings.

- **R1 — Idempotent memory writes.** A dream run is re-runnable without
  duplication: Phase-1 outputs are PK-upserted per session in sqlite
  (`stage1_outputs`), and the Phase-2 router dedupes each routed claim (sqlite
  provenance + a content check) so re-routing is a no-op — never a duplicate
  tracker row, design-doc Decision-log line, or index entry.
- **R2 — Dreaming degrades, never blocks.** The `dream-rollouts` pipeline is
  best-effort and out-of-band (manual, not a session hook): a model timeout/error
  records a `failed`/`skipped` status and writes nothing; the forgetting pass
  degrades to a recorded error. It can never wedge or crash a session — the read
  path is on-demand pull, so there is no SessionStart feeder to fail.
- **R3 — Single-flight dreaming.** `dream_run` holds a process lock (`dream.lock`,
  stale-reclaimed) and Phase 2 additionally holds a global DB lock (`claim_phase2`)
  + a 6h cooldown, so at most one dream runs at a time — concurrent `claude -p`
  storms are forbidden; a rare lock race is short-circuited by the authoritative
  DB lock.
- **R4 — At-least-once extraction.** Rollouts are discovered + claimed (sqlite)
  before extraction; a crash between claim and store leaves the rollout
  re-claimable next run (lease expiry), so work is retried, never lost → hence
  R1 (idempotent writes) must hold.
- **R5 — Transcripts are transient.** transcript_path may be gone by the time
  Phase-1 extraction runs; skip-and-mark, don't crash.
- **R6 — Hooks fail open.** A hook script exception must never break the
  user's session: catch, log to `.claude/harness/`, exit 0.
- **R7 — Claim before extract.** `dream_discover.claim_rollouts` marks a rollout
  claimed (sqlite) before Phase-1 spawns extraction, so a failed or slow
  extraction cannot retry-storm — the claim/lease gates the next attempt (the
  mark-before-act principle generalized in R9).
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
  sentinel (no-op unless `docs/design-docs/agent-harness.md` exists — a plugin
  loaded into a non-harness repo must not judge it; repointed from the retired
  `docs/memory/MEMORY.md` by the memory-as-docs pivot). Only lint FAILs block; the
  hook's own tooling crashes (child timeout/traceback) are logged and never
  block (R6). Runs only the deterministic lint subset with per-child
  timeouts that fit inside the hook's own budget. Untracked files are
  fingerprinted by name only (can under-block, never over-block). Two
  concurrent sessions in one repo may each block once for the same state
  (last-writer wins) — accepted.
