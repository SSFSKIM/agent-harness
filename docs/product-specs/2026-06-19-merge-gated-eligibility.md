---
status: draft
last_verified: 2026-06-19
owner: harness
---
# Merge-gated DAG eligibility — a child waits for the parent's PR to LAND, not just to be "done"

A child ticket's `blocked_by` edge must clear only when the parent's PR has actually
**landed on `main`**, not merely when the worker reported `done`. Today the two events are
decoupled, so a child can start on a stale base. **Direction A** (human pick, 2026-06-19,
over stacked-branches B and minimal-guard C): make the board's `done` state *mean*
"merged-to-main", so the existing `done_types` eligibility gate becomes correct.

Parent: [symphony-director-orchestration](2026-06-14-symphony-director-orchestration.md)
(Phase 5 correctness). Sibling: [symphony-parity-gap](../design-docs/symphony-parity-gap.md).
Grounding: **RELIABILITY R19** (act-before-consume), the ARCHITECTURE principle that **the
orchestrator owns board writes** (the merger never writes the board — it surfaces via the
queue), and Symphony's ticket lifecycle Todo → In Progress → Human Review → **Merging** →
Done (`docs/symphony-original/SPEC.md` §6/§8).

## Problem (what is unsatisfied today — observable)

The DAG resolves dependencies through `main`, but eligibility is keyed on the wrong event.

1. **`done`-on-board ≠ merged-to-main.** In `reconcile` a `done` worker outcome enqueues the
   PR-merge and then **immediately** sets the board to `done`
   (`orchestrator.py:179-181`): the merge is only *queued*, the serialized merger lands it
   *asynchronously, later*.
2. **Eligibility clears on `done`.** `eligible_tickets` (`orchestrator.py:257-263`) clears a
   `blocked_by` edge when the blocker's `state_type ∈ done_types` (`"completed"`).
3. **⇒ A child can dispatch while the parent's PR is still unmerged** (sitting in the
   merger's queue, or escalated as a `mergeReview`). The child's workspace clones / `git
   reset --hard origin/<default>` from a `main` that does **not** yet contain the parent's
   work, so it builds on a stale base — and its own PR later conflicts or silently drops the
   parent's foundation. *Observable:* parent `done` on tick N, merger lands on tick N+k; a
   child created/unblocked in between is dispatched against pre-parent `main`.

This is reachable in the daemon (the real runtime) and in batch when the merger lags.

## Requirements

- **R1 — `merging` is a distinct, OPTIONAL board state.** `config.DEFAULTS["states"]` gains
  `"merging": None`, validated like the existing optional `failed`/`blocked` (a host maps it
  to a "Merging" workflow state via `.harness.json` `director.states.merging`). When
  **unconfigured**, the whole feature is inert and behavior is byte-identical to today
  (additive, opt-in). *Verifiable:* configuring `director.states.merging: "Merging"` resolves
  at load; omitting it leaves `resolve_states` and all behavior unchanged.
- **R2 — A PR-bearing `done` parks in `merging`, not `done`.** When `merging` is configured,
  a `terminal(done)` disposition **that enqueued a merge** transitions the board to `merging`
  (not `done`); the merge enqueue still happens **first** (R19 act-before-consume preserved).
  A `done` outcome with **no PR** (planning/research/design/spec tickets — `_maybe_enqueue_merge`
  returned False) transitions to `done` **immediately**, exactly as today. *Verifiable:* a
  done disposition carrying `pr_url`/`pr_branch` → board `merging` + a `merge|<tid>|a1`
  queued; a done disposition with no PR fields → board `done`.
- **R3 — The ORCHESTRATOR completes `merging` → `done` on observing the land.** Once per tick
  (`run_forever`) and once per pass (`run_until_drained`), the orchestrator reads the
  `merging`-state tickets (`board.fetch_issues_by_states(team, [merging_id])` — the parity-R1
  op) and, for each whose merge **landed** (its latest `merge|<tid>|aN` answer carries
  `merge_result == "merged"` and no `merge|<tid>|*` is still pending), transitions it to
  `done` + comments. A still-pending or escalated/abandoned merge leaves the ticket in
  `merging`. Fail-soft per §8.6 (a board/queue read error skips the sweep, never crashes the
  loop). *Verifiable:* after the merger writes `merge_result=merged`, the next orchestrator
  reconcile moves the ticket `merging`→`done`; a ticket with a pending merge stays `merging`.
- **R4 — Eligibility is unchanged and now correct.** `eligible_tickets` is **not modified**:
  a child `blocked_by` a parent stays ineligible while the parent is `merging`
  (`merging` `state_type ∉ done_types`) and becomes eligible only once the parent reaches
  `done` (= merged, via R3). *Verifiable:* a child whose only blocker is a `merging` parent is
  not dispatched; the instant the parent reaches `done` the child is dispatched on the next poll.
