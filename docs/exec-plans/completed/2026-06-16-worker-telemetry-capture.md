---
status: completed
last_verified: 2026-06-16
owner: harness
type: exec-plan
tags: [worker, telemetry, observability]
description: Captures per-ticket token usage, turn counts, and session ids plus run-level aggregate codex_totals and rate_limits from the codex stream and persists them additively into status.json as non-failing instrumentation.
base_commit: 5a833fb781ce40654e1988d53221a95454f55e3d
review_level: standard
---
# Worker telemetry capture (Symphony-grade) into status.json

## Goal
A human can run a multi-ticket orchestration (mock or real codex) and then read
`python3 -m director.status` to see, for each completed ticket, its token usage
(`tokens:{input,output,total}`), `turn_count`, and `session_id`; and for the run
as a whole, an aggregate `codex_totals` (input/output/total + live
`seconds_running`) plus the latest `rate_limits` payload. The data is captured at
turn/dispatch boundaries from the codex stream the worker already reads, persisted
**additively** into `status.json`, and is purely instrumentation: a missing or
malformed usage event never fails a turn, a dispatch, or the gate. Done = a
2-ticket mock run produces a `status.json` whose `recent[]` rows carry per-ticket
tokens and whose `run.codex_totals` equals the sum, with all 318 existing tests
still green.

