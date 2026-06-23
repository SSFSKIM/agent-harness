---
status: stable
last_verified: 2026-06-20
owner: review-reliability
type: methodology
tags: [reliability, idempotency, review-reliability]
description: The numbered reliability rules that ground the review-reliability persona, covering concerns such as idempotent memory imprinting.
---
# RELIABILITY.md

Grounding document for the review-reliability persona. Rules are numbered;
cite them in findings.

> **Status — the memory-loop rules are historical (loop retired, packaging
> Slice 1).** **R1–R5** and **R7** (idempotent imprinting, feeder degradation,
> single-flight imprint worker, at-least-once imprint queue, transient
> transcripts, mark-seen-before-enrich) describe the **retired** feeder/imprint/
> dream memory loop (`docs/logs.md`). They are kept verbatim — and deliberately
> **not renumbered** — because the live rules R8–R22 (and ~15 tech-debt rows,
> code comments, and tests) cite this numbering, and several live rules
> *generalize* the loop's contracts (R8 per-entry isolation, R9 atomic append,
> R10 lock-liveness). **R8–R22 and R11 (stop-tidy) remain in force** — they
> govern the live runtime: the commit gate, `tidy_stop`, and `director/`. Read
> R1–R5/R7 as lineage, the rest as current.

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
  sentinel (no-op unless `.harness.json` exists — a plugin loaded
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
- **R19 — Durable handoff precedes the consume-enabling transition; restart GC trusts it,
  not just board state.** A generalization of [[queue-act-before-consume-ordering]] to
  restart-time cleanup. When finishing a unit of work writes BOTH a board-terminal state
  AND a durable downstream handoff (e.g. `reconcile` marking a ticket `done` AND enqueuing
  its PR to the serialized merger), the **handoff enqueue MUST happen before the terminal
  board write** — so a crash in between leaves the ticket pre-terminal (recoverable via
  orphan re-attach) rather than terminal-without-handoff. Correspondingly, any restart-time
  GC keyed on board-terminal state (`_startup_recovery`'s workspace cleanup) MUST treat
  "terminal on board" as **insufficient** evidence that a resource is disposable when a
  separate durable queue owns the remaining work: it excludes anything still referenced by
  that queue (the pending-`mergeRequest` workspace set). Deleting a workspace whose un-landed
  PR branch it holds is unrecoverable — the ordering + the exclusion together close it.
- **R20 — Control-path cursor loops must terminate.** A paginated fetch on a control path
  (`board/linear.py` `_paginate`, behind candidate-poll + startup recovery) must be bounded
  against a Byzantine/looping server: a `hasNextPage: true` with a missing/empty `endCursor`
  raises (`linear_missing_end_cursor`), AND a repeated/non-advancing cursor raises rather than
  looping forever. Per-request timeouts bound a single POST, not the loop; the loop itself must
  make progress or fail loud (the daemon's `poll_failed` catch then absorbs it). Distinct from
  R12 (telemetry totality) — this governs control-path *termination*, not parse safety.
- **R21 — Read-only corpus projections (`nav.py`) are total.** `nav.py` is a
  read-only navigator over the docs corpus; every query and projection
  (`build_index`, `relations`, `roadmap`, `tree`, `charter_map`, `followups`,
  `drift`, and the `_emit_*` renderers) must be a TOTAL function over a hostile
  corpus. Each of these degrades — skip the page, drop the edge, render empty —
  and the tool still emits a complete result for the rest and exits 0; none may
  raise: a malformed page or frontmatter value, an unresolvable link / `supersedes`
  target, a non-numeric phase `NN`, a supersession cycle, an empty result set, and
  a **transient I/O failure** (a file present at index time but gone/renamed/
  unreadable at a later re-read — e.g. `followups` re-reading the tracker; wrap the
  read, fall back to empty). Generalizes R12 (instrumentation totality) and R8
  (per-entry isolation) to the corpus-query surface — nav must never become a gate
  on the corpus it only observes. (Promoted from three tech-debt rows on the third
  recurrence: per-page/per-edge isolation, empty-set emit totality, and this I/O
  re-read gap.)
- **R22 — Every commit-gate lint step in `check.py` is total over a hostile corpus.**
  R21's sibling for the *write* gate — and strictly higher-stakes: a `check.py` lint
  step (`lint_docs`, `lint_structure`, `lint_base`, and any future step) runs on every
  commit, so a traceback here BLOCKS the commit (not just a dropped read). Every
  per-page / per-file check must degrade to a clean FAIL or a skip and never raise.
  In `lint_docs` (D3/D4/D11/D12 in `check_frontmatter`, and the rest): a frontmatter
  value authored as a list where a scalar is expected (`type`/`description`/`phase`/
  `resource` → guard with `isinstance(v, str)` so it FAILs cleanly, never throws), a
  non-str element in a list-valued key, a missing/odd path (resolve via the total
  `Path.exists()` pattern), and pathological regex input (no catastrophic backtracking)
  all produce a deterministic FAIL/skip. `lint_base`'s tolerant `_read` holds the same
  contract (a missing/non-UTF8 base template → a coded `B2`/`B6` FAIL, never a
  traceback). A new gate step inherits the totality rule by being a `check.py` step,
  not by re-deriving it. Third instance of the pattern (D4 list-degradation → D11
  `isinstance` guards → D12 path/grammar totality, now generalized across all gate
  lints); generalizes R12/R8 to the gate surface.
- **R23 — Worker-runtime SDK programmatic hooks fail open, never breaking a turn.**
  A `cc-harness` hook (`worker-runtime/harness/src/hooks/` builders, or anything wired into the
  SDK `options.hooks`) runs *inside* the agent's turn — an exception out of it aborts that turn.
  So a hook that does real work (reads control-plane state, decides an injection) must own a
  catch-all that degrades to a no-op `{}`. The context-budget push (`context/budgetHook.ts`) is
  the live instance: `getContextUsage()` can reject, so the `UserPromptSubmit` injector wraps its
  whole body in `try/catch → {}` (and treats a not-yet-bound query the same), proven by its
  "holder throws → {}" unit test; advisory-only by design, so failing silent loses a nudge, never
  a turn. The `observe` builder already bakes this in (swallow → `{}`); a hand-written hook adds it
  explicitly. R6's "hooks fail open" carried into the worker runtime (cf. R14 for request threads)
  — the turn boundary owns the catch, the worker keeps working.
