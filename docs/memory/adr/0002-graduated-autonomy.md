---
status: accepted
last_verified: 2026-06-17
owner: harness
type: adr
tags: [autonomy, director, worker, escalation]
description: Move the Director from per-turn judge to exception-handler — workers self-govern the routine, the human is woken only on genuine taste/risk.
---
# Graduated autonomy — human at the edges, autonomous in the middle

## Decision

We move the Director from a **per-turn judge** toward an **exception-handler**:
the worker self-governs the routine, and the Director (and through it, the human)
is woken **only** on the genuine taste/risk subset. We deliberately take
Symphony's autonomy bet on two of its four axes while **keeping our correctness
wins** on the other two:

| Axis | Symphony | Us today | This decision |
|---|---|---|---|
| human in the **middle** (per-turn) | none (unattended daemon) | Director judges *every* turn-end | **move toward Symphony** — wake the Director only on real escalation |
| worker **autonomy** | high (`approval_policy: never`) | low (per-turn deference) | **move toward Symphony** — more rope, bounded by the authority guardrail |
| who **writes the board** | agent writes lifecycle | orchestrator writes | **keep ours** — correctness, not control |
| who **merges** | agent self-merges (`land`) | serialized merger | **keep ours** — correctness, not control |

In one line: **human at the edges (board curation in, PR-approval out),
autonomous in the middle.** Realized as two **ordered** child slices (this is a
parent decomposition per [[0001-recursive-decomposition]]):

1. **Worker operating-protocol depth** (Symphony-parity gap #5) — *the
   precondition.* Spec:
   `docs/product-specs/2026-06-17-worker-operating-protocol.md`. Harvest
   `docs/symphony-original/WORKFLOW.md`'s stage-agnostic
   disciplines (single-workpad-as-source-of-truth, reproduction-first,
   acceptance-criteria mirroring, the **PR feedback sweep**, no-scope-creep,
   revert-proof-edits) into a shared worker-protocol preamble (sibling to
   `taxonomy.TERMINAL_CONTRACT`) + enriched per-stage templates, PR-feedback-sweep
   placed on the impl/rework path. **Do NOT port the file** — its lifecycle steps
   (worker moves the board, self-merges, never-asks-a-human) are welded to the two
   axes we reject; a line-by-line keep/adapt/reject triage is the spec's spine.
2. **Selective-escalation decider + its two companions.** Three pieces that
   cohere because each is about *what the human sees, and what the worker may do,
   when no longer judged every turn* (scope confirmed 2026-06-17):
   - **(2a) Selective-escalation decider** — graduate `director/decider.py` from
     the current *binary* (watched = judge every turn-end; `--autonomous` = judge
     nothing, no `turnReview` reaches the queue, `DIRECTOR.md §6`) into a **dial**:
     auto-continue routine turn-ends, route only the `DIRECTOR.md §2` taste/risk
     subset (`needs_human`, `attempt≥2` + destructive, `stuck` + force-past, merge
     taste-forks) to the Director/human.
   - **(2b) Board-side canonical progress comment** — Symphony's `## Codex Workpad`
     discipline, *adapted*: as the Director steps back, the human curating the
     daemon watches the **board**, not repo docs, so the worker maintains **one
     canonical** progress comment on the ticket (via the already-allowlisted
     `commentCreate`/`commentUpdate`) as a board-visible mirror of the repo-doc
     narrative — single, not fragmented. This is the slice-1 source-of-truth
     framing's natural completion: repo doc = the narrative's authoritative home,
     board comment = its human-facing mirror (NOT a competing second narrative).
   - **(2c) `issueUpdate` authority-ceiling decision** — the guardrail allowlists
     `issueUpdate` ("state transitions, labels, assignment"), but the architecture
     says the *orchestrator* owns lifecycle-state writes; today only a soft prompt
     convention keeps the worker off it. Raising worker autonomy must mean *more
     self-governance / less Director gating*, **not** the worker writing lifecycle
     state (which would race the daemon claim/reconcile). Decide deliberately:
     tighten `issueUpdate` out of `DEFAULT_MUTATION_ALLOWLIST`, or split
     forward-only moves from terminal moves — so the convention becomes a ceiling.
   Likely also couples a worker-authority posture raise toward `approval_policy:
   never`.

## Why

- **The daemon (gaps #1–#3, shipped) made us an unattended service; the per-turn
  watched-Director is the remaining human-attention bottleneck that contradicts
  "unattended."** Closing it is the natural maturation of the daemon, not a new
  direction bolted on.
- **The autonomy infrastructure already exists** — `--autonomous` proves the
  worker self-governs end-to-end; the authority guardrail (`worker/authority.py`)
  bounds its board writes; the serialized merger guards the output edge. The only
  missing setting is the *middle*: escalation today is all-or-nothing. So this is
  *graduating a binary into a dial*, not building autonomy from scratch.
- **Even Symphony keeps humans at the edges** — `Human Review` + `Merging`-on-human-approval
  (`WORKFLOW.md` Step 3). "Remove human-in-loop as much as possible" realistically
  means *remove from the middle, keep at the edges* — and that target is fully
  compatible with keeping our merger and orchestrator board-ownership.
- **The two kept axes are correctness, not human-in-loop artifacts.** Self-merge
  reintroduces concurrent-`main` thrash (Symphony absorbs it *reactively* via the
  `land` retry-loop; our merger avoids it *structurally* — strictly better under
  concurrency). Worker-writes-the-board puts a **second writer** beside the
  daemon's claim/reconcile machinery shipped in stage 1 — the literal clone would
  *partially unwind* that work to stay race-free. We gain nothing but fidelity by
  cloning either.
- **Sequencing is forced, not arbitrary:** auto-continue is only *safe* once the
  worker reliably does reproduction-first / workpad-as-truth / PR-feedback-sweep.
  Gap #5 earns the trust the decider then spends. Slice 1 must precede slice 2.

## Consequences

- **Supersedes the strategic framing** in
  `docs/design-docs/symphony-parity-gap.md`: "a different bet, neither ahead" and
  "gap #5 = output-quality lever" are now narrowed — we are deliberately taking the
  autonomy bet on the middle/worker-autonomy axes, and gap #5 is reclassified as
  *the worker-autonomy enabler*. That doc cross-links here; the per-axis verdicts
  above are the authority.
- **Out of scope (explicit rejects):** adopting `WORKFLOW.md` as a file; moving
  board lifecycle writes to the worker; worker self-merge / `land`-in-worker. The
  serialized merger stays exactly as-is (rebase → integration gate → squash-merge,
  one PR at a time, escalates to the Director — `DIRECTOR.md §7`; human-confirmed
  2026-06-17).
- Each slice runs the full `product-design → execplan → completion-gate` flow and
  links this ADR in its Context. Roadmap/status is the derived view of the two
  slice tags (per [[0001-recursive-decomposition]]), not a separate tracker.
- A live risk to watch in slice 2: the §2 taste predicate must be conservative
  (fail-safe = escalate). A decider that under-escalates ships a wrong autonomous
  taste call un-reviewed — costlier than one extra escalation. The richer worker
  protocol (slice 1) is what keeps the auto-continue lane's *correctness* bar high
  enough that the residual escalations really are only taste.
