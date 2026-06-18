---
status: completed
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
- [x] (2026-06-19) plan created; base_commit 0fefede; review_level standard
  (arch for the new module placement + orchestrator hook; reliability for the best-effort
  write + tolerant read + the new read route's R14 fail-soft). No write/exec surface → no
  security persona (history is a read store + a read route).
- [x] (2026-06-19) **M1 done** — store + producer. New `director/history.py` (stdlib-only,
  explicit `base=`): `summarize(snapshot)` (pure — exact run aggregate + outcomes counted from
  `recent`, tolerant of None/garbage), `append_run(record, base)` (append-only JSONL,
  best-effort — never raises, mirrors `_flush`), `read_history(base, limit)` (tolerant — skip
  torn line, missing → `[]`), `RECENT_RUNS_MAX=50`, `python3 -m director.history` read surface.
  `director/orchestrator.py`: `_record_run_history(status, history_base)` (guarded to a real
  StatusWriter) called after `status.finished(...)` in BOTH `run_until_drained` and
  `run_forever`; optional `history_base=None` threaded into both. 10 new tests (8 history:
  summarize map/tolerant, append+read roundtrip, limit-tail, missing→[], torn-line skip,
  bad-base no-raise; 2 orchestrator hook: run_until_drained over the mock appends 1 record
  with exact codex_totals/outcomes, Noop run writes nothing). Full gate GREEN (501 tests).

- [x] (2026-06-19) **M2 done** — dashboard route + panel. `director/dashboard.py`:
  `from director import history`; `_HISTORY_PATH` added to `_ROUTES`/`_route` →
  `_send(read_history(history_dir))`; `_DashboardServer` carries `history_dir`; `serve()` +
  `main()` (`--history-dir`) thread it. `PAGE`: a `<h2>history (recent runs)</h2>` section +
  `fmtRun`/`renderHistory` (newest-first: when · tokens · runtime · ✓/✗ outcomes · stopped-reason)
  + `loadHistory()` on a slow 10s interval (history changes only at run end — independent of
  the SSE/poll). 4 tests (history route empty→[], route returns seeded records oldest-first,
  PAGE wires the panel). `GET /` read rendering preserved (+ the history panel/JS — R8 requires
  it); `/api/v1/state` + `/api/v1/stream` bodies byte-unchanged. Full gate GREEN (504 tests).

- [x] (2026-06-19) **M3 done** — behavioral E2E + docs. `docs/DIRECTOR.md` §10: history-panel
  description + `--history-dir`/`$DIRECTOR_HISTORY_DIR`. **Behavioral check (web → playwright),
  PASS:** seeded a current run (status: in-flight `NOW-1` accrued 500 tok) + two completed-run
  records (history); served the dashboard with `--history-dir`; `GET /api/v1/history` returned
  2 records (`[3000, 4000]` totals), and the browser **history panel** rendered both newest-first:
  `2026-06-19 09:30:00 · 4000 tok · 1080s · ✗1 ✓5 · stuck` and `… 08:00:00 · 3000 tok · 540s · ✓4
  · drained`, while the **live view coexisted** (run header `pass #3 · 500 tok`, in-flight
  `NOW-1 · 500 tok`). Empty store → empty panel (asserted). Full gate GREEN (504 tests).

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
Four reviews (Claude personas). All **SATISFIED**, zero P1s. One doc-wording P2 fixed; one
genuine P2 + several proposed rules recorded fix-forward.
- **spec-compliance (SATISFIED):** R7/R8 traced to code; scope clean (multi-run aggregate absent;
  R1–R6 untouched but-additive; `status.py` not in the diff). P2: plan M2 "GET / byte-unchanged"
  wording imprecise (the panel changes the page) → **FIXED**. Proposed (→tech-debt): pin
  `ended_at` source (`= snapshot.updated_at`) + the route's N in a future spec rev.
- **review-arch (SATISFIED):** clean separate module (one-job), correct minimal hook, append-only
  JSONL the right shape. **P2 → tech-debt:** producer/consumer history-dir asymmetry — the
  dashboard grew `--history-dir` but `orchestrator.main()` doesn't thread `history_base` and there's
  no `paths.history_dir` config, so the two converge only via the shared default or
  `$DIRECTOR_HISTORY_DIR` (the common same-repo case works). Deferred: the full symmetric fix
  touches `config.DEFAULTS["paths"]` + orchestrator main (a different subsystem). Proposed rule
  (→tech-debt): a new operator-redirectable state dir must be reachable by the same precedence on
  EVERY process that reads/writes it.
- **review-reliability (SATISFIED):** R12/R14/D-6 hold end-to-end (append_run swallows; the hook
  can't raise — snapshot/summarize are total; read_history tolerant; the route fail-soft). Note:
  concurrent appends are interleave-safe only because records are tiny (~580 B < the O_APPEND
  atomic bound) — recorded so a future record-shape growth is a conscious call. Unbounded growth =
  accepted non-goal (bounded read; one line/run).
- **review-code-quality (SATISFIED):** clean decomposition + naming + load-bearing comments; the
  hook test is a genuine end-to-end control (real run → read-back). P2s non-actionable: the
  `_root`/tolerant-read mirror of `status.py` is deliberate (different on-disk shapes; folding
  into status.py was rejected) — extract a shared `_dir_root` only if a THIRD store appears; the
  `run_forever` hook is graceful-shutdown-only by design.

## Outcomes & retrospective
**Shipped:** cross-run history — completed runs survive their own lifetime. New append-only
`director/history.py` (`summarize` pure · `append_run` best-effort · `read_history` tolerant ·
a read CLI) persists a compact run-summary at each run's completion (the orchestrator hooks it
after `status.finished` in both `run_until_drained` and `run_forever`, guarded to a real
StatusWriter); the dashboard reads it via `GET /api/v1/history` and renders a **history panel**
(per-run when · tokens · runtime · ✓/✗ · stopped-reason) on a slow independent poll.
**Goal met:** behaviorally proven in-browser — `GET /api/v1/history` served 2 records and the
panel rendered both runs newest-first while the live view coexisted; empty store → empty panel.
Gate GREEN (504 tests). `app_server`/`queue`/`decider` untouched; `status.py` untouched (the hook
reads its snapshot).
**Retrospective:**
- A clean separate module was the right call (the rejected alternative — folding into `status.py`
  — would have coupled the single-atomic-snapshot producer to a cross-run append store with a
  different on-disk shape). The `_root`/tolerant-read idiom mirrors `status.py` so it reads like
  the surrounding code; reviewers flagged the duplication as deliberate, not a DRY violation.
- The exact-vs-approximate split is the honest design: the headline trend metrics (`codex_totals`,
  runtime) are exact from the run aggregate; outcome COUNTS derive from the bounded `recent` tail
  (under-counting only past 20 tickets), disclosed in code + docs + the plan.
- The one real seam to revisit is the producer/consumer history-dir symmetry (recorded) — today
  the default + `$DIRECTOR_HISTORY_DIR` keep the orchestrator's write and the dashboard's read
  aligned, but the dashboard's `--history-dir` flag has no orchestrator twin; the full fix belongs
  with the `.harness.json` `paths` config, a separate slice.
