---
status: active
last_verified: 2026-06-16
owner: harness
base_commit: f406da02b9d9633fcad000a3e4123de8b808d775
review_level: standard
---
# Activate the serialized merge pipeline (R4 end-to-end)

## Goal
Make the serialized PR-merge pipeline **run end-to-end**, not just exist. Today a worker
finishes done+PR but nothing enqueues a `mergeRequest`, and nothing calls `merger.drain` —
the pipeline is built (completed slice below) but inert. At done: (1) a worker that opened a
PR reports it, and the orchestrator **enqueues** a `mergeRequest`; (2) a **standalone merger
process** (`python3 -m director.merger`) drains the queue, landing PRs one at a time. Observable:
1. `report_outcome(done, pr_url=…, pr_branch=…)` flows the PR through to the disposition, and
   `orchestrator.reconcile` enqueues a `mergeRequest` for it (and does NOT for done-without-PR,
   blocked, or escalate).
2. `python3 -m director.merger --once` drains all pending `mergeRequest`s (serial, one PR at a
   time via the existing `merger.drain`) and exits; the event-loop mode keeps draining as new
   ones arrive, woken by the queue (no busy-spin).
3. An end-to-end test drives a terminal-done-with-PR disposition → reconcile enqueues → the
   merger drains → the PR is `merged` and the queue is empty.
4. `python3 plugin/scripts/check.py` GREEN.

## Context
- **Parent slice (done):** `docs/exec-plans/completed/2026-06-16-worker-qa-and-serialized-pr-merge.md`
  and its spec `docs/product-specs/2026-06-16-worker-qa-and-serialized-pr-merge.md` (R4/R8 + the
  "merger 상시/이벤트" Open Q). It built the merge MECHANISM: `mergeRequest`/`mergeReview` queue
  kinds + helpers (`director/queue/__init__.py`), the single-consumer `merger.drain`
  (`director/merger.py`, with a `flock` single-consumer guard), and the Director `mergeReview`
  surface (`director/director_min.py`, `docs/DIRECTOR.md` §7). This slice wires the two ends the
  parent explicitly deferred: the **worker→enqueue handoff** and the **drain-runner**.
- **On-model contract (D-40, multi-turn slice):** a worker *proposes* a terminal outcome via
  `report_outcome`; the orchestrator *executes* the board/queue side effects. So the PR travels
  on `report_outcome` (worker proposes), and `reconcile` does the enqueue (orchestrator executes)
  — the worker never writes the merge queue itself.
- **Reuse:** `director/queue.append_merge_request` (idempotent enqueue), `director/merger.drain`
  (serial drain + `_single_consumer_lock`), `director/watch.py` (`new_pending` dedup tail; already
  filters `--kinds mergeRequest`), `director/worker/tools.py` (`report_outcome_spec` / executor /
  sink), `director/orchestrator.py` (`reconcile`, `_dispatch_wave` — already threads `queue_base`
  + `workspace_root`).
- **Coordination:** the parallel secret-boundary session edits `director/run.py`/`app_server.py`/
  `policy.py`. This slice keeps `run.py` UNTOUCHED (the PR fields flow through the existing
  `sink.get("outcome")` pass-through; `reconcile` computes the workspace path inline rather than
  calling a run.py helper). It does touch `orchestrator.py::reconcile` (last touched by the
  secret-boundary commit `a6d8537`, currently clean) — commit only my paths, never `git add -A`.

## Approach (self-generated alternatives)
**Handoff — how the worker's PR reaches the enqueue:**
- A) **PR fields on `report_outcome`** (worker proposes) → `reconcile` enqueues (orchestrator
  executes). On-model (D-40), no new transport, the qa/push skill already opens the PR so it
  knows the branch/url. **Chosen.**
- B) Worker enqueues the `mergeRequest` itself via a new dynamic tool. Rejected: crosses the
  worker-proposes/orchestrator-executes boundary (D-40); a worker writing the Director's queue.
- C) Orchestrator discovers the PR from the workspace branch via `gh` after done. Rejected:
  fragile, couples the orchestrator to `gh`, and fails for the local-merge case.

**Drain-runner — who calls `merger.drain`:**
- A) **Standalone `python3 -m director.merger` process, event-woken** by tailing pending
  `mergeRequest`s (the `director.watch` dedup pattern) and calling `drain` when work appears.
  Preserves R7 (merger is a SEPARATE component from the Director); the `flock` guard already
  makes a standalone process safe; the Director still owns the human surface (handles
  `mergeReview` per §7). **Chosen** (human decision, this session).
- B) Director-owned: the watched Director loop also drains. Rejected: weakens the R7
  component separation; the Director's job is taste/turn-ends, not running merges.
- C) Orchestrator post-wave drain. Rejected: couples the orchestrator to merge mechanics.

