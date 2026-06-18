---
status: active
last_verified: 2026-06-17
owner: harness
type: product-spec
tags: [director, autonomy, principles, worker, board]
description: Splits the mode bit into Director-presence and human-presence axes so autonomous rebinds to human-absence, adds a PRINCIPLES.md decision-taste layer and a lights-out park contract, has workers keep one canonical progress comment, and removes issueUpdate from the worker allowlist.
---
# Lights-out Director — Core Principle layer, park contract, board comment, issueUpdate ceiling

Slice 2 of [ADR 0002](../memory/adr/0002-graduated-autonomy.md), built on the
reframe in [ADR 0003](../memory/adr/0003-lights-out-director.md). This spec owns the
**design**; the ExecPlan that follows owns the **build**.

## Context

- **Decisions (own the shape):** [ADR 0003](../memory/adr/0003-lights-out-director.md)
  (the two-axis mode model, the `PRINCIPLES.md` layer, the taste-vs-mechanical
  decision procedure, the daemon-as-separate-track, the no-headless reconciliation)
  and its parent [ADR 0002](../memory/adr/0002-graduated-autonomy.md) (human at the
  edges, autonomous in the middle; the 2a/2b/2c bundle).
- **Precondition (done):** slice 1,
  `2026-06-17-worker-operating-protocol.md` — the richer `WORKER_PROTOCOL`
  preamble in `director/taxonomy.py` (`frame_first_turn`) that earns the trust this
  slice spends. 2b extends that same preamble.
- **The decision seam (unchanged by this slice):** `director/decider.py`
  `make_queue_decider` posts each turn-end to the queue and blocks for *whoever is
  the Director*; `director/run.py:225` calls `decide(ctx)`; `director_min.answer_turn`
  is how the Director writes a disposition back. Lights-out reuses this seam verbatim
  — only *who answers* changes (a Daemonized Claude Code instead of a human-attended
  session), and that runtime is out of scope here.
- **The escalate path (the park foundation):** `director/orchestrator.py:187` —
  `kind == "escalate"` already comments on the board (`🙙 escalated…`) and keeps the
  ticket **visible** (`summarize("escalated", "started")` — state stays In Progress,
  human acts async). Park semantics already exist; R4 builds on them.
