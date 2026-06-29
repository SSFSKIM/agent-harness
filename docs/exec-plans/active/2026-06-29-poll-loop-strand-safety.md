---
status: active
last_verified: 2026-06-29
owner: harness
type: exec-plan
description: Close the two poll-loop gaps the worker-behavior review deferred — gap #3 (the always-on daemon never escalates a permanent strand; a ticket blocked behind a parked parent sits silent forever) and gap #2 (a ticket the orchestrator PARKED in `started` — an escalate, or a blocked with no configured blocked-state — is re-readied + re-run by startup orphan-reattach on a daemon restart, which can duplicate worker-filed children).
base_commit: de1955552fc2d6cb8cdd5407887008ca32cf75dd
review_level: standard
---
# Poll-loop strand safety — daemon strand-escalation (gap #3) + restart-safe parking (gap #2)

## Goal

After this plan the always-on daemon stops two silent failure modes the
worker-behavior review surfaced (tech-debt-tracker top row, gaps #2/#3):

1. **Strand-age escalation (gap #3).** When a ticket stays *blocked with no eligible
   progress* across `strand_escalation_polls` consecutive idle daemon polls, the daemon
   escalates it **once** — a board comment naming the strand + a distinct `stranded` flag
   on its `stuck` status entry — instead of leaving it to sit silent in the idle
   heartbeat forever. The streak resets the moment the ticket makes progress (leaves the
   blocked set). A `0`/`None` threshold disables it.
2. **Restart-safe parking (gap #2).** A ticket the orchestrator *parked* in `started` (an
   `escalate`, or a `blocked` left in `started` because no `blocked` board-state is
   configured) is **not** re-readied + re-run by startup orphan-reattach on a daemon
   restart. Parked tickets are recorded in a durable set; `_startup_recovery` skips them
   (they are parked-for-human, not crash-orphans), so a restart no longer re-runs a parked
   worker — closing the duplicate-children path. A genuine crash-orphan is still recovered.

Definition of done: both behaviors ship with unit tests, the gate is GREEN, and the
always-on + standard review personas (incl. review-reliability — this is recovery code)
return SATISFIED.

## Context

- Originating review + the two gaps: [tech-debt-tracker](../tech-debt-tracker.md) top row
  ("Worker ticket-issuance"), gaps (2) and (3); gap (1) was closed by
  [reconcile-spawned-ticket-validation](../completed/2026-06-29-reconcile-spawned-ticket-validation.md),
  whose completion gate *sharpened* gap #2 (its `blocked`→escalate downgrade is a new entry
  into the restart re-run path) and proposed the two RELIABILITY rules this plan acts on.
- The daemon: `orchestrator.run_forever` (`director/orchestrator.py:950`). Each idle tick it
  computes the `blocked` set (pending-but-ineligible) and writes it as *status* —
  `state.status.stuck(_stuck_report(blocked, done_set) if not state.futures else [])`
  (`:1106`) — but never escalates a persistent strand (gap #3). `_startup_recovery` (b)
  (`:895-902`) re-readies **every** `started` ticket on entry (gap #2 root).
- Why parked tickets sit in `started`: `reconcile` (`director/orchestrator.py`) leaves an
  `escalate` in `started` (`:325-327`, "stays visible; human acts async"), and a `blocked`
  in `started` when `states["blocked"]` is unconfigured (the default — `config.py`
  `blocked: None`); the `blocked`→escalate downgrade (`:297-305`) likewise stays `started`.
  A `blocked` moved to a *configured* `blocked` state is already safe (orphan-reattach only
  reads `started`).
- Durable run-state: the queue package (`director/queue/__init__.py`) is the atomic
  temp-then-`os.replace` store (R9) the parked-set mirrors. `status.json`'s `recent[]` is a
  **bounded tail** (`status.py` `RECENT_MAX`), so it can NOT serve as the parked record — a
  dedicated durable set is required.
- Total-function / best-effort discipline: every new board read/write and the parked-set IO
  follow the `_startup_recovery`/`reconcile` fail-soft pattern (log + proceed, never crash
  the daemon; RELIABILITY R12). Fail-soft DIRECTION for the parked-set: a read failure
  degrades to *today's behavior* (re-ready all) — never strands a real orphan.
- Out of scope: the operator-doc note (DIRECTOR.md/runbook: "blocked/escalate = needs manual
  re-ready") is a doc-gardener follow-up, tracked separately; this plan is the code fix.

## Approach (self-generated alternatives)

**Gap #3 — strand escalation surface:**
- A (chosen): a board **comment** + a `stranded` flag on the `stuck` status entry, fired
  once when the streak crosses the threshold. Board-as-truth (the human curates the board),
  visible on the dashboard, no new queue kind. Tradeoff: not a push (the human polls the
  board/dashboard), but that matches the lights-out "human at the edges" model.
- B: a new human-bound **queue kind** (`strandReview`) that `director.watch`/`notify`
  surface. Rejected for v1: invents a new request/answer kind + UI for a signal the board
  comment + dashboard already carry; revisit if a push is wanted.

**Gap #2 — distinguishing a parked ticket from a crash-orphan:**
- A (chosen): a **durable parked-set** (a small atomic file in the queue store):
  `reconcile` records a tid when it parks in `started`; `_startup_recovery` skips re-readying
  any `started` tid in the set (and GCs the set to `parked ∩ started`); the set is cleared
  for a tid on re-claim. Config-light (no new board states), fail-soft (missing set →
  re-ready all = today), board-mutation-free.
- B: a board **`parked` label** the orchestrator sets on a park and removes on re-claim;
  orphan-reattach skips labelled `started` tickets. More board-as-truth + human-visible, but
  adds label CRUD + two new board mutations + a find-or-create; heavier. Noted as the future
  upgrade if the park should be human-visible on the board.
- C: a dedicated **parked board-state** orphan-reattach excludes. Cleanest in principle but
  forces every host to configure another workflow state (config burden); rejected.
- **Chosen: A** — minimal, fail-soft toward the safe direction, no host-config burden, no
  new board write surface in the recovery path.

## Assumptions & open questions (self-interrogation)

- Assumption: a tid in the parked-set is genuinely parked (not running), so skipping its
  orphan-reattach is correct. Holds because a parked ticket only re-runs via a re-claim,
  which clears its parked entry first — so a tid in the set is never a live worker. — what
  breaks if wrong: a real orphan is skipped → stuck in `started`. Mitigated by clear-on-claim
  + the startup GC (`parked ∩ started`) and is fail-soft (the human can always re-ready).
- Assumption: `strand_escalation_polls` counts *idle* daemon polls, which back off
  exponentially (`_idle_wait_s`), so it is a fuzzy wall-clock measure. Acceptable — the
  escalation is a "this has been stuck a while, look at it" nudge, not a precise SLA; the
  default (6) + the backoff are documented on the knob. — what breaks if wrong: escalates a
  bit early/late; harmless (idempotent single comment).
- Open: escalate a strand only when *fully idle* (no workers running), or also under a
  saturated pool? → resolved: only when idle (the daemon already computes the `blocked` set
  only when idle / `not state.futures`; a strand under active work may clear when a slot
  frees, so "idle + still blocked" is the real strand signal). Matches the existing
  stuck-as-status gate (`:1106`).
- Open: which parks get recorded? → resolved: exactly the dispositions that leave the ticket
  in `started` — `escalate` (kind), the `blocked`→escalate downgrade, and a `blocked` whose
  `final_state` is `started` (no configured blocked-state). A `blocked` moved to a configured
  `blocked` state (final_state `blocked`) is already orphan-safe and is NOT recorded.

## Milestones

- **M1 — strand-age escalation (gap #3).** In `run_forever`, carry a `strand_streak:
  dict[tid,int]` across ticks. Where the idle stuck set is written (`orchestrator.py:1106`):
  for each tid in the current blocked/stuck set bump its streak; for tids no longer stuck,
  drop their streak (progress resets it); when a tid's streak first reaches
  `strand_escalation_polls` (new `config.DEFAULTS` knob, default 6; `0`/`None` disables),
  comment once on the ticket (`🚷 stranded — blocked N idle polls with no eligible progress;
  needs human`) and mark that tid's `stuck` entry `stranded: true` (+ `polls`). Fail-soft (a
  comment error logs, never crashes the tick). At the end: a daemon that idles with a
  permanently-blocked ticket emits exactly one strand comment at the threshold and flags the
  status; a ticket that progresses before the threshold never escalates. Run
  `python3 -m unittest discover -s tests`; expect new `run_forever` strand tests green
  (escalates once at threshold; resets on progress; disabled at 0; no double-comment).
- **M2 — restart-safe parking (gap #2).** Add `append_parked(tid)` / `read_parked()` /
  `clear_parked(tid)` / `gc_parked(live_started_ids)` to `director.queue` (atomic, mirroring
  `append_request`). In `reconcile`, after a park that leaves the ticket in `started`
  (escalate kind; `blocked`→escalate downgrade; `blocked` with `final_state=="started"`),
  call `append_parked(tid, base=queue_base)` (best-effort; skipped when `queue_base` is
  None). In `_startup_recovery` (b): read the parked-set, skip re-readying any `started`
  ticket whose tid is in it, and rewrite the set to `parked ∩ {started tids}` (GC the rest).
  In `state.claim_and_submit` (or the daemon's claim path), `clear_parked(tid)` on a
  successful re-claim. Fail-soft: a parked-set read error → re-ready all (today's behavior).
  At the end: a parked `started` ticket survives a daemon restart un-re-run (still `started`,
  for the human); a genuine crash-orphan (in `started`, not parked) is still re-readied; a
  re-claimed ticket is cleared from the set so a later crash recovers it. Run the suite;
  expect new `_startup_recovery` + queue tests green: (a) parked ticket NOT re-readied;
  (b) non-parked orphan IS re-readied; (c) parked-set GC drops a tid no longer in `started`;
  (d) reconcile records a park for escalate / blocked-in-started, NOT for blocked-in-a-
  configured-state; (e) read failure → re-ready all (fail-soft).

## Progress log
- [ ] (2026-06-29) Plan created; base_commit recorded; gate + commit pending.

## Surprises & discoveries

## Decision log
- 2026-06-29: gap #3 surface = board comment + stuck-status flag (approach A), not a new
  queue kind — board-as-truth, no new request/answer machinery.
- 2026-06-29: gap #2 mechanism = durable parked-set (approach A), not a board label (B) or a
  dedicated parked state (C) — config-light, fail-soft, board-mutation-free in the recovery
  path. The clear-on-reclaim + startup `parked ∩ started` GC keep the set honest.
- 2026-06-29: only dispositions that leave a ticket in `started` are recorded as parked; a
  `blocked` moved to a configured `blocked` state is already orphan-safe.

## Feedback (from completion gate)

## Outcomes & retrospective