## Assumptions & open questions (self-interrogation)
- **Assumption — the worker reliably knows its PR (branch + url) at done.** The qa/push skill
  opens the PR (`gh pr create`) before `report_outcome(done)`, so branch is always known and url
  is known after create. *If wrong* (PR open failed): the worker reports done WITHOUT pr fields →
  reconcile simply does not enqueue (the PR is surfaced by the worker's prose / a human notices) —
  no crash, no false merge.
- **Assumption — `reconcile` can derive the worker's workspace path inline** as
  `ticket.get("workspace") or <workspace_root>/<id>` (the same rule `run._workspace_for` uses),
  avoiding a `run.py` edit. *If wrong:* thread the path through the disposition instead.
- **Open — event-wake vs poll for the merger loop.** `director.watch` already polls the queue and
  emits per-kind; the merger loop will reuse that poll+dedup shape (a cheap sleep-poll calling
  `drain` when `pending_merges` is non-empty), NOT a busy-spin. Resolved autonomously: poll with a
  configurable interval + `--once` for tests; a push/inotify wake is a later optimization.
- **Open — enqueue idempotency on retry.** `append_merge_request` dedupes on `merge|<ticket>`, so
  a re-dispatched ticket that re-reports done won't double-enqueue. Acceptable (one PR per ticket);
  the re-enqueue-after-guidance loop stays the parent slice's deferred item.

## Milestones
- **M1 — Handoff: `report_outcome` carries the PR; `reconcile` enqueues.** Extend
  `director/worker/tools.py::report_outcome_spec` with optional `pr_url`/`pr_branch` and capture
  them in `make_report_outcome_executor` into the sink outcome (they ride the existing
  `sink.get("outcome")` pass-through to the disposition — `run.py` untouched). In
  `director/orchestrator.py::reconcile`, on a terminal `done` outcome that carries `pr_url`/
  `pr_branch`, call `dq.append_merge_request(ticket_id, pr=pr_url, branch=pr_branch,
  workspace_path=<inline ws>, base=queue_base)` — best-effort (an enqueue failure is recorded in
  the summary like a board-write failure, never raised). Thread `queue_base`+`workspace_root` from
  `_dispatch_wave` into `reconcile`. Update `director/workspace_skills/qa/SKILL.md` (+ the impl
  template if needed) to tell the worker to pass its PR to `report_outcome(done)`. At the end: a
  done-with-PR disposition enqueues exactly one `mergeRequest`; done-without-PR / blocked /
  escalate enqueue none. Run: `python3 -m unittest discover -s tests -p "test_director_orchestrator.py"`
  (+ new assertions). Expect: GREEN; a `mergeRequest` lands in the queue only on done-with-PR.
- **M2 — Standalone event-woken merger process.** Add `director/merger.py::main(argv)` →
  `python3 -m director.merger`: `--once` drains all currently-pending `mergeRequest`s via
  `drain` and exits (tests/cron); default loops — poll the queue (reuse the `director.watch`
  dedup shape) and call `drain` when `pending_merges` is non-empty, with `--poll` interval and
  `--queue-dir`/posture flags mirroring the orchestrator. The `flock` guard makes the standalone
  process the enforced single consumer (R4). At the end: `python3 -m director.merger --once`
  drains a seeded queue and exits 0; the loop drains newly-arriving requests without busy-spin.
  Run: `python3 -m unittest discover -s tests -p "test_director_merger.py"` (+ a `main --once`
  test with a mock driver). Expect: GREEN; seeded N requests → drained serially, queue empty.
- **M3 — End-to-end chain + completion gate.** One integration test exercising the whole chain
  with mocks (no real codex): a terminal-`done`-with-PR disposition → `reconcile` enqueues a
  `mergeRequest` → `merger.main(["--once", ...])` (mock land driver → terminal done) → the PR is
  `merged` and `pending_merges` is empty. At the end: R4 is mechanically end-to-end (worker
  proposes PR → orchestrator enqueues → merger lands), proven by one test that fails before M1/M2
  and passes after. Run: `python3 plugin/scripts/check.py`. Expect: GREEN; then the standard
  completion gate (review-arch + review-reliability via codex per CLAUDE.md). The full live
  `gh` PR roundtrip stays deferred (needs a remote — parent slice's note).

## Progress log
- [ ] M1 — handoff (report_outcome PR fields + reconcile enqueue) + tests.
- [ ] M2 — standalone event-woken `director.merger` process + tests.
- [ ] M3 — end-to-end chain test + completion gate.

## Surprises & discoveries

## Decision log
- 2026-06-16: PR travels on `report_outcome` (worker proposes), `reconcile` enqueues (orchestrator
  executes) — on-model D-40; no new transport, `run.py` untouched (parallel-session disjoint).
- 2026-06-16: drain-runner = standalone event-woken `director.merger` process (not Director-owned)
  — preserves R7 component separation; `flock` guard already makes it safe (human decision).

## Feedback (from completion gate)

## Outcomes & retrospective
