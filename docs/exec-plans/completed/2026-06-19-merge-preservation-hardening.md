---
status: active
last_verified: 2026-06-19
owner: harness
base_commit: a401be7
review_level: standard
---
# Merge-preservation hardening — build

## Goal

The serialized merger no longer lets the LLM land worker squash-merge on its own
judgment. Instead, after the land worker *prepares* a PR (rebase, fix CI, resolve
threads), the merger runs a **code-owned gate** and performs the merge itself:
a **preservation tripwire** (the merge would drop a file/hunk the PR
introduced → withhold + escalate, never silently merge) and a **hygiene gate**
(CI not green / unresolved review threads → withhold/defer), then a code-issued
`gh pr merge --squash`. The worker's PR-feedback-sweep result rides as structured
`report_outcome` evidence the merger audits. Observable definition of done:
`python3 -m unittest discover -s tests -p 'test_director_merger*'` (and new
`test_director_tools`/`test_director_taxonomy` assertions) show, failing on
`base_commit` and passing at HEAD: a land-lane `done` whose rebase dropped a path
yields result `escalated` with a `mergeReview` naming the path (not `merged`); a
red required check → `escalated`; an unresolved thread (knob on) → `escalated`; CI
still pending → `deferred` while other queued PRs still drain; a clean PR →
`merged` via a code-issued `gh pr merge`; a Director approve-and-requeue with the
preservation override → `merged`. The full gate (`python3 plugin/scripts/check.py`)
is GREEN, and `git diff a401be7..HEAD` is confined to the spec's touch surface with
`decider.py`/`eligible_tickets`/board-state ownership byte-unchanged and the merger
holding no board import.

## Context

- **Spec (owns the design — do NOT re-derive):**
  `docs/product-specs/2026-06-19-merge-preservation-hardening.md` — R1–R6 + Design +
  D1–D5. This plan builds it. The spine (D1): code owns the irreversible merge.
- **Track / decisions:** Symphony-parity gap #5 (worker-protocol depth);
  `docs/memory/adr/0002-graduated-autonomy.md` + `0003-lights-out-director.md`. The
  PR-feedback-sweep + acceptance-mirroring shipped as prose in slice 1
  (`docs/exec-plans/completed/2026-06-17-worker-operating-protocol.md`,
  `_IMPL_TEMPLATE` R5/R7); this plan makes the objective edge code-enforced.
- **The merge path today (verified this session):**
  - `director/worker/tools.py:25` `report_outcome_spec` already carries optional
    `pr_url`/`pr_branch`; `:66` `make_report_outcome_executor` records them into the
    outcome sink. M1 adds optional sweep-evidence fields the same way.
  - `director/orchestrator.py:99` `_maybe_enqueue_merge(tid, ticket, outcome, …)`
    reads `outcome.pr_url`/`pr_branch` and (`:121`) calls
    `dq.append_merge_request(tid, pr=…, branch=…, …)`. M1 forwards evidence here.
  - `director/queue/__init__.py:110` `append_merge_request(ticket_id, *, pr, branch,
    workspace_path, self_description, guidance, attempt, …)` builds the request
    payload. M1 adds an `evidence` kwarg carried into the payload.
  - `director/merger.py`: `_LAND_PROMPT`/`land_prompt` (`:45`/`:74`) frame the land
    lane; `land_ticket_from_request` (`:90`) reuses the worker's workspace;
    `classify(disp)` (`:101`) maps a land-lane disposition → `merged|failed|escalated`
    (today `terminal(done)` → `merged`); `_surface_escalation` (`:190`) posts a
    `mergeReview`; `process_request` (`:214`) drives one request; `drain` (`:229`)
    pops FIFO, surfaces-before-consume (`:249`), consumes (`:254`). M4 inserts the
    finalize stage between land-lane `done` and the `merged` classification.
  - The land worker itself runs the merge today: `director/workspace_skills/land/SKILL.md:98`
    `gh pr merge --squash`. M4 changes this to "report ready; do not merge."
  - `director/config.py:83` `DEFAULTS["merger"]`, `:121` `Merger` dataclass, `:246`
    `_build` merger branch. M3 adds the `require_resolved_threads` knob here.
