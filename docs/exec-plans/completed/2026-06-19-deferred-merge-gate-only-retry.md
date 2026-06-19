---
status: completed
last_verified: 2026-06-19
owner: claude (inline, Opus)
type: exec-plan
tags: [merger, pr-merge, retry, reliability]
description: Closes a merge-preservation limitation — a CI-pending PR the merger already PREPARED retries the code gate ONLY (preservation tripwire + hygiene gate + code-issued merge) on later cross-poll passes instead of re-driving the full LLM land lane, reusing the original pre-rebase intended diff so the tripwire is not blinded.
base_commit: 4c815d730de20883c0fb4da1b8c6185be77b5685
review_level: standard
---
# Deferred-merge gate-only retry (cross-poll prepared-state)

## Goal
A CI-pending PR that the merger has already PREPARED (driven through the land lane to a
prepared `done`) must NOT re-drive the full LLM land lane on every subsequent poll while
its CI runs. After the first preparation, a deferred PR's retry runs the **code gate only**
(preservation tripwire + hygiene gate + the code-issued merge), reusing the **original
pre-rebase intended diff** captured on the first pass. Observable definition of done: in a
two-pass drain over one CI-pending-then-green PR sharing the merger's cross-poll state, the
land-lane driver is invoked **exactly once**, the second pass merges via the gate alone, and
the finalize call on the second pass receives the *same* `intended` object captured before
the first rebase (so the tripwire is not blinded). With no cross-poll state (default /
`--once` / fresh process), behavior is byte-identical to today. Gate GREEN at every commit.

## Context
- Parent spec: [`docs/product-specs/2026-06-19-merge-preservation-hardening.md`](docs/product-specs/2026-06-19-merge-preservation-hardening.md) (R1 preservation
  tripwire, R3 hygiene gate, D1 code-owns-the-merge). This plan does NOT re-derive that design;
  it closes a known limitation in its implementation.
- Tracked limitation: `docs/exec-plans/tech-debt-tracker.md` row 94 (merge-preservation-hardening
  completion gate, review-arch P2): "defers a CI-pending PR correctly WITHIN a drain pass … but
  across `run_loop` polls … re-`drain`s → `process_request` re-captures the intended diff AND
  re-drives the FULL LLM land lane before the gate defers again." Fix sketch in the row:
  "cross-poll 'prepared' state (remember the request is prepared + its ORIGINAL pre-rebase
  intended diff) so a deferred PR's retry runs the code gate ONLY … the retry must reuse the
  ORIGINAL intended (re-capturing post-rebase would equal actual and blind the tripwire)."
- Code under change: `director/merger.py` (`process_request`, `drain`, `run_loop`, module +
  function docstrings). No queue-schema change (see Approach). No board write (merger stays
  board-free). The gh/git subprocess surface is UNCHANGED (still argv, worker-supplied `pr`).
- Relevant existing seams: `_finalize_merge` returns `result ∈ {merged, escalated, deferred}`
  (merger.py:254); `mp.files_from_pr` captures the PR's per-file change pre-rebase (the
  `intended`); the per-pass `deferred` set in `drain` already prevents head-of-line block
  within one pass (merger.py:382); `_single_consumer_lock` makes `run_loop` the enforced sole
  drainer (merger.py:167) — so an in-memory cache in `run_loop` is coherent (no second drainer
  could miss it).

## Approach (self-generated alternatives)
- **A — In-memory prepared-cache owned by `run_loop`.** A `{request_id: original_intended}` dict
  lives in the long-lived `run_loop` process, threaded `run_loop → drain → process_request`. On
  the first prepared+deferred result, store the original pre-rebase `intended`; on a later poll,
  if the request_id is cached, skip the land-lane drive and run `finalize` gate-only against the
  stored `intended`. Pop on terminal (merged/escalated/failed); GC entries no longer pending.
  Tradeoff: lost on a merger restart → the first post-restart poll re-drives once (re-prepares).
- **B — Persisted prepared-marker file** (`prepared/<request_id>.json` in the queue dir) written
  on defer, read on retry, deleted on consume. Tradeoff: survives restart, but adds a new
  persisted lifecycle (create/read/delete across merged/escalated/requeue/abandon) and a stale-
  marker correctness risk (an orphaned marker could feed a stale `intended` into a future
  finalize). More surface for a rare-race gain.