- **The authority guardrail (2c target):** `director/worker/authority.py:31`
  `DEFAULT_MUTATION_ALLOWLIST` contains `issueUpdate`; `director/workspace_skills/
  linear/SKILL.md:242` actively instructs the worker to call `issueUpdate` for state
  transitions. The orchestrator's *own* state writes go through `director/board/
  linear.py:56` (`update_issue_state`), which is unaffected by the worker allowlist.
- **Not this slice (separate track):** the Daemonized Claude Code runtime, and any
  change to the worker's own judgment surface (`report_outcome` stays as-is).

## Problem

Today the Director is a per-turn judge that requires a *human-attended* session:
`watched` routes every turn-end to a human, `--autonomous` routes nothing to a weak
pure-code decider (`autonomous_decide`) that can only trust-and-continue. There is no
mode where a capable judge runs **without a human present** — so an unattended daemon
run either floods a human with every turn-end or flies blind on pure code. Three
things are missing to close that gap:

1. **No place for the human's taste to live** where a Director can consult it. The
   human's decision principles exist only in their head, so the only options at a
   fork are "ask the human" or "guess." There is no `PRINCIPLES.md`.
2. **No durable, distinguishable "awaiting human" signal** for the rare fork the
   Director genuinely cannot resolve — escalate comments exist but a *taste-park* is
   not separable from a generic escalation, and there is no recorded rationale trail
   for the calls the Director *does* make autonomously.
3. **Two board-write discipline gaps** that matter precisely when the human steps
   back: the worker has no instruction to keep a *single* board-visible progress
   narrative (it fragments across comments), and the worker *can* still write
   lifecycle state (`issueUpdate`) — a second writer racing the orchestrator.

## Requirements

Each is independently verifiable by a human.

- **R1 — Mode model is the two-axis model, documented; no new orchestrator flag.**
  `DIRECTOR.md` documents three modes: **attended** (watched orchestrator + human
  answers the queue), **lights-out** (watched orchestrator + a Daemonized Claude Code
  answers the queue — *no new flag*; it is the watched queue path with a daemon on the
  answering end), and **no-agent** (`--autonomous` → `autonomous_decide`, reframed as
  the `--mock`/CI/truly-detached niche). Verifiable: `DIRECTOR.md §6` (and the
  `--autonomous` help text in `orchestrator.py`/`merger.py`) describe these three and
  state that lights-out needs no orchestrator change.

- **R2 — `docs/PRINCIPLES.md` exists, structured, with a seed, and the Director is
  told to consult it.** The file holds the human's decision-taste as numbered
  principles (each: a decision-guiding statement, a *why*, and where useful a worked
  example), seeded by Claude from observed patterns. `DIRECTOR.md` names it as the
  source consulted *before* escalating a taste fork. Verifiable: the file exists with
  ≥1 principle in the specified shape and is registered in the docs tree;
  `DIRECTOR.md` references it.

- **R3 — `DIRECTOR.md` encodes the lights-out decision procedure, and §2 is
  revised.** The manual contains the procedure: hard-blocker → park; else
  mechanical → decide+log; else taste → consult `PRINCIPLES.md` → (confident →
  decide+log+cite; ambiguous → park). `DIRECTOR.md §2`'s "the human owns
  irreversible/outward-facing actions even if allowlisted" is revised to "the human
  owns the *taste* in those actions, not the *act*; the Director performs mechanical
  outward-facing actions within the guardrails," with the hard safety floor named as
  the guardrail architecture (sandbox / authority allowlist / serialized merger).
  Verifiable: both edits present and internally consistent with R2/R4.

- **R4 — A parked fork is durable, distinguishable, and drainable.** When the Director
  parks ("awaiting human"), the result is (a) a board comment that marks it as
  *awaiting a human taste/blocker decision* (distinct wording from a generic
  escalation), (b) the ticket stays visible (In Progress), and (c) it is surfaced to
  the async human (PushNotification) and enumerable from `director.status` /the
  dashboard. The human drains it by supplying a directive that resumes the ticket —
  reusing the existing turn-end answer / `requeue`-style path, not a new transport.
  Verifiable: a turn-end that the procedure routes to "park" produces the distinct
  comment + stays In Progress + appears in the status view; a human directive resumes
  it.

- **R5 — Every autonomous taste call leaves an audit trail.** When the Director
  resolves a taste fork via `PRINCIPLES.md` (decide+log), its disposition carries the
  decision *and the principle it relied on*; this is persisted in the queue answer
  record (existing) and, for a terminal disposition, rendered into the board comment
  by `reconcile`. Verifiable: a decide-via-principle disposition records
  `{decision, principle-citation}` durably where an async human can review it.

- **R6 (2b) — The worker maintains ONE canonical board progress comment.** The
  `WORKER_PROTOCOL` preamble instructs the worker to keep a single progress comment on
  the ticket, identified by a stable marker, created once (`commentCreate`) and
  updated thereafter (`commentUpdate`) — including finding-and-updating it on a fresh
  attempt rather than creating a second. It mirrors the repo-doc narrative (repo doc =
  authoritative; board comment = its human-facing mirror), never a competing second
  narrative. Verifiable: the preamble contains the discipline + the marker convention;
  a `taxonomy` test asserts the new text; conceptually a multi-turn/retry run yields
  one comment, updated.

- **R7 (2c) — The worker can no longer write lifecycle state; the orchestrator's
  state writes are unaffected.** `issueUpdate` is removed from
  `DEFAULT_MUTATION_ALLOWLIST`, and `workspace_skills/linear/SKILL.md` no longer
  instructs the worker to transition state (it points the worker at `report_outcome`
  for terminal proposals + `commentCreate`/`Update` for progress). The worker keeps
  `issueCreate` / `issueRelationCreate` / `commentCreate` / `commentUpdate`. The
  orchestrator's `board.update_issue_state` (which itself uses an `issueUpdate`
  mutation, outside the worker allowlist) still works. Verifiable: an authority test
  asserts a worker `issueUpdate` mutation is now blocked; the SKILL.md edit is present;
  orchestrator state-transition tests stay green.

## Design

### Mode model (R1) — realized by *who answers*, not a flag

The orchestrator already supports "post turn-ends to the queue; something answers."
Lights-out is therefore **not a new orchestrator mode** — it is the existing watched
queue path with a Daemonized Claude Code on the answering end. The only code-visible
artifact is documentation + reframed help text:

- `autonomous_decide` / `--autonomous` is documented as the **no-agent** path
  (`--mock`, CI, truly-detached), matching `DIRECTOR.md §5`'s existing "only for the
  truly-detached case (no session at all)."
- `make_queue_decider` is the path for **both** attended and lights-out — it routes to
  "whoever is the Director." No change to `decider.py` behavior; at most a docstring
  note that the answerer may be a daemon.

This keeps the slice's code surface tiny and puts the autonomy where ADR 0003 says it
belongs: in the Director agent's reasoning, not a code predicate.

### `docs/PRINCIPLES.md` (R2) — structure + seed

**Placement:** top-level `docs/PRINCIPLES.md`, sibling to `DIRECTOR.md` and
`PRODUCT_SENSE.md` (the `docs-tree` skill confirms placement + frontmatter at build
time). Registered where top-level operating docs are indexed.

**Structure:** frontmatter (`status/last_verified/owner`) + a short preamble stating
its purpose (the human's externalized decision-taste, consulted by the Director to
*simulate the human's call* at a fork; refined by the human and by the audit loop) +
numbered principles. Each principle:

```
### P<n> — <one-line decision-guiding statement>
**Why:** <the reasoning, so the Director can extend it to unseen forks>
**Applied:** <optional worked example: at fork X, this resolves to Y>
```

**Seed content** (Claude-authored from observed patterns — CLAUDE.md guidelines, this
repo's decisions, this human's autonomy bias; the human edits later):

- **P1 — Default to action on a reasonable next step; do not pause for confirmation.**
  *Why:* human attention is the scarce resource; a reasonable path taken now beats a
  confirmed path taken later. *Applied:* "should I proceed with the obvious next step?"
  → proceed, note the choice.
- **P2 — Mechanical/technical calls are yours; the human owns taste.** *Why:* the
  Director usually knows better on technical/mechanical matters; reserve human time
  for genuine taste/product/risk forks and hard blockers (missing auth/resource).
  *Applied:* a merge with a mechanical conflict → resolve it; a merge where "which
  version is canonical" is a product call → consult principles, else park.
- **P3 — Prefer the simplest solution that fully captures the real complexity.** *Why:*
  YAGNI on speculative scope, but never under-model genuine nuance/detail that matters.
  *Applied:* at "minimal vs general" forks, take minimal-that-covers-the-actual-case.
- **P4 — Prefer reversible, fix-forward moves over ceremony.** *Why:* short-lived
  changes + mechanical gates beat human-approval steps; reversibility lowers the bar to
  act. *Applied:* ship a reversible cut now rather than park for sign-off.
- **P5 — Correctness over control.** *Why:* keep a design choice because it is more
  correct/robust under concurrency, not because it preserves human/operator control
  (the ADR 0002 kept-axes rationale). *Applied:* prefer the single-writer / serialized
  design even when a looser one would "feel" more flexible.
- **P6 — Right division of labor; don't overload one actor.** *Why:* push each piece of
  work to the actor best placed for it (worker self-governs + proposes; orchestrator
  owns state; Director adjudicates). *Applied:* never have the Director redo what the
  worker can self-resolve.
- **P7 — Trace the call to the project's ultimate goal.** *Why:* the harness exists to
  do big-software development with minimum human-in-loop; resolve a fork toward
  whatever advances that, all else equal.
- **P8 — When you genuinely cannot tell whether a fork is taste, park (fail-safe) and
  log your reasoning.** *Why:* a wrong autonomous taste call costs more than one
  escalation; logging lets the human teach you so the parked set shrinks over time.

### `DIRECTOR.md` lights-out section + §2 revision (R3)

Add a section (e.g. `§13 Running lights-out`) that states: lights-out = a daemon
answering the queue with the **same** taste-vs-handle judgment (§2), augmented by the
decision procedure (the ADR 0003 tree, reproduced), plus the rule "consult
`PRINCIPLES.md` before escalating a taste fork; park only when it is silent/ambiguous
or the blocker is hard." Revise §2's irreversible/outward-facing clause per R3. Note
the existing §9 run-report and §7 merge-escalation paths already embody
"Director resolves mechanical, human owns taste" — lights-out generalizes that, it does
not contradict it.

### Park contract (R4) — reuse escalate, add a distinguishable marker

A park is a turn-end **`escalate`** disposition (it already stays-visible + comments +
human-acts-async). The additions are minimal:

- **Distinct wording:** the Director's `escalate` `reason` marks it as *awaiting a
  human taste/blocker decision* (vs a generic escalation), and `reconcile`'s comment
  renders that wording so the board shows it as parked-for-human. (Comment text only —
  no board-schema change, no new state.)
- **Surfacing + enumeration:** the daemon Director sends a `PushNotification` (DIRECTOR
  §5.4); `director.status`/the dashboard already list escalated-and-still-`started`
  tickets, which *is* the parked set. No new queue kind unless evaluation shows the
  comment+status surface is insufficient (kept as a deliberate YAGNI line; if added,
  it mirrors the merger's `requeue` give-directive-and-resume pattern).
- **Drain:** the human supplies a directive; the Director resumes the ticket via the
  ordinary turn-end answer path (a `reply` on the next dispatch) — the same mechanism
  attended mode already uses. No new transport.

### Audit trail (R5) — rationale rides the disposition

The Director includes its reasoning + principle citation in the disposition it writes
via `answer_turn` (already persisted in the queue answer record). For a **terminal**
taste call, `reconcile` renders the citation into the board comment it already writes
(`orchestrator.py:164` done / `:173` blocked) — so the board carries the autonomous
rationale where an async human reviews it. New = the *discipline* (DIRECTOR.md) +
ensuring the comment rendering includes a disposition-supplied note. No new store.

### 2b — single canonical progress comment (R6)

Extend the `WORKER_PROTOCOL` preamble in `director/taxonomy.py` (the slice-1 seam) with
a progress-comment discipline: maintain exactly one comment on the ticket, led by a
**stable marker** (e.g. a leading `## 🤖 Worker Progress` header or an HTML-comment
sentinel the worker can grep its own prior comment by); `commentCreate` it on first
write, `commentUpdate` it thereafter; on a fresh attempt, read the ticket's comments,
find the marked one, and update it rather than create a second. It mirrors — does not
replace — the repo-doc narrative. Worker-prompt text only; covered by a `taxonomy` test
asserting the new instruction. (Reads are unrestricted; `commentCreate`/`Update` are
already allowlisted — no guardrail change.)