- **R5 — An abandoned / permanently-escalated merge keeps the parent in `merging`.** If the
  Director resolves a `mergeReview` as `abandon`/`human` (the PR never lands), the orchestrator
  never observes `merged`, so the parent stays `merging` and dependent children stay blocked
  (no build on a foundation that isn't on `main`). The dependency impact is the human's to
  resolve (re-target the child's blocker, or accept) — surfaced through the existing
  abandon/human escalation. *Verifiable:* abandon → parent stays `merging` → child stays
  blocked; a re-land (`requeue_merge` → a new `merge|<tid>|a2` that lands) clears it.
- **R6 — Crash-safety / idempotency preserved.** Enqueue-before-board-write is retained (a
  crash between leaves the ticket in `started` → orphan-recovered → re-run; once `merging`,
  the merge is queued so startup cleanup's pending-merge exclusion still protects the branch).
  The `merging`→`done` sweep is idempotent (setting `done` on an already-`done` ticket is a
  no-op; a crash after a land but before the board write is fixed on the next sweep). The
  **merger stays board-free** — it writes only the queue answer, exactly as today. *Verifiable:*
  running the sweep twice is a no-op; `merger.py` gains no board dependency.
- **R7 — Additive; existing contracts preserved; gate GREEN.** No change to the decider, the
  queue schema (reuses the `merge|<tid>|aN` answer + pending read), the merger's contract,
  active-run reconciliation, orphan recovery (only re-attaches `started`, so `merging` is
  ignored), or the batch/daemon loop structure beyond the one new sweep call. `merging`
  unconfigured → byte-identical. `python3 plugin/scripts/check.py` GREEN. *Verifiable:* diff
  is additive; the full suite passes with and without `merging` configured.

## Design

Additive. The whole change is: one optional state, a one-line branch in `reconcile`'s `done`
path, and one new orchestrator sweep that reuses the parity `fetch_issues_by_states` op. The
key property — **eligibility, orphan-recovery, and active-run-reconciliation stay pure board
reads** — falls out of representing "merged-but-not-done" as a board state rather than a
queue-consulting predicate.

### Component 1 — `director/config.py` (R1)
- `DEFAULTS["states"]` gains `"merging": None`; `_STATE_KEYS` gains `"merging"`. `_build`
  already validates each state key as string-or-None (reuse). `resolve_states`
  (`orchestrator.py:46`) resolves `merging` in the **optional** group with `failed`/`blocked`
  (a configured-but-missing name fails loud at startup; `None` → feature inert).

### Component 2 — `director/orchestrator.py` `reconcile` (R2)
- In the `terminal`/`ostatus == "done"` branch (`orchestrator.py:171-184`): keep the
  act-before-consume order — `enqueued = _maybe_enqueue_merge(...)` **first**. Then:
  - `if enqueued and states.get("merging"): set_state(states["merging"])` →
    `summarize("completed", "merging", merge_enqueued=True)` (worker outcome is still
    `completed`; the *board* `final_state` is `merging`).
  - `else: set_state(states["done"])` → `summarize("completed", "done", ...)` (today's path —
    covers the no-PR ticket AND the `merging`-unconfigured fallback).

### Component 3 — `director/orchestrator.py` merge-completion sweep (R3, R5)
- A new `_reconcile_merges(board, team, states, queue_base, *, status=None)` (sibling of
  `_startup_recovery`):
  - if `not states.get("merging")`: return (inert).
  - `for t in board.fetch_issues_by_states(team, [states["merging"]])`: determine the merge
    outcome for `t["id"]` from the queue — **landed** iff no `merge|<id>|*` is in
    `read_pending()` **and** the latest answered `merge|<id>|aN` has
    `merge_result == "merged"`; otherwise pending/unresolved. On landed → `set_state(done)` +
    `comment("🔀 PR landed — merged to main")`.
  - Best-effort/fail-soft (§8.6): wrap the board/queue reads; a failure logs and skips the
    sweep (mirrors `_startup_recovery`'s `…_skipped` discipline), never crashes the loop.
- **Call sites:** once per tick in `run_forever` (after `reap`/`drain_accrual`, beside
  `reconcile_in_flight`) and once per pass in `run_until_drained` (before re-poll), so a
  landed parent is finalized and its children become eligible on the very next poll.
- **Merge-outcome helper** (in `merger.py` or `queue`, reused by both the sweep and tests):
  `merge_outcome(tid, base) -> "landed" | "pending" | "unresolved"` reading
  `read_pending()` + `read_answer("merge|{tid}|a{n}")` across attempts.

### Integration points / docs
- **`docs/DIRECTOR.md` §4/§7:** record that a `terminal(done)` on a **PR** ticket moves the
  board to `merging` (work done, integration pending), and the orchestrator finalizes
  →`done` when the merger lands — so "the orchestrator executes board transitions" now spans
  the terminal disposition **and** the merge-completion sweep (still orchestrator-owned; the
  merger remains board-free). The Director reads a `merging` ticket as "done work, awaiting land".

### Errors / edge cases
- **`merging` unconfigured** → Components 2/3 are inert → today's behavior exactly (R7).
- **No-PR `done`** → straight to `done`, never enters `merging` (R2) — planning/research/spec
  tickets unblock their children immediately, as before.
- **Abandon / human-escalated merge** → never observed as `merged` → parent stays `merging`,
  children stay blocked (R5); the existing abandon/human path surfaces it.
- **Re-queued merge** (`requeue_merge` → `merge|<tid>|a2`) → a pending request exists again →
  sweep keeps the parent in `merging` until that attempt lands.
- **Merger not running** → `merging` tickets never finalize → the DAG wedges. Merge-gating
  **presumes the serialized merger is running** (it is, in the real runtime); documented as an
  operating assumption.
- **Batch mode exits before a land** → the ticket stays `merging` until a subsequent run's
  sweep finalizes it (daemon is the steady-state mode; documented limitation, Open question).

## Non-goals (scope fence — YAGNI)

- **Stacked / nested branches (Direction B).** No cloning a child off the parent's PR branch,
  no branch-topology mirroring of the ticket DAG. We bet on `main` as the single integration
  point; B contradicts the board-ownership + serialized-merger model.
- **The merger writing the board (the rejected "who finalizes done" alternative).** Board
  writes stay in the orchestrator (stated principle); the merger keeps its board-free,
  queue-only contract.
- **Merge-aware eligibility consulting the queue (the rejected representation).** We represent
  merged-ness as a board state so eligibility/orphan-recovery/active-run-reconciliation stay
  pure board reads — no two-source eligibility, no separate abandoned-set.
- **Dashboard surfacing of `merging` tickets.** The board reflects `merging`; a dedicated
  dashboard panel/count is a later best-effort visibility add, not required for the eligibility
  fix.
- **Auto-provisioning a host's "Merging" workflow state.** The host configures it (self-host
  does); we only consume a configured state.

## Acceptance criteria

1. **R1:** with `director.states.merging` set, `resolve_states` returns a `merging` id;
   omitting it changes nothing (load + behavior identical to today).
2. **R2:** a unit test on `reconcile` shows a `done` disposition with a PR → `set_state(merging)`
   + a `merge|<tid>|a1` queued; a `done` disposition with no PR → `set_state(done)`; with
   `merging` unconfigured both go to `done`.
3. **R3/R5:** a test drives `merging` → (a) a queue with `merge_result=merged` → sweep moves
   the ticket to `done`; (b) a still-pending `merge|<tid>|a1` → stays `merging`; (c) an
   abandoned merge (no merged answer) → stays `merging`.
4. **R4:** an `eligible_tickets`/dispatch test shows a child blocked by a `merging` parent is
   not eligible, and becomes eligible once the parent is `done` — with `eligible_tickets`
   itself unchanged.
5. **R6:** the sweep run twice is a no-op; `merger.py` imports/holds no board.
6. **R7 + (behavioral):** the full gate is GREEN; an end-to-end mock run (parent with a PR →
   merger lands → next sweep → parent `done` → child dispatches) shows the child does **not**
   dispatch until the parent's merge lands.

## Decision log

- **D1 — gate eligibility on *merged*, by deferring the board `done` (Direction A).** Human
  pick over stacked-branches (B) and minimal-guard (C). Makes board-`done` mean
  merged-to-main, so the existing `done_types` gate is correct unchanged. (**human, 2026-06-19.**)
- **D2 — represent merged-but-not-done as an optional `merging` board state**, not a
  queue-consulting eligibility predicate. Keeps eligibility, orphan-recovery, and active-run
  reconciliation as pure board reads (no second source of truth, no separate abandoned-set);
  Symphony-aligned (it has a Merging state). (autonomous.)
- **D3 — the ORCHESTRATOR finalizes `merging`→`done`, not the merger.** Preserves the stated
  "orchestrator owns board writes" principle and keeps the merger board-free. Cost: completion
  is eventual (next tick) and daemon-centric; a batch run that exits before a land leaves the
  ticket `merging` until re-run (Open question). Alternative — the merger writes `done` on land
  (immediate, all-modes) — rejected: it violates board-write ownership and puts board
  credentials in a second process. (autonomous.)
- **D4 — opt-in via configuring `merging`.** Absent → byte-identical to today; merge-gating is
  active only where a host wires the state (self-host does). (autonomous.)
- **D5 — abandon leaves the parent `merging` (children stay blocked); the human owns the
  escape.** A permanently-unlanded parent must not unblock children onto a stale `main`; the
  abandon escalation surfaces the impact and the human re-targets or accepts. (autonomous.)

## Open questions

- **Batch-mode `merging` tickets** when the orchestrator exits before the merger lands —
  resolved in spirit (daemon is the steady-state mode; a re-run's sweep finalizes), but worth
  confirming from real use whether batch needs a join-on-merger step.
- **Dashboard `merging` surfacing** — whether/when to show `merging` tickets as a distinct
  section (deferred; the board is the truth).