- **The merger runs in the worker's workspace** (`land_ticket_from_request` reuses
  `req.workspace_path`) with `GH_TOKEN` in `worker_env` (`.harness.json`) — so the
  finalize stage has `git`/`gh` available there.
- **Grounding for reviewers:** `docs/RELIABILITY.md` (fail-closed, act-before-consume
  R19, no-spin), `ARCHITECTURE.md` + `docs/DESIGN.md` (layer law, merger board-free).

## Approach (self-generated alternatives — execution choices the spec left open)

The spec fixed the design; these are the build choices:

1. **Where the finalize stage lives.**
   - A — a new `finalize_merge()` called from `drain` after `process_request` returns.
   - B — fold finalize **into** `process_request`: drive the land lane, and on
     `terminal(done)` run tripwire→hygiene→code-merge, returning the resulting
     `result` (`merged`/`escalated`/`deferred`). **Chosen: B** — keeps `process_request`
     the single "process one request fully" unit and leaves `drain`'s
     surface-before-consume discipline intact; `drain` only learns the new
     `deferred` result.
2. **Tripwire diff metric (M2).** Pure logic over `git diff --numstat`:
   `preservation_delta(pr_numstat, merge_numstat) -> {ok, dropped_paths, shrunk_paths}`
   — a path in the PR's delta **absent** from the merge delta is `dropped`; one whose
   added-line count fell materially (below a fraction, default conservative) is
   `shrunk`. Chosen over a hunk-by-hunk semantic diff (overkill; the spec says
   heuristic→escalate, so favor a cheap signal + Director override). A thin
   `collect_numstats(workspace, base, branch)` wrapper shells `git` (argv) to produce
   the two numstats; the pure comparator is unit-tested with fixtures, the wrapper is
   mockable. (Unknown → M2 validates the comparator on a fixture first.)
3. **Evidence on the payload (M1).** Add an `evidence` kwarg to
   `append_merge_request` (mirrors `self_description`), carried into the payload dict
   — chosen over packing into `self_description` (mixes prose + structured) and over a
   parallel queue record (needless transport).
4. **Pending-defer mechanism (M4).** `process_request` returns `result="deferred"` for
   CI-pending; `drain` does **not** consume a deferred request, records its id in a
   per-pass `deferred` set, and skips it when picking the next pending — so the pass
   drains every *non-deferred* PR and ends when only deferred remain; `run_loop`'s poll
   retries next pass. No busy-spin, no head-of-line block. Chosen over sleeping inside
   the gate (blocks the single consumer) and over re-enqueue-at-tail (reorders FIFO,
   loses attempt provenance).
5. **Override (M4, D3).** A `preservation_override` boolean on the requeue payload,
   set when the Director approves a flagged drop; the finalize stage skips the tripwire
   (still runs hygiene) when present. Chosen over parsing the free-form guidance string
   (fragile).

## Assumptions & open questions (self-interrogation)

- **Assumption:** the land lane's `terminal(done)` reliably means "branch is rebased,
  gate-green, threads replied, pushed" once M4 rewrites the land skill. If a land
  worker reports `done` without pushing, the finalize stage's `gh`/git reads operate on
  a stale remote → hygiene/tripwire fail-closed → escalate (safe). Acceptable.
- **Assumption:** `gh pr view --json statusCheckRollup,reviewThreads,...` is available
  with the merger's `GH_TOKEN`. If `gh` is absent/unauthed → fail-closed escalate
  (R3 edge). Tests mock `gh`.
- **Assumption:** `report_outcome` evidence is advisory only; the gate never trusts it
  (D5). So the evidence schema can be loose (optional strings/ints) without weakening
  safety.