### 2c — issueUpdate ceiling (R7)

- `director/worker/authority.py`: remove `"issueUpdate"` from
  `DEFAULT_MUTATION_ALLOWLIST` (and its comment). Re-add narrowly only if a real
  non-state worker need (e.g. relabeling an existing ticket) ever appears — YAGNI for
  now (labels at creation go through `issueCreate`).
- `director/workspace_skills/linear/SKILL.md`: remove the "use `issueUpdate` to
  transition state" instruction; redirect the worker to `report_outcome` (propose
  terminal state) and `commentCreate`/`Update` (progress). Keep read/query guidance.
- Tests: a new/extended `test_director_authority` assertion that a worker `issueUpdate`
  mutation is now refused; confirm `test_director_linear`/orchestrator state-transition
  tests (the orchestrator's own `update_issue_state`) remain green — they exercise the
  board client, not the worker allowlist.

### Error / edge cases

- **Daemon answers slow / not running:** the existing `make_queue_decider` timeout
  surfaces a no-answer as `escalate` (`decider.py:79`) — a parked item, not a
  fabricated continue. Lights-out inherits that fail-safe unchanged.
- **PRINCIPLES.md absent/empty:** the Director simply has nothing to infer from →
  every taste fork parks (fail-safe). Lights-out degrades to "park all taste," never to
  "guess." So the seed is a convenience, not a correctness dependency.
- **Worker progress comment id lost mid-run:** the stable-marker find-or-create makes
  the comment self-healing — worst case one duplicate if the marker is missing, caught
  by the next update.
- **issueUpdate removal hitting a hidden dependency:** mitigated by R7's test that the
  orchestrator's state writes (separate path) stay green, and by the grep evidence that
  no worker flow other than the (now-fixed) SKILL.md instructs `issueUpdate`.

## Non-goals

- **The Daemonized Claude Code runtime.** Separate, in-development track. This slice
  builds the contracts it will consume and is validated without it.
- **Live end-to-end lights-out validation** (needs the daemon) and the **continuous
  production audit-learning loop** (the mechanism is specified; the loop runs once the
  daemon is live).
- **Changing the worker's judgment surface.** `report_outcome` (done/blocked/
  needs_human) stays exactly as-is — it is the worker's own valve; removing it would
  shift load onto the Director (ADR 0003 §5).