## Context
- Product-spec (owns the design — build from it, don't re-derive):
  `docs/product-specs/2026-06-16-worker-telemetry-capture.md` (R1–R8, D-1–D-7).
- This plan is the **prerequisite** for the deferred renderer
  `docs/product-specs/2026-06-16-director-observability-dashboard.md` — that
  dashboard becomes the consumer of the data this plan produces.
- Symphony oracle (vendored, gitignored local reference):
  `docs/symphony-original/SPEC.md` §4.1.6 (Live Session: tokens, last_event,
  turn_count), §4.1.8 (codex_totals + rate_limits), §13.3 (snapshot rows), §13.5
  (token-accounting rules) — and `/tmp/symphony-research`.
- Code touched, with the exact seams (verified at base_commit):
  - `director/worker/app_server.py:230` `run_turn` reads every notification (the
    `on_event` path, line 262) and today extracts only `agentMessage`
    (`agent_message_text`, line 61, live-pinned to codex-cli 0.139.0). Usage
    notifications are seen and dropped. This is where extraction lands.
  - `director/run.py:123` `drive` runs the multi-turn loop on one thread and
    returns one disposition enriched with `{turns, turn_id, final_message,
    thread_id}`. This is where per-ticket accumulation lands.
  - `director/orchestrator.py:111` `reconcile`'s `summarize()` (line 144) builds
    the summary dict (already carries `turns` from the disposition) and
    `run_once` calls `status.terminal(ticket, outcome["summary"])` on the **main
    thread** (line 297). Workers run in a `ThreadPoolExecutor` (line 240), so
    `on_event` fires in a worker thread — mid-turn writes to the StatusWriter
    would cross threads. Hence boundary capture (spec D-2).
  - `director/status.py:68` `StatusWriter` is a **main-thread, lock-free single
    writer**; `recent[]` rows are built in `terminal()` (line 112); the snapshot
    is assembled in `snapshot()` (line 150). Additive fields only.
  - `director/worker/_mock_app_server.py` — the deterministic fake app-server;
    `complete_turn()` (line 28) and the per-scenario `turn/start` branch are
    where a usage notification gets emitted for tests.
- Gate command (`docs/design-docs/agent-harness.md`): `python3
  plugin/scripts/check.py` must be GREEN.

## Approach (self-generated alternatives)
- **A — boundary capture via `run_turn` return → `drive` accumulation →
  `reconcile` fold → `StatusWriter` persist.** `run_turn` extracts usage from the
  notifications it already reads and returns it; `drive` accumulates per-ticket
  and enriches the disposition; the main thread folds telemetry into the summary
  and the StatusWriter persists + aggregates. Tradeoff: a running ticket's tokens
  only appear when it terminates (no live mid-turn accrual) — accepted (spec D-2).
- **B — wire an `on_event` callback through `_prepare`/`drive` into a telemetry
  sink the orchestrator reads.** Gives live mid-turn accrual. Tradeoff: `on_event`
  fires in the worker thread, so the sink → StatusWriter path crosses threads and
  needs a lock or atomic per-ticket file, breaking status.py's deliberate
  lock-free single-writer invariant. This is the deferred Layer-2 design.
- **C — parse usage from worker logs/stderr post-hoc.** Tradeoff: brittle, and
  `app_server.py` sets `stderr=DEVNULL` (line 106) — no structured access. Reject.
- **Chosen: A** — captures the bulk of the value (per-ticket cost + run aggregate)
  while preserving the lock-free model; B's live accrual is the explicit Layer-2
  follow-up. (Mirrors spec D-2.)

## Assumptions & open questions (self-interrogation)
- Assumption: codex emits **absolute thread token totals** in a notification on
  the same stream `run_turn` reads (SPEC §13.5). If wrong (deltas only, or via a
  sync request), `extract_usage` returns None and telemetry is simply absent
  (R6 tolerance) — the M1 live-pin surfaces the true shape; nothing breaks.
- Assumption: the mock app-server can emit a usage notification matching the
  pinned shape (we own the mock — yes).
- Open: exact usage method/field names for codex-cli 0.139.0 → resolved
  autonomously: pin `extract_usage` to the SPEC §13.5 documented names
  (`thread/tokenUsage/updated`, events carrying `total_token_usage`; ignore
  `last_token_usage`) with lenient field matching, and confirm against real codex
  in M4 (like `agent_message_text` was pinned). Not a taste call.
- Open: does the `board/linear` ticket model carry a `url` for deep-links → resolved:
  verify in M3; if absent, persist `url` only when present and defer the field
  otherwise (R7) — never fabricate. Record in Decision log.
- Open: `rate_limits` payload shape → store the latest raw payload, no parsing
  (spec non-goal); presentation is a later concern.

## Milestones
- **M1 — `extract_usage` + `run_turn` returns usage/rate_limits (the wire-level
  capture).** Scope: add a pure, tolerant `extract_usage(method, params) ->
  {input,output,total}|None` to `director/worker/app_server.py` that recognizes
  absolute thread-total usage notifications (SPEC §13.5 names, lenient field
  matching), returns None for delta-style (`last_token_usage`)/unknown/missing
  payloads, and never raises; extend `run_turn` to track the latest usage +
  rate-limit payload seen during the turn and return them as `usage`/`rate_limits`
  (None when none seen). Extend `_mock_app_server.py` to emit a
  `thread/tokenUsage/updated`-shaped notification (a new `usage` scenario and/or
  inside `complete_turn`). At the end: usage extraction exists and is unit-tested,
  and a mock turn surfaces real numbers through `run_turn`. Run: `python3 -m
  unittest tests.test_director_app_server -v` (new cases). Expect: `extract_usage` maps an
  absolute-total payload → totals, a delta payload → None, missing → None, and
  variant field names → totals; `run_turn` against the mock `usage` scenario
  returns `usage={input,output,total}` and `None` against `plain`. A new test for
  each fails at base_commit and passes after.
- **M2 — `drive` per-ticket accumulation + disposition telemetry.** Scope: in
  `director/run.py` `drive`, accumulate across turns the latest absolute thread
  total (ticket total = latest absolute, NOT a sum — §13.5 anti-double-count),
  capture `session_id = f"{thread_id}-{turn_id}"`, `turn_count = turns`,
  `last_message = final_message`, and the latest `rate_limits`, and attach a
  `telemetry` block to the returned disposition (present on every kind —
  terminal/escalate/stuck/failed — via the shared `base`). At the end: a
  multi-turn drive returns telemetry. Run: `python3 -m unittest
  tests.test_director_drive -v` (new cases, mock emitting rising absolute totals across
  2 turns). Expect: `disp["telemetry"]["tokens"]` equals the LAST turn's absolute
  total (not the sum), `session_id` is `thr_mock_1-turn_mock_1`, `turn_count == 2`,
  `last_message == "done"`. Fails before, passes after.
- **M3 — orchestrator fold + `status.py` additive schema + run aggregate.** Scope:
  (a) `director/orchestrator.py` `reconcile` reads `disp.get("telemetry")` and
  includes it in the summary (alongside `turns` in `summarize`); (b)
  `director/status.py` `StatusWriter.terminal` records `tokens`/`session_id`/
  `last_message` on the `recent[]` row and accumulates run-level aggregate state
  (`_codex_totals` via token delta vs that ticket's last-reported absolute — clamp
  negatives to 0; latest `_rate_limits`; cumulative-ended seconds from the
  in_flight `started_at`); `snapshot()['run']` gains `codex_totals` with
  `seconds_running` computed live (ended + Σ active-elapsed over current in_flight,
  §13.5) and `rate_limits`; (c) conditionally persist `url` on `in_flight`/`recent`
  rows when the ticket carries one (verify `board/linear`; else defer per R7). All
  additive — `NoopStatusWriter`, `read_status`, `context_for` untouched in
  behavior. At the end: a 2-ticket mock orchestration writes telemetry into
  `status.json`. Run: `python3 -m unittest tests.test_director_status
  tests.test_director_orchestrator -v` (new cases). Expect: after a 2-ticket run, each
  `recent[]` row has `tokens`, `run.codex_totals.total` equals the sum across
  tickets, `run.codex_totals.seconds_running > 0`; a run with NO usage events
  yields a valid snapshot with absent/zero telemetry; re-feeding the same absolute
  total does not double-count. Fails before, passes after.
- **M4 — completion: full gate, backward-compat, R6 tolerance, live-pin.** Scope:
  run the whole gate; confirm the 318 pre-existing tests stay green (additive
  proof); add an R6 test that a malformed usage payload leaves the turn/dispatch
  intact (telemetry None, turn still `completed`); if real codex is available,
  live-pin the actual usage notification shape against codex-cli 0.139.0 and
  reconcile `extract_usage` to it (else record the live-pin as a tracked
  follow-up, since the tolerant extractor + mock already prove the mechanism). At
  the end: the capability is gate-green and proven end-to-end. Run: `python3
  plugin/scripts/check.py`. Expect: `check: GREEN — commit allowed.`; test count is
  318 + the new cases; the malformed-payload test passes.

## Progress log
- [x] (2026-06-16) Plan created from product-spec; base_commit recorded; gate green; committed (4d3515f).
- [x] (2026-06-16) M1 done — `extract_usage`/`extract_rate_limits` + `_pluck_tokens` in
  app_server.py (tolerant, §13.5 absolute-totals, delta-ignored, lenient field names);
  `run_turn` returns `usage`/`rate_limits`; `_mock_app_server.py` `usage` scenario emits
  rising cumulative totals; 7 new tests in test_director_app_server.py. Gate GREEN (326).
- [x] (2026-06-16) M2 done — `drive` accumulates latest-absolute tokens + rate_limits
  across turns and attaches a `telemetry` block (tokens/turn_count/session_id/
  last_message/rate_limits) to every disposition (terminal/escalate/stuck/failed). 2 new
  tests in test_director_drive.py (latest-absolute-not-sum: 200 over 2 turns, not 300;
  telemetry present without usage events). Gate GREEN (328).
- [x] (2026-06-16) M3 done — `reconcile` folds `disp.telemetry` into the summary;
  `StatusWriter.terminal` records tokens/session_id/last_message on the recent[] row and
  accumulates run aggregate (`_codex_totals` summed once per ticket; latest `_rate_limits`;
  `_seconds_ended`); `snapshot()['run']` gains `codex_totals` (live `seconds_running` =
  ended + Σ in_flight elapsed via tolerant `_elapsed`) + `rate_limits`. All additive.
  **R7 url deferred** — board/linear `_to_ticket` doesn't carry `url` (GraphQL doesn't request
  it); adding it is a separate board change. 3 status unit tests + 1 end-to-end orchestrator
  test (2-ticket `usage` run → status.json recent[].tokens + summed codex_totals). Gate GREEN (332).
