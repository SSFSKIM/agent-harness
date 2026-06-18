---
status: stable
last_verified: 2026-06-18
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
- **R14 — Read-API listeners fail soft, never to a dropped connection.** Any
  long-lived HTTP / read-API surface on `director/` (the observability dashboard
  is the first — `director/dashboard.py`) must isolate every request: a handler
  bug degrades to a structured error response (a `{"error":{code,message}}` 500
  the client already handles), and a peer that disconnects mid-write is a quiet
  drop — catch the FULL errno family (`BrokenPipeError` / `ConnectionResetError` /
  `ConnectionAbortedError` and any other `OSError` on the socket, not just the
  named two, including on the error-response's own write). An in-handler exception
  must NEVER reach `socketserver.handle_error`, which prints a traceback to stderr:
  a read-only instrument that noisily crashes its own request thread has become a
  gate on the very run it only meant to observe. This is R6's "hooks fail open"
  generalized to request threads — the boundary owns a catch-all, the listener
  stays up.
- **R15 — Config/host-policy loaders split fail-open vs fail-loud, before any side
  effect.** A loader for declarative config or host policy (`harness_lib.gate_config`,
  `worker.policy.load_worker_policy`, `director.config`) treats an **absent** file/block as
  **fail-open** (use defaults) and a **present-but-malformed** one as **fail-loud** (raise) —
  and the fail-loud raise MUST land at load time, *before* the first irreversible side effect
  (a board claim/transition, a worker spawn, a lock). A half-parsed policy must never widen
  access or silently run on partial settings; a wrong team/state must never claim the wrong
  tickets. (3-instance pattern; `director.config` raises before any worker spawns.)
- **R16 — Cross-thread coordination uses thread-safe primitives; cancellation is bounded
  and stale-safe.** Companion to R13 (single-writer). (1) Any object shared across threads
  (main ↔ worker pool) MUST be a thread-safe primitive (`threading.Event`/`Queue`) — never a
  plain dict/list reached into from a pool thread (the pool's `cancel_event` is the only
  cross-thread object; `futures`/`attempts`/`cancelled_states` are main-thread-only).
  (2) Cooperative cancellation of a long-running subprocess worker MUST bound observation
  latency (a poll interval) AND guarantee no stale signal cancels a *fresh* attempt
  (fresh Event per submit + drop-on-completion). (3) A worker outside the live tracking set
  (e.g. parked in a retry holding-map, not yet in `futures`) is human-cancel-blind until it
  re-enters — an accepted bounded staleness (board-as-truth converges), not a lost cancel.
- **R17 — Daemon-lifetime state is evicted on set-exit, not only on success.** Any map
  keyed by ticket id in a long-running loop (`run_forever`'s `attempts`, claim-backoff
  `claim_fails`/`claim_retry_at`, the bounded `recent[]`) MUST be evicted when the ticket
  **leaves the relevant set** — terminal, or moved/deleted off the board — not only on the
  success path. Popping only on success leaks for the daemon's lifetime when a ticket exits
  any other way; GC against `ready ∪ in_flight` each poll. (Bounds unbounded growth over a
  multi-week run; the batch wave is exempt — it returns and is reaped.)
- **R18 — Write-surface result fidelity.** An operator/human write surface (e.g.
  `director/dashboard.py`'s `POST /api/v1/answer`) that fans a request out to a downstream
  writer which can **refuse** (an idempotent no-op, a cap exceeded, an already-queued dedup —
  e.g. `requeue_merge` at `max_attempts`) MUST propagate that refusal to the caller (a
  non-2xx + reason), never return a generic success envelope for a no-op. Reporting a
  declined write as written leaves the operator believing they acted when the request is
  still open — the write analog of R12/R14's "never a wrong value / never a false gate".