- **`approval_policy: never` posture raise.** Out of scope — it removes Codex's
  fail-closed reviewer while the T11 exfil residual is still deferred (SECURITY.md);
  not needed for the dial.
- **A new "lights-out" orchestrator flag / mode** (R1: realized by who answers).
- **A new park queue-kind / board state** unless evaluation proves comment+status
  insufficient (deliberate YAGNI line).
- **Re-deriving slice 1** (the `WORKER_PROTOCOL` preamble) — 2b only extends it.

## Acceptance criteria

1. `docs/PRINCIPLES.md` exists with the specified structure and the ≥8-principle seed,
   registered in the docs tree; `DIRECTOR.md` names it as the consult-before-escalate
   source (R2).
2. `DIRECTOR.md` contains the lights-out decision procedure and the revised §2
   outward-facing clause, consistent with the guardrail-as-floor framing (R1, R3).
3. The park contract is demonstrable: a procedure-routed park yields the distinct
   "awaiting human" board comment, the ticket stays In Progress, and it appears in
   `director.status`; a human directive resumes it (R4). Autonomous taste calls carry a
   principle citation in the persisted disposition/comment (R5).
4. `python3 -m unittest discover -s tests -p 'test_director_taxonomy*'` shows a new
   assertion for the 2b progress-comment discipline that fails on the base commit and
   passes at HEAD (R6).
5. `test_director_authority` asserts a worker `issueUpdate` mutation is now refused; the
   `workspace_skills/linear/SKILL.md` state-transition instruction is gone;
   orchestrator/board state-transition tests stay green (R7).
6. The full gate `python3 plugin/scripts/check.py` is GREEN.
7. The diff touches only: `docs/PRINCIPLES.md`, `docs/DIRECTOR.md`,
   `director/taxonomy.py`, `director/worker/authority.py`,
   `director/workspace_skills/linear/SKILL.md`, the orchestrator comment-rendering for
   the audit note, the relevant tests, and docs indexes — `report_outcome`,
   `decider.py` behavior, board-state ownership, and `merger.py` are unchanged in
   substance (R1 mode model is doc/help-text only).
