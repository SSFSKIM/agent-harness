---
status: draft
last_verified: 2026-06-19
owner: harness
---
# Merge-preservation hardening

The serialized merger gains a **preservation-first land precondition**: before a
PR's work lands on `main`, code verifies the merge actually carries the PR's
intended change (nothing silently dropped or overwritten) and, secondarily, that
the PR's review hygiene is clean (CI green, no unresolved review threads). The
worker's PR-feedback-sweep stops being prose-only — its result becomes structured
evidence the merger records and a human/Director can audit.

## Context / grounds

- **Track:** Symphony-parity **gap #5** (agent operating-protocol depth) —
  [`docs/design-docs/symphony-parity-gap.md`](../design-docs/symphony-parity-gap.md).
  Slice 1 ([`2026-06-17-worker-operating-protocol.md`](2026-06-17-worker-operating-protocol.md))
  shipped the **PR feedback sweep** (`_IMPL_TEMPLATE` R7) and **acceptance
  mirroring** (R5) as worker prompt disciplines. Slice 2 / lights-out
  ([`2026-06-17-lights-out-director.md`](2026-06-17-lights-out-director.md), ADR
  0002/0003) shipped the escalation contracts. This spec is the **observability +
  enforcement** complement: the protocol prescribes the sweep, but nothing
  *verifies* it, and the merger's only "GREEN" today is the **local integration
  gate** (`check.py` on rebased `main`), which proves the code *integrates* — not
  that review feedback was handled, and not that the merge *preserved* both sides'
  work.
- **The merge path (today):** `orchestrator.reconcile` →
  `_maybe_enqueue_merge` (`orchestrator.py:99`) reads
  `outcome.pr_url`/`pr_branch` and `append_merge_request` (`queue/__init__.py:110`,
  payload carries `pr`/`branch`/`self_description`/`guidance`/`attempt`). The
  serialized merger (`merger.py`) drains FIFO, one PR at a time, driving the **land
  lane** (`run.drive` + the `land` skill) which **rebases onto latest `main`, runs
  the local integration gate, and — itself — `gh pr merge --squash`**
  (`land/SKILL.md:98`). A non-`done` land-lane outcome surfaces a `mergeReview`
  (`merger.py:190` `_surface_escalation`) to the Director; the Director may
  `requeue_merge` with guidance (attempt+1). The merger is **board-free** (the
  queue is its only hand-off; merge-gated-eligibility reads `merge_result=="merged"`).

## Problem

A squash-merge can pass every check and still corrupt `main`:

1. **Silent loss / overwrite (the dominant risk).** A rebase or conflict
   resolution can drop a hunk, or auto-merge two non-overlapping edits into
   something semantically broken (A deletes a symbol B still calls). The local
   integration gate catches this **only** where a test happens to exercise the
   lost behavior — a coverage gap becomes a silent overwrite on `main`. **Nothing
   today verifies the landed change is the faithful union of `main` + the PR.**
2. **No code gate on the irreversible action.** The land worker *itself* runs
   `gh pr merge --squash`. The `land` skill already prescribes "watch checks to
   green" and "do not merge while review comments outstanding" — but those are LLM
   prose. A worker that misreads the check rollup, treats a real failure as a
   flake, or merges with unresolved threads lands anyway. The objective gate is
   *prescribed* but not *enforced*.
3. **The sweep is unobserved.** The worker is told (slice-1 R7) to sweep the PR's
   checks + every comment channel before `report_outcome(done)`, but the only
   trace is prose in the PR body (`self_description`). There is no structured
   signal of "checks green / threads addressed / acceptance run", so a skipped or
   partial sweep is invisible and unauditable.

This is the merge-correctness counterpart to the worker-protocol depth track:
slice 1 told the worker *what to do*; this spec makes the **objective, irreversible
edge** (does this merge preserve the work?) enforced in code, while leaving the
**craft** (was each review reply a meaningful resolution? was a conflict resolved
faithfully?) as worker/land-lane judgment, surfaced for audit.

## Requirements

Each R is independently verifiable (a human can check the stated condition).

