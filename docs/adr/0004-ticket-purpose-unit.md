---
status: accepted
last_verified: 2026-06-25
owner: harness
type: adr
tags: [taxonomy, ticket, decomposition, worker, methodology]
description: A ticket is a purpose/feature unit that carries the whole research→spec→plan→exec→QA pipeline within it; a worker issues a new ticket only on a genuine size split or surfaced deferred work, and every issued ticket is self-contained.
---
# Ticket = purpose unit — pipeline within, decompose only on size or surfaced work

## Decision

A ticket is a **purpose (feature) unit, not an action (stage) unit.** The default
worker walks the *entire* methodology pipeline inside one ticket — clarify →
(research if needed) → product-design spec → ExecPlan → implementation → QA → PR
— and closes it. The dev-stage `type` label says only *where the work starts*, not
"do this one stage, then hand off to a child."

A worker issues a **new** ticket on exactly two triggers — everything else stays in
the current ticket:

1. **Genuine size.** When, at the brainstorm/spec stage, the work splits into
   independently shippable sub-projects/slices (each its own `spec → ExecPlan`
   cycle), file one child ticket per piece, `blocked_by` this one. This is
   [[0001-recursive-decomposition]] applied at run-time: the spec tree (design-time)
   and the ticket DAG (run-time) are the same tree.
2. **Surfaced deferred work.** When work you choose *not* to do in this ticket
   surfaces — whether out-of-scope, or **in-scope** tech debt / additional
   production tests / hardening whose inline fix would break momentum — file a
   follow-up ticket rather than expanding the current scope or losing the thread.

Every ticket a worker issues, under either trigger, is **self-contained**:
provenance (a link to the parent ticket and to the source doc — spec/design/research
— it derives from), a clear title, a description of the work, and acceptance
criteria. A fresh-context worker assigned that ticket must be able to initiate its
context exploration and the work from the ticket alone.

This **revises** the dev-stage-taxonomy decisions D-18 (full per-stage taxonomy
first) and D-20 (worker-driven *per-stage* decomposition as the default): inter-stage
decomposition is no longer the routine hand-off but the **exception**, reserved for
the two triggers above.

## Why

- **It is already the law one layer down.** [[0001-recursive-decomposition]] and
  `docs/PLANS.md` "Scope check" define the unit as one `spec → ExecPlan` cycle and
  split only when work "spans independently shippable subsystems," realized as the
  ticket DAG. `product-design/SKILL.md` and `execplan/SKILL.md` say the same. The
  taxonomy templates simply drifted from it.
- **The drift is concrete and asymmetric.** `director/taxonomy.py:_IMPL_TEMPLATE`
  already obeys the rule — "split off impl children *only if the work is too large
  for one plan*." But `_SPEC_TEMPLATE` unconditionally says "*Then create impl child
  tickets for the build*," forcing a stage hand-off even for a one-unit feature. That
  mandatory spec→impl split is the action-unit decomposition this ADR removes.
- **The worker protocol was consumer-complete but producer-thin.** Every discipline
  that makes a ticket actionable — acceptance-mirroring, reproduction-first — is
  specified for the worker *receiving* a ticket; the worker *creating* a downstream
  ticket was told only "label it, blockedBy it." In a decomposition pipeline the
  consumer of ticket N is the producer of ticket N+1, so producer-thinness lets
  self-containedness degrade each generation. The self-contained-issuance contract
  closes that loop. (Symphony's `WORKFLOW.md` already requires a follow-up issue to
  carry "clear title, description, and acceptance criteria"; we generalize it to all
  worker-issued tickets — the one Symphony discipline our gap-#5 harvest left as
  label+link only.)
- **Run-time fan-out already has an owner.** The daemon + ticket DAG sequence many
  child work-units via `blocked_by` eligibility. Per-stage child tickets duplicated
  that machinery for no gain while fragmenting one feature's narrative across several
  tickets — the opposite of the single-source-of-truth discipline (gap #5,
  [[0002-graduated-autonomy]]).

## Consequences

- **Implemented by one ExecPlan** (worker-protocol / taxonomy prompt text — single
  subsystem, no product-spec needed per `docs/PLANS.md` entry decision):
  - `_SPEC_TEMPLATE` (and the `_DESIGN_TEMPLATE` hand-off) continue forward through
    the pipeline in the same ticket, creating children only on the genuine-size
    trigger — mirroring `_IMPL_TEMPLATE`'s existing conditional.
  - `_PLANNING_TEMPLATE` decomposes a large goal by **independently-shippable
    sub-project** (trigger #1 itself), not by per-stage child — otherwise it would
    contradict the protocol's "do not split by stage." (Caught in review: the first
    cut realigned only spec/design and left planning splitting by stage.)
  - The `WORKER_PROTOCOL` no-scope-creep rule becomes the **two-trigger issuance +
    self-contained-ticket contract** (provenance + title + description + acceptance
    criteria), covering surfaced **in-scope** deferred work, not only out-of-scope.
  - Bundled worker-protocol fixes from the same Symphony `WORKFLOW.md` parity review
    (gap #5): **(a)** *sync-before-work* — sync the working base to `origin/main`
    before substantial work and record the evidence (the serialized merger rebases at
    land, but a stale base surfaces conflicts late, mid-sweep); **(b)** *rework reset*
    — when a ticket returns because the *approach* was wrong (not incremental
    feedback), reset (close the PR, fresh branch, fresh plan) instead of always
    continuing the on-arrival sweep.
- **Relationship to the tech-debt-tracker.** `docs/exec-plans/tech-debt-tracker.md`
  stays the home for harness-internal fix-forward notes; the surfaced-deferred-work
  trigger is for work that should re-enter the orchestration loop as a *dispatchable*
  unit — when in doubt, a self-contained follow-up **ticket** is the active channel,
  a tracker row the passive one.
- **No new tooling; no taxonomy type removed.** The five types remain as start-points;
  only the templates' hand-off behavior and the issuance contract change. The DAG,
  orchestrator board-ownership, and serialized merger are untouched.
- Supersedes the D-18/D-20 framing in
  `docs/product-specs/2026-06-14-dev-stage-taxonomy.md` and refines the
  "self-contained children" finding of the Symphony-parity worker-policy review
  (`docs/design-docs/symphony-parity-gap.md` gap #5). Cross-links
  [[0001-recursive-decomposition]] and [[0002-graduated-autonomy]].