- **C — Mutate the pending request's payload in place** (literal "prepared-state in the queue
  payload"). Tradeoff: the queue is append-only (`requests.jsonl` + per-request answers);
  rewriting it in place would race concurrent `append_request` by workers (the merger holds the
  flock only during drain, not workers' appends) — a shared-log rewrite hazard. Rejected:
  compromises queue integrity.
- **Chosen: A.** The durable queue holds *facts* ("this merge request exists, unconsumed");
  whether the single consumer has already done the expensive prep *this process-lifetime* is a
  transient *cache*, and caches belong in the consumer's memory, not the durable log. A restart
  cold-starts the cache and re-prepares once — which is **exactly today's cross-poll behavior**
  (today every poll re-drives), so it is a strict improvement with no regression, minimal diff,
  and no new failure surface. (Mirrored in Decision log; the restart degradation is recorded,
  not hidden — persisting it (B) is a cheap follow-on if restart-frequency ever warrants it.)

## Assumptions & open questions (self-interrogation)
- Assumption: `run_loop` is the single long-lived drainer (enforced by `_single_consumer_lock`).
  If two mergers ran, the flock makes the second fail loud — so at most one holds the cache and
  the cache can never be "missed" by a concurrent drainer. Breaks only if the flock is removed.
- Assumption: reusing the **original** pre-rebase `intended` on retry is correct AND strengthens
  the tripwire. Today a deferred PR re-captures `intended` from `gh pr view` each poll — but the
  branch was already rebased+pushed on the first pass, so the re-captured "intended" is already
  post-rebase == actual → the tripwire is blinded across the defer boundary. Reusing the stored
  original keeps `intended` (pre-rebase) vs `actual` (current post-rebase) a meaningful
  comparison. So this is a **correctness fix**, not only an efficiency one. What breaks if wrong:
  nothing — if the original were somehow wrong, finalize fail-closes (escalate), the safe side.
- Open: persist across restart? → resolved autonomously to **no** (Approach A): the restart case
  degrades to today's behavior (no regression) and persistence (B) adds a marker lifecycle whose
  stale-marker risk outweighs the rare-race gain. Not a taste fork — a simplicity/safety call.
- Open: does `--once`/cron benefit? → resolved: no — a single-pass drain owns no cross-poll
  memory by definition; each cron invocation is a fresh process (== today). The daemon
  `run_loop` is the primary deployment and gets the full fix. Recorded, not silently dropped.
- Assumption: orphan growth is bounded. A cached entry whose request_id leaves `pending_merges`
  (Director abandoned / answered out-of-band) is GC'd at the top of each drain pass, so the cache
  is bounded by the count of concurrently-deferred PRs (tiny). Mirrors the tracker's unbounded-
  growth concern for the orchestrator's `claim_failed`.

## Milestones
- **M1 — cross-poll prepared-cache + gate-only retry path.** `process_request` gains
  `prepared: dict | None = None`: when `request_id in prepared`, skip `mp.files_from_pr` and the
  `driver(...)` drive entirely, run `finalize(req, intended=prepared[rid], ...)`, pop the entry
  on a non-deferred (terminal) result, and return a `{"kind": "prepared", "gate_only": True}`
  disposition; on the first-encounter path, after a prepared+deferred finalize, store
  `prepared[rid] = intended` (the original pre-rebase capture). `drain` gains `prepared=None`,
  threads it through, and GCs entries not in this pass's pending set. `run_loop` owns one dict
  across polls and passes the SAME dict each poll. With `prepared=None` (default), every path is
  byte-identical to today. At the end: a deferred PR's next poll runs the gate without a drive.
  Run `python3 plugin/scripts/check.py`; expect GREEN.
- **M2 — tests.** `tests/test_director_merger.py`: (1) two-pass drain, CI-pending→green, shared
  `prepared` dict → driver called once, second pass merged; (2) finalize on the second pass
  receives the *same* `intended` captured before the first drive (tripwire not blinded) — a
  finalize spy recording each `intended` asserts call-2 `intended is` call-1's pre-rebase value;
  (3) cleanup — after deferred→merged, `prepared` no longer holds the rid; (4) `preservation_
  override` deferred PR caches `None` and the gate-only retry passes `None` to finalize without
  error; (5) orphan GC — a cached rid that drops out of pending is pruned next drain; (6)
  backward-compat — `drain`/`process_request` with `prepared=None` re-drives (existing tests
  already assert this; add one explicit assertion). Run the gate; expect GREEN.
- **M3 — docs + tracker.** Refine `director/merger.py` module docstring + `drain`/`run_loop`/
  `process_request` docstrings to name the gate-only retry and the original-intended reuse. Flip
  `docs/exec-plans/tech-debt-tracker.md` row 94 → `fixed (…)` with the in-memory-cache rationale
  and the correctness-bonus note. DIRECTOR.md §7 unchanged (the retry is internal/operator-
  invisible — the PR still shows `merging`); record that as a scope decision. Run the gate; GREEN.

## Progress log
- [x] (2026-06-19) Plan created from tracker row 94 + parent spec; base_commit 4c815d7,
  review_level standard. Creation-time self-review: no placeholders; Approach↔Goal↔Milestones
  agree (in-memory cache, gate-only retry, original-intended reuse); single-subsystem (merger);
  each requirement reads one way. Confirmed the queue is append-only (rules out C) by reading
  `director/queue/__init__.py`. Gate GREEN at base (609). Commit 2ec194f.
- [x] (2026-06-19) M1+M2 — gate-only retry path in `process_request` (cache check → finalize on
  stored original → pop on terminal / plant on prepared+deferred), `drain` threads `prepared` +
  GCs orphans at entry, `run_loop` owns one dict. 5 tests (GateOnlyRetryTest). Gate GREEN (614).
  Commit be92601. (Folded M1+M2 into one commit — no commit lands new behavior untested.)
- [x] (2026-06-19) M3 — merger module docstring + `drain`/`run_loop`/`process_request` docstrings
  name the gate-only retry; tracker row 94 → fixed. DIRECTOR.md §7 unchanged (operator-invisible).
  Gate GREEN (614). Commit 97a37a0.
- [x] (2026-06-19) Completion gate — gate GREEN; behavioral check (below); self-review trimmed a
  speculative `_ci_sh` helper param set (commit d81cbcf). Reviews: spec-compliance (codex)
  SATISFIED, review-arch SATISFIED, review-reliability SATISFIED, code-quality (Claude fallback)
  SATISFIED. Fixed two cheap/high-value code-quality P2s inline with one real-gate test (615
  green). P2s + proposed doc-rules tracked.
- Behavioral check: no live GitHub PR in the gate env (same constraint as the parent slice), so
  behavior is proven by the mocked-gh/git unit tests — `test_deferred_then_green_runs_gate_only_
  without_redrive` (defer → gate-only retry → merge, driver called once) and
  `test_gate_only_retry_catches_a_drop_with_the_real_gate` (the real `_finalize_merge` tripwire
  trips on a gate-only retry) are the behavioral acceptance. Live PR QA: N/A (no GitHub PR
  fixture available in the gate environment).

## Surprises & discoveries
- The fix is also a CORRECTNESS fix, not only efficiency (anticipated in the plan, confirmed by
  review-reliability): pre-fix, each poll re-drove the land lane (re-rebase) AND re-captured
  `intended` post-rebase, so `intended == actual` and the preservation tripwire could never trip
  across a defer. Reusing the stored pre-rebase original restores a meaningful tripwire.
- Subtlety surfaced while writing the real-gate test: in the gate-only path the branch does NOT
  change between polls (no re-drive), so a drop is normally caught on pass 1 (escalate, never
  cached). The tripwire's value on the *retry* is for the rare case where the branch is mutated
  externally between polls — the stored original still catches it (the test simulates this).
- Codex spec-compliance ran but its shell stdout channel degraded mid-review; it then
  confabulated implementation detail (an imagined `PreparedMerge` dataclass + a `gate_only=True`
  finalize param — neither exists; the code uses a plain `{request_id: intended}` dict). Its
  SATISFIED verdict was sound only because review-arch + review-reliability independently verified
  the same properties against the real code with accurate cites. Reinforces the
  [[codex-review-companion-scoping]] flakiness pattern — corroborate a codex verdict, don't lean
  on its evidence.

## Decision log
- 2026-06-19: prepared-state lives **in `run_loop` memory**, not the queue (Approach A over B/C).
  Durable queue = facts; "already prepared this process-lifetime" = a transient cache. Append-only
  queue makes literal payload-mutation (C) a shared-log rewrite race; a persisted marker (B) adds
  a stale-marker correctness risk for a rare-restart gain. Restart degrades to today's behavior.
- 2026-06-19: the fix also closes a latent **correctness** gap — today's per-poll re-capture of
  `intended` reads the already-rebased branch (== actual), blinding the tripwire across a defer;
  reusing the stored original pre-rebase `intended` keeps the comparison meaningful.
- 2026-06-19: DIRECTOR.md §7 not changed — the gate-only retry is operator-invisible (deferred PR
  still surfaces nothing; it sits in `merging`). Keeps the diff scoped to the merger + tracker.

## Feedback (from completion gate)
- spec-compliance (codex, gpt-5.5/high): **SATISFIED**. No P1. Verdict sound but evidence partly
  confabulated after a mid-review stdout-channel failure (see Surprises) — corroborated by the two
  risk personas reading real code.
- review-arch: **SATISFIED**. No P1, no blocking P2. Confirmed in-memory-cache-over-durable is the
  right call, board-free intact, gh/git exec surface unchanged, the two cache mechanisms (per-pass
  `deferred` set vs cross-poll `prepared`) cleanly separated with disjoint write sites.
- review-reliability: **SATISFIED**. No P1. Confirmed the tripwire fix is genuine (broken before,
  restored now), no cache leak (drain-entry GC + terminal pop + request_id self-invalidation on a
  requeue's attempt bump), crash/restart degrades to pre-fix (no stuck ticket/double-merge),
  idempotency guard + fail-closed + flock-coherence + override-None all safe.
- code-quality (Claude general-purpose + rubric — codex declined to, given its demonstrated
  unreliability this session): **SATISFIED**. No P1. Three P2s: (#1) the `command`/`drive_kwargs`
  asymmetry on the gate-only path is intentional, no action; (#2) no test for an *escalated*
  gate-only retry; (#3) the original-intended test stubbed finalize (proves plumbing, not the
  catch). **#2 + #3 FIXED inline** (`test_gate_only_retry_catches_a_drop_with_the_real_gate`,
  615 green) — one real-gate test covering both.
- P2 tracked (not fixed; all three reviewers rated non-blocking and advised against the de-dup):
  drain reads `pending_merges()` twice per pass (orphan-GC at entry + the loop's first iteration)
  — one redundant small-file parse under the held flock, no race. → tech-debt-tracker.
- Proposed doc-rules tracked (arch + reliability each proposed one): a written
  ARCHITECTURE/RELIABILITY rule for *in-memory consumer-side caches that gate an irreversible act*
  — keyed on the durable item's identity, evicted on terminal AND GC'd against the live set, loss
  degrades to the pre-cache path. → tech-debt-tracker (doc-debt, not applied this slice = scope).

## Outcomes & retrospective
- Shipped: a CI-pending PR the merger already prepared no longer re-drives the full LLM land lane
  every poll — `run_loop`'s in-memory `{request_id: original pre-rebase intended}` cache feeds a
  gate-only retry path. Closes tech-debt row 94. Also closed a latent tripwire-blinding correctness
  gap as a bonus. 6 tests, gate GREEN (615), all four completion-gate reviews SATISFIED.
- What went well: the append-only-queue reading up front ruled out the unsafe literal-payload-
  mutation (Approach C) and grounded the in-memory-cache decision before any code; the cheap
  high-value P2 fix (real-gate retry test) turned the safety-critical claim from "plumbing proven"
  into "tripwire-catches-a-drop proven".
- What to watch: codex's review reliability degraded again (confabulated detail) — keep using it
  but always corroborate with a real-code reviewer; the [[codex-review-companion-scoping]] note
  stands. The two proposed doc-rules are worth landing in a future doc-gardening pass.
- Scope held: diff confined to `director/merger.py` + `tests/test_director_merger.py` + the two
  docs; decider/eligible_tickets/board ownership byte-unchanged; merger still board-free.