- **R1 — Preservation tripwire (code, primary).** Before a PR lands, code compares
  the **merge delta** (what the squash will add to `main`: the rebased branch's
  diff against the merge-base / current `main`) against the **PR's intended delta**
  (the PR branch's original diff against *its* base). If the merge delta is missing
  files the PR touched, or its net change is materially smaller (a dropped hunk
  signature), the merge is **withheld and escalated** (a `mergeReview` naming the
  specific files/shrink), **not** silently merged and **not** hard-rejected — it is
  a heuristic, so it routes to judgment. Verifiable: a PR whose rebase drops a hunk
  does not land; the `mergeReview` reason names the dropped path.
- **R2 — Faithfulness check (land skill, primary).** The `land` skill instructs the
  land worker, during/after rebase and conflict resolution, to verify that **both**
  `main`'s prior behavior and the PR's intended change survive the resolution, and
  to **escalate on any doubt** (extends the skill's existing no-force-merge stance).
  Verifiable: the skill text directs an explicit preservation check + escalate-on-
  doubt before declaring the PR ready.
- **R3 — Hygiene gate (code, secondary).** Before a PR lands, code verifies via
  `gh`: (a) the PR's **CI checks** (the `statusCheckRollup`) are **green**, and (b)
  there are **zero unresolved review threads**. *(a) classifies the whole rollup, not a
  "required" subset: this repo runs no branch-protection required checks (the land
  lane's local integration gate is the real test gate), and "a bad merge is worse than a
  delayed one" makes blocking on **any** red check the fail-safe direction — a
  non-required check the Director judges irrelevant is cleared via the
  approve-and-requeue path, same as a tripwire false-positive.* Tri-state outcome:
  - **green** → proceed to land;
  - **failing** → withhold + escalate (`mergeReview`, reason = which check failed);
  - **pending** (CI still running, e.g. re-triggered by the merger's rebase) →
    **defer**: leave the request pending, do not consume it, do not busy-spin, and
    do not block other queued PRs — retried on a later drain.

  The **unresolved-threads** half (b) is **enforced but configurable**
  (`director.merger`), defaulting **on**, because of a self-host nuance: a `gh`
  reply to a review comment does *not* auto-resolve the thread, so requiring
  zero-unresolved also requires the sweep to *explicitly resolve* threads it
  addresses (recorded in Decisions). Verifiable: a PR with a red CI check (any in the
  rollup), or with an unresolved review thread (when the knob is on), does not land; setting the
  knob off drops only check (b).
- **R4 — Structured sweep evidence + audit (wiring).** `report_outcome` gains
  **optional** `done`-only fields capturing the sweep's result (e.g.
  `checks_state`, `unresolved_threads`, `acceptance_verified`); the worker reports
  them, they flow `outcome → _maybe_enqueue_merge → merge payload → merger`, and the
  merger **records what it independently verified** alongside the worker's claim. A
  mismatch (worker reported clean, code found a red check / dropped hunk /
  unresolved thread) is **logged as a protocol misfire** (a structured log line),
  feeding the same audit-and-sharpen loop lights-out uses. Verifiable: a `done` with
  evidence produces a recorded comparison; a mismatch emits the misfire log.
- **R5 — Backward-compatible (regression net).** A `done` **without** evidence still
  lands (degraded): the merger falls back to its own independent verification and
  logs "no sweep evidence". A PR with no review threads / no required checks lands
  on the integration gate alone, exactly as today. The local integration gate
  (`check.py` on rebased `main`) is **unchanged** — it remains the independent
  second net. Existing merger/queue/orchestrator tests stay green.
- **R6 — Merger stays board-free; scope fence.** The merger acquires no board
  import and writes no board state; all withhold/escalate paths reuse the existing
  `mergeReview` channel. `git diff` touches only the worker terminal contract
  (`worker/tools.py`), the sweep text (`taxonomy.py`), the merger
  (`merger.py` + a thin gh/git helper), the land skill (`workspace_skills/land/`),
  config (`config.py` knob), `orchestrator.py` (payload passthrough only), tests,
  and docs. `decider.py`, board-state ownership, and `eligible_tickets` are
  untouched.

## Design

A single-subsystem slice: the **serialized merge path** plus the **worker terminal
contract that feeds it**. The local integration gate stays as-is; this adds a
preservation+hygiene gate *in front of the irreversible merge* and moves the merge
itself behind that gate.

### The spine — code owns the irreversible merge (the central decision)

Today the LLM land worker performs `gh pr merge --squash`. To make preservation
**preventive** (not merely detected after `main` is already corrupted) and the
hygiene gate **non-bypassable**, the squash-merge moves behind code:

- **Land worker (LLM) — *make the PR mergeable*.** Unchanged responsibilities:
  locate the PR, rebase onto latest `main`, resolve conflicts (R2 faithfulness +
  escalate-on-doubt), fix failing CI, reply to / resolve review threads, keep the
  local integration gate green, push the prepared branch. Its terminal `done` now
  means **"prepared and verified-ready"**, *not* "merged". The land skill's final
  step changes from `gh pr merge` to "report ready; the merger finalizes."
- **Merger (code) — *verify, then merge*.** After the land lane returns `done`, the
  merger runs, in the worker's workspace (where the branch + `gh`/`GH_TOKEN` live):
  1. **R1 preservation tripwire** (git diff comparison) — withhold+escalate on a
     drop signature;
  2. **R3 hygiene gate** (`gh` checks + unresolved threads) — green→continue /
     failing→escalate / pending→defer;
  3. only when both pass, **`gh pr merge --squash`** (the merge becomes a
     code-issued action), then `result = "merged"`.

  Any gate failure → the existing `_surface_escalation`/`mergeReview` path; the PR
  stays unmerged. Fail-closed: if `gh`/git is unavailable or a check cannot be read,
  **withhold + escalate** ("a bad merge is worse than a delayed one", per the land
  prompt's existing stance).

This makes `merge_result == "merged"` mean *code verified preservation+hygiene and
merged* — strictly stronger than today, and the signal merge-gated-eligibility
already consumes is unchanged in shape.

### Components & contracts

1. **`director/worker/tools.py` — `report_outcome` evidence (R4).** Extend
   `report_outcome_spec`'s `inputSchema` with optional `done` fields (sweep result:
   check state, unresolved-thread count, acceptance-run flag); `make_report_outcome_executor`
   records them into the outcome sink beside `pr_url`/`pr_branch`. Optional ⇒ a
   worker that omits them still produces a valid `done` (R5).
2. **`director/taxonomy.py` — sweep text (R4).** Reword `_IMPL_TEMPLATE`'s PR-feedback-
   sweep step so the sweep's *output* is the structured `report_outcome` evidence,
   and add (consistent with R3-b) "explicitly resolve each review thread you
   address". Preamble/other stages untouched.
3. **`director/merger.py` + a thin helper — the gate + code-merge (R1/R3/R6).**
   A new finalize stage (between land-lane `done` and `result="merged"`):
   - `preservation_delta(workspace, pr_base, branch) -> {ok, dropped_paths, …}` —
     computes and compares the two diffs (pure git, deterministic, unit-testable
     with a fixture repo / mockable subprocess).
   - `pr_hygiene(pr, *, require_threads) -> "green"|"failing"|"pending"` — `gh pr
     view --json statusCheckRollup` (+ unresolved-thread count when `require_threads`).
   - Wire into `process_request`/`drain`: on land-lane `done`, run tripwire→hygiene→
     code-merge; map failures to `escalated` via `_surface_escalation`, `pending`
     to **defer** (skip this request, do not consume, process other pending PRs,
     retry next drain — no head-of-line block, no spin). Record the worker-claim vs
     verified comparison; emit the misfire log on mismatch (R4).
4. **`director/workspace_skills/land/SKILL.md` — R2 + the merge-ownership change.**
   Add the preservation faithfulness check + escalate-on-doubt; change the final
   step from `gh pr merge --squash` to "do **not** merge — confirm the branch is
   rebased, gate-green, threads replied/resolved, then report ready; the merger
   finalizes the squash-merge after its preservation+hygiene gate."
5. **`director/config.py` — knob (R3).** Add `director.merger.require_resolved_threads`
   (default `True`) to `DEFAULTS["merger"]` + the `Merger` dataclass + `_build`.
6. **`director/orchestrator.py` — passthrough (R4).** `_maybe_enqueue_merge` forwards
   the worker's sweep evidence into the merge payload (likely the only change here;
   verify it needs no behavioral change beyond carrying the new field).
7. **`docs/DIRECTOR.md` §7** — document that the merger finalizes the merge behind a
   preservation+hygiene gate (land worker prepares; code verifies+merges), and that a
   tripwire/hygiene withhold surfaces as a `mergeReview` the Director adjudicates.

### Key behaviors & edge cases

- **Tripwire is a heuristic → judgment, with an override path.** A legitimate
  conflict resolution can correctly drop a hunk (the PR's change already partly in
  `main`). So a trip → escalate (with the specific delta), and the Director can
  **approve-and-requeue**: `requeue_merge`'s guidance carries an explicit
  preservation-override for that attempt, which the finalize stage honors (so the
  heuristic is never a hard wall). Mechanism (param vs guidance marker) is the
  ExecPlan's; the behavior — overridable on Director approval — is fixed here.
- **Pending CI must not stall the queue.** `defer` skips the pending request and
  lets the drain process other queued PRs, retrying the deferred one on a later
  drain pass (the merger's `run_loop` already polls with a sleep). No busy-spin, no
  head-of-line block.
- **No PR / no network / `gh` down.** Fail-closed: withhold + escalate (never an
  un-verified merge). Mirrors the deny-by-default posture.
- **Watched vs autonomous land lane unaffected.** The gate runs in `process_request`
  regardless of which decider the land lane used; it is code beside the land lane,
  not inside the turn loop.
- **Merge-gated-eligibility interplay.** `merge_result == "merged"` is now written
  only after the code gate + code-merge succeed — so a `merging`-parked ticket
  finalizes to `done` only on a *verified* land. No change to the reading side.

## Non-goals (scope fence)

- **Hard gates on craft.** The merger does not score "was each review reply
  meaningful" or block on subjective quality — that stays worker/Director judgment;
  code gates only the objective edge (preservation delta, check rollup, thread
  count). The tripwire escalates (judgment), never hard-rejects.
- **Board-ownership change / worker self-merge.** Unchanged (ADR 0002/0003). The
  merger stays board-free; the worker still only *proposes* via `report_outcome`.
- **The daemonized Director runtime.** Separate track; this spec is independent of
  it (the gate is code in the merger).
- **Branch-protection / required-CI-checks on the repo.** Considered and rejected:
  out of the director subsystem, requires repo-admin config, and the repo
  deliberately has no required checks (`land/SKILL.md:134`). The gate lives in our
  code, not GitHub config.
- **Enriching non-impl stage templates / changing the local integration gate.**
  Out of scope; `check.py`-on-rebased-`main` stays the independent second net.
- **A new board state or transport.** All withhold/escalate paths reuse the existing
  `mergeReview` channel.

## Acceptance criteria

- **R1:** a PR whose rebase/conflict-resolution drops a hunk the PR introduced does
  **not** land — the merger withholds and surfaces a `mergeReview` naming the
  dropped path; a Director approve-and-requeue lets it proceed.
- **R2:** `land/SKILL.md` directs an explicit both-sides-preserved check +
  escalate-on-doubt, and its final step no longer merges (reports ready instead).
- **R3:** a PR with a red CI check (any in the rollup) is withheld+escalated; one with CI still
  running is deferred (not consumed, not spun, other PRs still drain); with the
  threads knob on, an unresolved review thread withholds, and turning the knob off
  drops only that half.
- **R4:** a `done` carrying sweep evidence yields a recorded worker-claim-vs-verified
  comparison; a deliberate mismatch (claim clean, code finds red) emits the
  protocol-misfire log line.
- **R5:** a `done` with no evidence, and a PR with no threads/checks, both land on
  the independent integration gate as today; existing merger/queue/orchestrator/
  taxonomy tests stay green.
- **R6:** `git diff` is confined to the listed files; the merger has no board import;
  `decider.py` / `eligible_tickets` / board-state ownership are byte-unchanged.
- `python3 plugin/scripts/check.py` is GREEN.

## Decisions (resolved autonomously; recorded per product-design)

- **D1 — Code owns the irreversible merge (spine).** Chosen over (a) *detect-after*
  (keep `gh pr merge` in the land worker, audit `main` post-merge) — rejected because
  for preservation "detected after" means `main` was *already* overwritten, failing
  the stated "nothing overwritten" bar; and (b) *B-lite* (land worker invokes a
  mandatory code tripwire script before merging) — weaker, since it still trusts the
  LLM to run+obey before the irreversible action. Code-owned merge is the only option
  that **provably** gates the irreversible edge. Cost: the merger now shells `gh`/git
  for the final merge (it previously delegated all git to the land lane) — bounded and
  exactly the "irreversible action owned by code" the architecture favors.
- **D2 — Preservation is primary, hygiene secondary.** CI-green + threads-resolved is
  review *hygiene*; the dominant correctness risk is silent loss/overwrite. The
  tripwire (R1) is the headline gate; the hygiene gate (R3) rides along as a cheaper
  net. (Surfaced by the human during design.)
- **D3 — Tripwire escalates, never hard-rejects.** It is a heuristic (legit
  resolutions can change hunks), so a trip routes to Director/human judgment with an
  approve-and-requeue override.
- **D4 — `require_resolved_threads` is configurable, default on.** Self-host nuance: a
  `gh` reply does not auto-resolve a thread, so enforcing zero-unresolved also
  mandates the sweep explicitly resolve addressed threads (R3-b + taxonomy text). A
  host that uses a different review convention can turn it off; the check-green half is
  always on.
- **D5 — Evidence is optional (backward-compatible).** The worker self-report is the
  *audit* record; the merger's independent code verification is the *gate*. The gate
  never depends on the worker's claim — so omitting evidence degrades observability,
  not safety.