- [x] (2026-06-16) M4 done — R6 tolerance test (mock `usage_bad` malformed event → turn
  completes, usage None); live-pin against real codex-cli 0.139.0 (rate_limits CONFIRMED via
  `account/rateLimits/updated`; token-event shape unobserved — account `usageLimitExceeded` —
  tracked follow-up, R6 validated against real codex); 333 pre-existing+new tests GREEN.
  Entering completion gate.

## Surprises & discoveries
- 2026-06-16 (M4 live-pin, real codex-cli 0.139.0): codex emits rate limits as
  `account/rateLimits/updated` with `params.rateLimits` (camelCase) — `extract_rate_limits`
  captured it end-to-end (probe `EXTRACTED_RATE` populated). **rate_limits live-pinned ✓.**
- 2026-06-16: the live turn hit `usageLimitExceeded` (account out of credits), so NO
  token-usage event fired and `EXTRACTED_USAGE` was null. This **validated R6 against real
  codex**: usage absent, rate_limits still captured, the turn did not crash, telemetry
  degraded to null cleanly. The exact token-usage event method/fields for codex-cli 0.139.0
  remain unobserved (couldn't run a token-consuming turn) → tracked follow-up; `extract_usage`
  stays pinned to the SPEC §13.5 documented shapes + lenient matching, proven via the mock.
- 2026-06-16 (POST-COMPLETION, credits restored): re-ran the live-pin and the token-event
  shape DIFFERED from the SPEC §13.5 documentation — codex-cli 0.139.0 NESTS the absolute
  totals under `params.tokenUsage.total` (`{totalTokens,inputTokens,outputTokens,
  cachedInputTokens,reasoningOutputTokens}`) next to a `last` per-turn delta, NOT the flat
  `total_token_usage` the SPEC shows. The shipped extractor returned None on real data.
  Reconciled: `_absolute_from_wrapper` descends to `.total` (never `.last`); the mock now
  emits the real nested shape; `test_real_codex_0139_nested_shape` pins the exact payload.
  Live-confirmed end-to-end — `run_turn` captured `{input:26399,output:40,total:26439}` on a
  real turn. **Token-usage now live-pinned ✓** (joining rate_limits). Vindicates the
  tolerant "None when the shape differs" stance (D-5/R6): the slice shipped safe — degrading
  to absent telemetry, not wrong telemetry or a crash — until the real shape could be observed.

## Decision log
- 2026-06-16: Chose boundary capture (Approach A) over on_event live-stream (B) —
  preserves status.py's lock-free single-writer; B is the deferred Layer-2 path
  (spec D-2).
- 2026-06-16: `extract_usage` pinned to SPEC §13.5 documented shapes + lenient
  matching, tolerant (None when absent) — same defensive pattern as
  `agent_message_text`; real-codex live-pin deferred to M4 since the pure function
  + mock prove the mechanism without it.
- 2026-06-16: `review_level: standard` (arch + reliability) — the data path +
  concurrency-boundary reasoning is the risk; the diff does not touch the
  security live-exec surface (hooks/ , .harness.json, .claude/lints/,
  docs/.harnessignore), so no security persona. Per CLAUDE.md, the completion-gate
  personas are run via `/codex:rescue --model gpt-5.5 --effort high`, falling back
  to the Claude `agent-harness:review-*` personas if codex is unavailable.

- 2026-06-16: R7 `url` deep-link DEFERRED — verified `director/board/linear.py`
  `_to_ticket` builds `{id,identifier,title,desc,prompt}` with no `url`, and the read
  GraphQL query doesn't request it. Persisting a deep-link needs a board/linear change
  (query `url` + carry it on the ticket); out of this slice's scope. The status schema is
  ready to carry it the moment the ticket does.

## Feedback (from completion gate)
Standard review = review-arch + review-reliability (Claude personas; codex skipped —
the M4 live-pin proved the codex account is `usageLimitExceeded`, the documented
codex-unavailable fallback). Both verdicts **SATISFIED, no P1**.
- review-arch P2 (status.py aggregate) — code sums where the spec worded it "delta vs
  last-reported"; equivalent in the boundary-capture model. **Fixed inline**: comment now
  explains the delta-collapses-to-absolute reasoning. Two proposed rule-additions noted
  below.
- review-reliability P2.2 (partial-payload fold) — a partial `tokens` dict could leave
  `codex_totals` internally inconsistent. **Fixed inline**: the {input,output,total} group
  now folds atomically (all-or-nothing) + regression test
  `test_partial_tokens_not_folded_into_aggregate`.
- review-reliability P2.1 (retry token under-count) — failed-then-retried attempts' tokens
  aren't folded (each `drive` starts fresh; `retry` skips `summarize`), so the aggregate is
  final-attempt cost, not total burn. Not a double-count, not a crash. **Documented inline**
  (status.py terminal comment) + **tracked** (tech-debt-tracker, accepted for this slice).
- Proposed rule-additions (both reviewers, for the host architecture doc, not built here):
  (1) host telemetry/instrumentation extractors must be total (None/0 on malformed input,
  never raise, never block the primary path); (2) the StatusWriter is a main-thread lock-free
  single writer — cross-thread mutation forbidden (steers the Layer-2 live-stream follow-up).
  Recorded as tracked doc-debt.

## Outcomes & retrospective
**Done.** `status.json` now carries Symphony-grade telemetry, captured at turn/dispatch
boundaries and persisted additively: per completed ticket `recent[].{tokens,session_id,
last_message}`, and a run-level `run.{codex_totals{input,output,total,seconds_running},
rate_limits}`. Verifiable via `python3 -m director.status` after any (mock or real) run.
Gate GREEN at 334 tests (318 baseline + 16 new); base_commit 5a833fb → HEAD.

What newly exists: `extract_usage`/`extract_rate_limits`/`_pluck_tokens` (tolerant,
§13.5-pinned) + `run_turn` usage/rate_limits return (M1); `drive` per-ticket accumulation
folded onto every disposition as a `telemetry` block (M2); `reconcile` fold + `StatusWriter`
additive schema with a lock-free run aggregate and a live `seconds_running` (M3); R6
malformed-event tolerance + a real-codex live-pin (M4). Blast radius held to the producer
path (app_server/run/orchestrator/status + mock) with status.py changes strictly additive.

Live-pin result: `rate_limits` confirmed against real codex-cli 0.139.0
(`account/rateLimits/updated`); the token-event method/fields stayed unobserved because the
account was `usageLimitExceeded` — which incidentally validated R6 (telemetry absent ≠
broken) against real codex. Token-event shape is a tracked follow-up.

Completion gate: review-arch + review-reliability both SATISFIED (no P1). Of 3 P2s, two were
fixed inline (delta-collapses comment; atomic partial-payload fold + test) and one
documented + tracked (final-attempt aggregate semantics). Two proposed host-architecture
rule-additions captured as doc-debt.

Retrospective: the boundary-capture decision (D-2) paid off exactly as designed — the
lock-free single-writer held, both reviewers confirmed no cross-thread path, and the
"telemetry never a gate" posture (total extractors, None/0 on bad input) was independently
flagged by both reviewers as a rule worth promoting. The producer-before-renderer pivot
proved its thesis immediately: the renderer slice (deferred) will now consume genuinely
rich data rather than rendering a thin snapshot. Follow-ups (all tracked, none blocking):
token-event live-pin on a credited account; final-attempt-vs-total retry accounting; the
two architecture-doc rules; and the deferred `url` deep-link (board/linear doesn't carry it
yet) and Layer-2 live in-flight accrual.