- **Open:** exact `git` refs for the two numstats (PR-base vs post-rebase main). →
  resolved in M2: PR-delta = `git diff $(git merge-base <base> <branch>)..<branch>`
  computed from the PR's base ref in the payload; merge-delta = `git diff
  <base>..<branch>` against current main tip. The comparator is ref-agnostic (takes
  numstats), so this lives in the mockable wrapper.
- **Open:** does the Director's requeue entrypoint already thread a payload flag? →
  resolved in M4: confirm the requeue path (`director_min`/queue `requeue_merge` or the
  `mergeReview` answer) and add the `preservation_override` flag there; if no clean
  seam exists, carry it as a payload key set on re-append. (Not "handle later" — M4
  owns wiring it; the behavior is fixed: override honored on Director approval.)
- **Open (escalate? No — recorded):** the `shrunk` fraction threshold is a tuning
  knob; default conservative (only flag a clear shrink) to keep false-positives low —
  recorded in Decision log, not a product fork.

## Milestones

- **M1 — R4 evidence channel.** Scope: the structured-evidence wiring, end to end,
  with no gate yet. At the end: `report_outcome` accepts optional `done`-only fields
  (`checks_state: str`, `unresolved_threads: int`, `acceptance_verified: bool`),
  `make_report_outcome_executor` records them into the outcome sink beside
  `pr_url`/`pr_branch`; `taxonomy._IMPL_TEMPLATE`'s sweep step is reworded so its
  *output* is that structured report and it says "explicitly resolve each review thread
  you address"; `orchestrator._maybe_enqueue_merge` forwards the evidence into the merge
  payload via a new `append_merge_request(..., evidence=…)` kwarg. Run `python3 -m
  unittest discover -s tests -p 'test_director_tools*' -p 'test_director_taxonomy*' -p
  'test_director_orchestrator*'`. Expect: new assertions green — the executor records
  evidence when present and a bare `done` (no evidence) still yields a valid outcome
  (R5); the impl prompt contains the structured-evidence + resolve-threads phrasing;
  the enqueued payload carries `evidence`. Existing tools/taxonomy/orchestrator tests
  stay green.

- **M2 — R1 preservation tripwire helper.** Scope: the deterministic comparator + its
  git wrapper, standalone (not wired into the merger yet). At the end: a new helper
  (in `director/merger.py` or a sibling `director/merge_preserve.py`)
  `preservation_delta(pr_numstat, merge_numstat) -> {"ok": bool, "dropped_paths":
  [...], "shrunk_paths": [...]}` (pure), plus `collect_numstats(workspace, base,
  branch)` shelling `git diff --numstat` with argv. Run `python3 -m unittest discover
  -s tests -p 'test_*preserve*' -p 'test_director_merger*'`. Expect new unit tests
  green: identical deltas → `ok=True`; a path present in PR-delta but absent in
  merge-delta → `dropped_paths=[that]`, `ok=False`; a path whose added lines fell below
  the threshold → `shrunk_paths`; the wrapper parses `--numstat` correctly (fixture or
  mocked `subprocess`). This is a PoC-first milestone: validate the comparator on a
  fixture before M4 depends on it.

- **M3 — R3 hygiene gate helper + config knob.** Scope: the `gh`-backed tri-state
  classifier + the config knob, standalone. At the end: `pr_hygiene(pr, *,
  require_threads) -> "green"|"failing"|"pending"` shelling `gh pr view --json
  statusCheckRollup,reviewThreads` (argv, never a shell string), returning `pending`
  when any required check is still running, `failing` on a failed/!= success rollup or
  any unresolved thread (when `require_threads`), `green` otherwise; **fail-closed**
  (`gh` error / unparseable / missing → treat as `failing` so the merge is withheld);
  and `director.merger.require_resolved_threads` (default `True`) added to
  `config.DEFAULTS["merger"]`, the `Merger` dataclass, and `_build`. Run `python3 -m
  unittest discover -s tests -p 'test_director_merger*' -p 'test_director_config*'`.
  Expect: green/failing/pending each classified from a mocked `gh` JSON; the threads
  knob off ignores unresolved threads; a `gh` non-zero exit → `failing`; config loads
  the knob with the default and honors an override.

- **M4 — The spine: code owns the merge (R1/R2/R3/R6).** Scope: wire M2+M3 into the
  merger as the finalize stage, move the merge into code, and rewrite the land skill.
  At the end: `process_request`, on a land-lane `terminal(done)`, runs
  `collect_numstats`→`preservation_delta` (skipped when `payload.preservation_override`),
  then `pr_hygiene`; maps `dropped/shrunk` and `failing` → withhold (returns a result
  that `_surface_escalation` posts as a `mergeReview` whose reason names the dropped
  path / failed check), `pending` → `result="deferred"`; on both-clean it performs the
  code-issued `gh pr merge --squash --subject/--body` (argv, in the workspace) and
  returns `merged`. It also records the worker-claimed evidence vs what it verified and
  emits a structured `protocol_misfire` log line on mismatch. `drain` handles
  `deferred` (no consume, per-pass skip, no spin). `workspace_skills/land/SKILL.md`
  gains the R2 both-sides-preserved faithfulness check + escalate-on-doubt and its final
  step changes from `gh pr merge --squash` to "do NOT merge — confirm rebased,
  gate-green, threads replied/resolved, then report ready; the merger finalizes." Run
  `python3 -m unittest discover -s tests -p 'test_director_merger*'`. Expect new tests
  green: clean → `merged` (a mocked code-issued `gh pr merge` invoked); dropped path →
  `escalated` + mergeReview names it; red check → `escalated`; unresolved thread (knob
  on) → `escalated`; pending → `deferred` and a second clean PR in the same pass still
  `merged`; `gh`/git failure → `escalated` (fail-closed); `preservation_override` on
  requeue → tripwire skipped → `merged`; and `import director.board` is absent from
  `merger.py` (merger stays board-free, R6).

- **M5 — Docs + behavioral + scope-fence.** Scope: documentation, the behavioral
  acceptance, and the diff fence. At the end: `docs/DIRECTOR.md` §7 describes the new
  split (land worker prepares; merger code verifies-then-merges; a tripwire/hygiene
  withhold surfaces as a `mergeReview` the Director adjudicates, with the approve-and-
  requeue override). Behavioral check: a fixture/mock-driven merger run (no live GitHub
  PR is available in the gate env — recorded as the behavioral-QA note) demonstrating a
  drop-PR does **not** land and surfaces a `mergeReview`, and a clean PR lands via the
  code path — captured in Outcomes. Scope-fence: `git diff a401be7..HEAD --stat` lists
  only `director/worker/tools.py`, `director/taxonomy.py`, `director/merger.py` (+ any
  `director/merge_preserve.py`), `director/workspace_skills/land/SKILL.md`,
  `director/config.py`, `director/orchestrator.py`, the new/changed tests, and docs; and
  `git diff a401be7..HEAD -- director/decider.py` is empty. Run `python3
  plugin/scripts/check.py`; expect GREEN. This is the pre-completion-gate checkpoint.

## Progress log
- [x] (2026-06-19) Plan created from spec; base_commit a401be7, review_level standard.
- [x] (2026-06-19) M1 done — R4 evidence channel. `report_outcome_spec` gains optional
  `checks_state`/`unresolved_threads`/`acceptance_verified`; the executor groups present
  fields into `outcome["evidence"]` (or None) — `is not None` keeps falsy-valid 0/False.
  `taxonomy._IMPL_TEMPLATE` sweep step now mandates explicit thread resolution + ties
  `report_outcome` evidence to the sweep result + notes the merger re-verifies.
  `queue.append_merge_request(evidence=…)` carries it into the payload;
  `orchestrator._maybe_enqueue_merge` forwards `outcome.get("evidence")`. Tests:
  `ReportOutcomeTest` (5, test_director_tools) + taxonomy evidence/resolve-threads test +
  2 orchestrator payload tests. Targeted suites 103 OK; full gate GREEN. Backward-compat
  confirmed (mock `done` → `"evidence": null`).
- [x] (2026-06-19) M2 done — R1 preservation tripwire helper. New `director/merge_preserve.py`:
  `parse_numstat` (handles binary `-` + malformed lines), `preservation_delta(intended,
  actual)` → `{ok, dropped_paths, shrunk_paths}` (dropped = path absent from the merge;
  shrunk = added fell to ≤0.5× AND ≥3 lines — conservative, low false-positive per D3), and
  `numstat_from_cmd(argv, …)` shelling with argv (never a shell string — PR ref/branch are
  untrusted) and fail-closed (None on non-zero/exception). 13 unit tests; full gate GREEN
  (571). Ref-acquisition decision: INTENDED = `gh pr diff --numstat` captured at
  `process_request` START (pre-rebase), ACTUAL = post-rebase `git diff --numstat
  base..branch` — both merger-local (gh/git there), wired in M4.
- [x] (2026-06-19) M3 done — R3 hygiene gate helper + config knob. Added to
  `merge_preserve.py` (broadened to "merge-gate code checks"): `classify_checks(rollup)` →
  green/failing/pending (fail>pending>green precedence; empty→green per R5), `pr_hygiene(pr,
  *, require_threads)` (checks via `gh pr view --json statusCheckRollup`; threads via
  `gh api graphql` reviewThreads — verified `gh pr view --json` does NOT expose reviewThreads,
  hence graphql + url parse; fail-closed → "failing"; pending short-circuits the thread query),
  `unresolved_thread_count` (url→owner/repo/number→graphql). Config: `merger.require_resolved_threads`
  (default True) in DEFAULTS + `Merger` + `_build` via `_bool`. 16 helper tests + 2 config
  tests. Full gate GREEN (588).
- [x] (2026-06-19) M4 done — the spine: code owns the merge. `merger.process_request`
  captures the PR's intended files pre-rebase, drives the land lane, and on a prepared
  `done` runs `_finalize_merge` (preservation tripwire → hygiene gate → code-issued
  `gh pr merge --squash`); drop/failing → `escalated` (mergeReview names the dropped
  path / failed check, via `_surface_escalation` now preferring `gate_reason`), pending →
  `deferred` (drain skips it this pass via a per-pass set — no consume, no surface, no
  head-of-line block, no spin), both-clean → `merged`. `_log_misfire` emits a structured
  `protocol_misfire` when worker-claimed-clean contradicts a withheld gate (R4).
  `preservation_override` flows `requeue_merge`→`append_merge_request`→payload→finalize
  (Director approve-and-requeue skips the tripwire; D3). `require_resolved_threads` threaded
  config→main→run_loop→drain→finalize. Replaced M2's numstat helpers with `files_from_pr`
  (see Surprises). land/SKILL.md: R2 preservation-faithfulness check + escalate-on-doubt,
  and the final step no longer self-merges (reports ready). +13 tests (FinalizeGateTest,
  GateIntegrationTest incl. no-head-of-line + misfire, LandSkillPreparesTest); existing
  drain-mechanics tests stub the injectable `finalize`. Full gate GREEN (601).
- [x] (2026-06-19) M5 done — docs + behavioral + scope-fence. `docs/DIRECTOR.md` §7 now
  describes the land-worker-prepares / merger-code-verifies-then-merges split, the
  preservation-tripwire + hygiene-gate withhold as `mergeReview` causes (reason names the
  path), and the `preservation_override=True` approve-and-requeue. **Behavioral acceptance**
  (mocked gh — no live GitHub PR in the gate env, recorded N/A-for-live): `GateIntegrationTest`
  (6) GREEN — a dropped-hunk PR does NOT land and surfaces a `mergeReview` naming the path; a
  clean PR lands via the code merge; pending CI defers unsurfaced + stays pending; a deferred
  PR does not block a sibling (no head-of-line); the protocol-misfire logs on claim-vs-gate
  contradiction; merger has no board import. **Scope-fence** (`git diff a401be7..HEAD`):
  `decider.py` byte-empty; `eligible_tickets` untouched; merger board-free. Files changed are
  the merge-path subsystem — the spec's enumerated surface PLUS `queue/__init__.py` (the
  `evidence` + `preservation_override` payload keys) and `director_min.py` (`requeue_merge`
  threads the override): both anticipated by R4 ("flowing through … merge payload") and D3
  (Director approve-and-requeue), within-subsystem, not a fence breach. Full gate GREEN (601).

## Surprises & discoveries
- (2026-06-19, M4) **`gh pr diff` has no `--numstat`.** M2 built `parse_numstat`/
  `numstat_from_cmd` for `git diff --numstat`, but the clean per-file source for a PR's
  change is `gh pr view <pr> --json files` (`[{path, additions, deletions}]`) — single
  call, no base-ref gymnastics (GitHub computes the PR diff vs its base). M4 replaced the
  numstat helpers with `files_from_pr` (the shape-agnostic `preservation_delta` core was
  kept unchanged). Lesson: M2 was PoC-first without confirming the gh interface; verifying
  it in M3 (also `reviewThreads` absent → graphql) caught both before wiring.
- (2026-06-19, M4) `gh pr view --json` exposes neither `reviewThreads` (→ `gh api graphql`)
  nor a `--numstat` on `pr diff` — both confirmed against the installed gh 2.87.3.

## Decision log
- 2026-06-19: Finalize stage folded into `process_request` (Approach B) — keeps
  `drain`'s surface-before-consume intact; `drain` learns only the `deferred` result.
- 2026-06-19: Tripwire = `git diff --numstat` file-set + added-line comparison
  (`dropped`/`shrunk`), pure comparator + mockable git wrapper; heuristic→escalate, so
  cheap signal over semantic diffing.
- 2026-06-19: Evidence rides a new `append_merge_request(evidence=…)` kwarg into the
  payload; advisory only (the gate never trusts it — D5).
- 2026-06-19: Pending → `deferred` result + per-pass skip set in `drain`; no in-gate
  sleep, no FIFO reorder.
- 2026-06-19: `shrunk` threshold defaults conservative (flag only a clear shrink) to
  keep false-positives low; tuning knob, not a product fork.
- 2026-06-19 (M4): the code gate is an injectable `finalize` seam on
  `process_request`/`drain` — drain-mechanics tests stub it to "merged" (keeping their
  FIFO/serialization intent), while the gate's behavior is tested directly
  (`_finalize_merge` + a fake `sh`). Avoids re-mocking gh in every mechanics test.
- 2026-06-19 (M4): preservation source = `gh pr view --json files` (not git numstat),
  captured pre-rebase (intended) in `process_request` and post-rebase (actual) in
  `finalize` — both via the injectable `sh`, both fail-closed.

## Feedback (from completion gate)

**Round 1 (2026-06-19).** review-spec-compliance (codex gpt-5.5) → **NOT-SATISFIED**;
review-arch (Claude persona) → **SATISFIED**. Findings processed:
- **P1 (codex) — audit incomplete (R4/R5).** `_log_misfire` only logged contradictions; the
  spec requires recording claim-vs-verified AND a "no sweep evidence" log. **Fixed:**
  `_log_evidence_audit` emits `no_sweep_evidence` / `protocol_misfire` / `sweep_evidence_verified`
  on every finalized (non-deferred) result. +2 tests.
- **P1 (codex) — hygiene gated all checks, spec said "required".** **Fixed by clarifying the
  spec** (R3-vs-Design imprecision; the Design always said "classify the rollup"): R3 now reads
  "CI checks (the statusCheckRollup)", with a recorded rationale — this repo runs no required
  checks, blocking on any red check is the fail-safe direction, and a non-required red is
  cleared via approve-and-requeue. `classify_checks` gains the same comment.
- **P1 (codex) — reviewThreads `first:100` could miss page 2.** **Fixed:** the query requests
  `pageInfo{hasNextPage}` and `unresolved_thread_count` fails closed (None → withhold) when
  there is a next page. +1 test.
- **P2 (codex) — land skill frontmatter still advertised "squash-merging".** **Fixed:** the
  description now says it prepares the PR and the merger lands it.
- **P2 (arch) — `require_resolved_threads` default literal duplicated DEFAULTS** (ARCHITECTURE
  invariant 5). **Fixed:** `DEFAULT_REQUIRE_RESOLVED_THREADS` aliased from DEFAULTS, used as the
  signature default in process_request/drain/run_loop.
- **P2 (arch) — a deferred (CI-pending) PR re-drives the FULL land lane on every poll** (the
  spec's "no busy-spin" intent; the per-pass `deferred` set prevents head-of-line within a pass
  but not cross-poll re-drive). **Tracked** (tech-debt-tracker) — the correct fix needs cross-poll
  prepared+intended state so a re-check runs the gate only; not a correctness/data-loss bug
  (the PR is never wrongly landed or lost), so fix-forward per arch's P2 rating.
- **Proposed rules (arch, non-blocking) — tracked:** (1) a DESIGN.md note that merger `gh` calls
  address the PR by full URL (cwd-independent); (2) a rule clarifying misfire scope (worker-claim-
  false vs gate-caught-uncovered). Below P2; promote on recurrence.

**Round 2 (2026-06-19).** review-reliability (Claude persona) → **SATISFIED**; the codex
spec-compliance re-run TRUNCATED (no captured verdict) but surfaced a real land-skill
contradiction before cutoff — both processed:
- **P2 (reliability) — crash-after-merge-before-consume strands the ticket.** A crash between
  `gh pr merge` succeeding and `_consume` re-drives finalize; re-merging a MERGED PR fails →
  escalated → `merge_outcome` reads `unresolved` → the ticket sits in `merging` forever though
  its PR landed. **Fixed** (chose to fix, not defer — small + prevents a real stuck-ticket):
  `merge_preserve.pr_is_merged` + an idempotency guard in `_finalize_merge` (on merge failure,
  if the PR is already MERGED → result `merged`). +4 tests. Reliability's proposed rule
  ("irreversible external side effects guarded by a has-it-already-happened check") is the
  generalization — noted for promotion.
- **P1-equivalent (codex, recovered from a truncated run) — stale "before merge" framing in the
  land skill body** (`Failure/Review Handling`: "Do not merge while review comments
  outstanding", "acknowledged before merge", "before merging") contradicted R2/D1's
  prepare-not-merge model. **Fixed:** reworded to "report the PR ready" / "before you report
  ready" (the worker resolves threads first; the merger lands).
- **P2 (reliability) — deferred-PR cross-poll re-drive** — same finding as arch's; already tracked.

**Round 3 (2026-06-19).** review-spec-compliance (Claude fallback — codex truncated twice;
the dedicated persona isn't in this session's registry) → **NOT-SATISFIED** on two remaining
P1s, now fixed:
- **P1×2 — two more stale self-merge phrasings in the land skill** that round 2 missed: step 6
  ("handled before merging") and Review Handling ("before requesting a new review or merging").
  **Fixed** → "before you report the PR ready". Added a **regression assertion** to
  `LandSkillPreparesTest` (`before merging` / `review or merging` absent) so the gate catches
  this class, not just a reviewer.
- **P2 — spec acceptance still said "red required check"** (the R3 body was clarified in round 1
  but the acceptance shorthand wasn't). **Fixed** → "red CI check (any in the rollup)".
- P2 (deferred re-drive) + P2 (queue/director_min outside R6's enumeration) — already tracked /
  documented as defensible; no change.

Re-review (clean spec-compliance verdict + code-quality) follows this gate re-run.

## Outcomes & retrospective
