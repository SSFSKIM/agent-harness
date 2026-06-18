---
status: active
last_verified: 2026-06-19
owner: harness
base_commit: 0fefede
review_level: standard
---
# Cross-run history persistence — runs remembered across runs (Phase B)

## Goal
Completed runs survive past their own lifetime, so the dashboard can show **trends
across runs** instead of only the current one. Observable definition of done: after
two runs complete, a new append-only store holds two run-summary records (each with
the run's token totals, duration, stopped-reason, and outcome counts), a tolerant
reader returns the last N, `GET /api/v1/history` serves them as JSON, and the
dashboard renders a compact **history panel** listing the recent runs with their
metrics. A torn/absent store reads as empty and the rest of the page is unaffected.

This is the v1 **Phase B** slice (spec R7–R8). v1 (Layer-2 R1–R3 + SSE/rate-limit
R4–R6) is DONE (two completed plans). Multi-run aggregate view stays deferred.

## Context
- **Product-spec (owns the design — do NOT re-derive):**
  `docs/product-specs/2026-06-18-observability-polish.md` (R7–R8 + Design §D + D-5/D-6).
  This plan owns build order + milestones only.
- **Grounding rules:** **RELIABILITY R12** (instrumentation extractors/readers are
  total — `read_history` never raises); the history write is **best-effort**, the
  same "never a gate" posture as `StatusWriter._flush` (D-6); the `director/`
  invariants (stdlib-only · explicit `base=` · a new read route is loopback/fixed-route,
  fail-soft per R14).
- **Producer contracts this build extends (verified at base_commit 0fefede):**
  - `director/status.py` — `StatusWriter.snapshot()` returns the final
    `{run:{started_at,pass,stopped_reason,codex_totals,rate_limits},in_flight,recent,
    stuck,updated_at}`; `read_status`; `NoopStatusWriter` (snapshot → None).
  - `director/orchestrator.py` — `run_until_drained` (calls `status.finished(reason)`
    at the end, has `results` = all terminal summaries) and `run_forever` (calls
    `state.status.finished("shutdown")` at graceful shutdown). Both hold the
    StatusWriter — the run-completion hook point.
  - `director/dashboard.py` — `_ROUTES`/`_route`/`_send`/`_error`/`PAGE`/
    `_DashboardServer(status_dir,queue_dir,token,serving)`/`serve`; the read routes
    (`_STATE_PATH`, `_STREAM_PATH`) this mirrors.

## Approach (self-generated alternatives)
- **A — a new `director/history.py` (append-only JSONL), written by the orchestrator
  at run completion; a new `GET /api/v1/history` + panel reads it** (the spec's design,
  §D / D-6). `summarize(snapshot)` (pure) → `append_run(record)` (best-effort append) →
  `read_history(limit)` (tolerant). The orchestrator hooks it after `status.finished`.
- **B — fold history into `status.py`** (the StatusWriter appends a record on
  `finished()`). Rejected: couples the single-snapshot producer to a cross-run store and
  fattens status.py; a separate module keeps each responsibility clean (the `director/`
  one-module-one-job grain).
- **C — derive history from the persisted `status.json`** (no new store; the reader
  walks old snapshots). Rejected: status.json is a single atomic CURRENT snapshot
  (overwritten each run) — there is no history to walk; a durable append store is the
  point.
- **Chosen: A.** Append-only JSONL is the right shape for a metrics log (a torn final
  line is tolerated on read; no atomic-snapshot machinery needed); a separate module is
  stdlib-only, explicit-`base=`, and independently testable.

## Assumptions & open questions (self-interrogation)
- **Assumption:** the run aggregate (`codex_totals`, `seconds_running`, `stopped_reason`,
  `passes`, `started_at`) on the final snapshot is exact (verified — the StatusWriter
  maintains it), so the headline trend metrics are exact. Outcome COUNTS are derived from
  the bounded `recent` tail (RECENT_MAX=20), so for a >20-ticket run the per-status counts
  under-count — acceptable for a metrics log (the cost/duration headline is exact);
  recorded as a known limitation.
- **Assumption:** a history-write failure must never sink a run — `append_run` is
  best-effort (swallows, like `_flush`), so the orchestrator hook is a pure side-channel.
- **Open:** daemon run identity → resolved per spec (a `run_forever` lifetime = one record
  at shutdown; finer cuts are the spec's Open Question, deferred).
- **Open:** history-store growth → resolved per spec: read only the tail (`limit`);
  rotation is a non-goal (a record is tiny). Recorded.
- **Open:** only write history when visibility is ON (a real StatusWriter, not Noop) →
  resolved YES: a Noop run has no snapshot to summarize and history is itself observability.
  Guard the hook on `isinstance(status, StatusWriter)`.

## Milestones

- **M1 — `director/history.py` + orchestrator run-end hook (store + producer, headless).**
  New `director/history.py`: `_root(base)` (explicit → `$DIRECTOR_HISTORY_DIR` →
  `.claude/harness/director-history`); pure `summarize(snapshot, *, ended_at=None) -> dict`
  (run-level fields + `outcomes` counted from `recent` by status + `ticket_count`);
  `append_run(record, base=None)` (append one JSON line to `runs.jsonl`, best-effort —
  never raises); `read_history(base=None, limit=RECENT_RUNS_MAX) -> list[dict]` (tolerant —
  skip a torn line, missing → `[]`, last `limit`). `director/orchestrator.py`: after
  `status.finished(...)` in BOTH `run_until_drained` and `run_forever`, append a record
  (`history.append_run(history.summarize(status.snapshot()), base=history_base)`) guarded to
  a real StatusWriter; thread an optional `history_base=None` into both run fns for tests.
  At the end: completed runs are persisted; pure/tolerant, fully unit-testable.
  Run: `python3 -m unittest discover -s tests -p 'test_director_history.py'`
  (+ `test_director_orchestrator.py` for the hook).
  Expect (new tests): `summarize` maps a snapshot → the record shape (exact codex_totals,
  outcomes counted by status); `append_run`+`read_history` roundtrip two records; a torn
  final line / missing file → tolerant (`[]`, no raise); a bad base in `append_run` does not
  raise; a `run_until_drained` over the mock with a real StatusWriter + a temp `history_base`
  leaves exactly one record; the Noop path writes nothing.

- **M2 — Dashboard `GET /api/v1/history` + history panel (consumer).** `director/dashboard.py`:
  add `_HISTORY_PATH = "/api/v1/history"` to `_ROUTES`(`{GET}`)/`_route` → `_send(read_history(
  history_dir))`; `_DashboardServer` carries `history_dir` (+ `serve`/`main` `--history-dir`,
  default the history root). `PAGE`: a `<h2>history</h2>` section + `renderHistory(runs)`
  (a compact per-run row: short started-at · total tokens · runtime · outcome counts like
  "✓3 ✗1"), fetched by a `loadHistory()` on load + a slow interval (history changes only at
  run end — independent of the SSE/poll). Values via `textContent`. `GET /` + `/api/v1/state`
  + `/api/v1/stream` byte-unchanged.
  At the end: the dashboard shows cross-run trends.
  Run: `python3 -m unittest discover -s tests -p 'test_director_dashboard.py'`.
  Expect: a `GET /api/v1/history` integration test returns the seeded records; no store →
  `[]` + the page shows "no history" (PAGE wires `renderHistory`/`loadHistory`); the other
  routes' bodies unchanged.

- **M3 — Behavioral E2E + gate + docs.** Run two real `--mock` runs (or seed two records),
  serve the dashboard, drive `/playwright-cli`: the history panel lists both runs with their
  token/duration/outcome metrics; with no store it shows "no history" and the live view is
  unaffected. Add a `docs/DIRECTOR.md` §10 line for the history panel + the `$DIRECTOR_HISTORY_DIR`
  env. Capture output into the plan.
  Run: `python3 plugin/scripts/check.py` (GREEN) + the playwright drive.
  Expect: GREEN gate; the panel lists the runs; empty-store degrades cleanly.

## Progress log
- [ ] (2026-06-19) plan created; base_commit 0fefede; review_level standard
  (arch for the new module placement + orchestrator hook; reliability for the best-effort
  write + tolerant read + the new read route's R14 fail-soft). No write/exec surface → no
  security persona (history is a read store + a read route).

## Surprises & discoveries

## Decision log
- 2026-06-19: review_level **standard** (arch + reliability). Additive, no threading, no
  write-fence — but it adds a new `director/` module + an orchestrator run-end hook (arch) and
  a best-effort store + tolerant reader + a new long-poll-free read route (reliability R12/R14).
- 2026-06-19: history is append-only JSONL in a NEW `director/history.py`, written by the
  orchestrator at run completion (spec D-6) — a metrics log, not an atomic snapshot, so append
  (not temp+replace); a separate module keeps `status.py`'s single-snapshot job intact.
- 2026-06-19: outcome counts derive from the bounded `recent` (exact codex_totals; approximate
  counts for >20-ticket runs) — YAGNI; the headline trend metric (cost/duration) is exact.

## Feedback (from completion gate)

## Outcomes & retrospective
