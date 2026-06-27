---
status: accepted
last_verified: 2026-06-18
owner: harness
type: adr
tags: [autonomy, director, lights-out, principles]
description: Human-absent autonomy — the Director judges with the human's externalized taste (PRINCIPLES.md), woken only on the residual the doc can't resolve.
---
# Lights-out Director — human-absent autonomy via the Core Principle doc

> **Refined by [[0007-one-operating-mode]]** (2026-06-28): the two-axes split stands,
> but "lights-out" is now framed as a **property** (human absent) of the one operating
> mode, not a separate mode; "autonomous" (pure-code decider) is a CI/`--mock` **fixture**.

Child decision under [[0002-graduated-autonomy]] slice 2 (recursive decomposition,
[[0001-recursive-decomposition]]). It revises slice 2's framing: the "dial" is not
a code predicate in `decider.py` — it is a **Director agent that judges with the
human's externalized taste**, woken only on the residual the doc cannot resolve.

## Decision

**Split the one mode bit into two independent axes** — *is a Director (judging
agent) present?* × *is the human present?* Today's flag is the diagonal:

| | human present | human absent |
|---|---|---|
| **Director present** | `watched` (human-attended session *is* the Director) | **lights-out — the missing quadrant this ADR adds** |
| **no Director (pure code)** | (n/a) | `--autonomous` = `decider.autonomous_decide` |

1. **"Autonomous" rebinds** from *"no Director, pure code"* to *"no human,
   Director-only."* The pure-code `autonomous_decide` retreats to the no-agent
   niche it already names in `DIRECTOR.md §5` — `--mock` / CI / truly-detached
   (no session at all). The interesting mode is **lights-out**: a Director agent
   judges every turn-end with real taste, and the *human* is the async-reachable
   escalation layer, not a per-turn participant.

2. **The runtime that makes lights-out real is a Daemonized Claude Code** — a full
   Claude-Code-equivalent session (Agent SDK), event-woken, always-ready, still
   able to receive human messages. It is a **separate, in-development track**, OUT
   of scope here. It is **not** the rejected `claude -p`-per-decision spawn:
   [[no-headless-director-codex-owns-approval]] is **NOT superseded**. A daemonized
   *main session* still satisfies "keep the Director the watched main session" — it
   *is* a main session, merely unattended-capable; `DIRECTOR.md §2`'s "no separate
   headless process that decides" stays true (the daemon is the Director, not a
   separate decider). The memory rejects a stateless per-event subprocess used as a
   security *approver*; this is a stateful session that is the *taste judge*. The
   distinction is recorded here so future work does not re-flag the daemon as the
   anti-pattern.

3. **New layer — `docs/PRINCIPLES.md`, the human's externalized decision-taste.**
   The Director consults it to *simulate the human's call* at a taste fork before
   ever escalating. It is the literal endpoint of two repo rules — "Feedback twice
   → promote" and "Not in the repo = does not exist" — applied to *judgment*, not
   process: the human's taste stops living only in their head (unreachable by the
   Director) and becomes a consultable artifact. It is a **sibling**, not a rewrite:
   `PRODUCT_SENSE.md` = what the *harness* optimizes (universal); `DIRECTOR.md §2`
   = the *mechanics* of taste-vs-handle; `PRINCIPLES.md` = the *content* that lets
   "escalate" first try "infer."

4. **The lights-out decision procedure** the Director runs at any turn-end it
   cannot trivially auto-continue:
   - **Hard blocker** (missing auth/secret/resource, external dependency down) →
     **park "awaiting human"** — cannot proceed regardless of judgment.
   - else **classify the call:**
     - **technical / mechanical** (most merges, conflict resolution, branch
       publish, refactors, approach A-vs-B) → **decide + log** — the Director
       usually knows better than the human; do not wake them.
     - **taste / opinion / product-direction** → **consult `PRINCIPLES.md`:**
       determines it with confidence → **decide + log** (cite the principle);
       silent / ambiguous → **park "awaiting human."**

   The discriminant is **taste-vs-mechanical, NOT reversibility.** The **hard
   safety floor is the guardrail architecture** — Codex sandbox, the
   `authority.py` mutation allowlist, the serialized merger — which physically
   bounds what *any* actor may do. The Director acts **freely within** those
   guardrails; it does not run a reversibility test in its head. This **revises**
   `DIRECTOR.md §2`'s "the human owns irreversible/outward-facing actions even if
   allowlisted" → the human owns the *taste* in those actions, not the *act*; the
   Director performs mechanical outward-facing actions within the guardrails.

5. **The division of labor is preserved — slice 2 removes nothing from the worker's
   judgment.** Three tiers, each absorbing what it can:
   - **worker** — does the work, self-resolves routine forks (slice-1 protocol),
     writes board *structure* (`issueCreate`/`issueRelationCreate`) + the *progress
     comment* (slice 2b), and **proposes its terminal outcome** (`report_outcome`:
     done/blocked/needs_human). All kept; `report_outcome` is the worker's own
     judgment valve and removing it would *increase* Director load.
   - **orchestrator** — owns lifecycle *state* writes (claim/reconcile/terminal).
     Unchanged. Slice 2c removes only the worker's *state-write hole* (`issueUpdate`
     out of `DEFAULT_MUTATION_ALLOWLIST` + the `plugin-workspace/skills/linear` doc that
     wrongly tells the worker to transition state) — **zero Director burden added**;
     it just stops a second writer racing the orchestrator.
   - **Director** — *adjudicates the worker's proposal* (one decision per turn-end);
     does not redo the work or write state.
   - **human** — uncovered taste + hard blockers + draining the parked set.

## Why

- **It removes the last human-attention bottleneck (the per-turn watched Director)
  while keeping a *real* judge.** The pure-code decider could only escalate on
  generic signals (`attempt≥2`, a "destructive" regex); a Director agent with
  `PRINCIPLES.md` applies *this human's* taste — a capability no code heuristic can
  reach. This is the faithful completion of ADR 0002's "autonomous in the middle."
- **The principle doc + audit loop is a self-improving taste loop.** Every "decide +
  log" records `{fork, principle relied on, inferred decision}`; the async human
  reviews, corrects misfires, the doc sharpens, the parked set converges down. It is
  "feedback twice → promote" running continuously over taste.
- **taste-vs-mechanical is the correct discriminant** because human time is the
  scarce resource (`PRODUCT_SENSE.md`) and the Director often knows better on
  technical calls. Safety does not come from making the Director timid about
  irreversible acts — it comes from the guardrails that bound every actor. Pushing
  the floor into the guardrail layer (code) and out of the Director's judgment
  (prose) matches "minimal blocking gates / guardrails as code."
- **Reconciling with the no-headless memory by mechanism, not by exception:** a
  persistent session clone is categorically different from a per-decision spawn, and
  it answers the *taste* question Codex's `auto_review` never covered.

## Consequences

- **Slice 2's center of gravity moves from code to contract + methodology.** The
  `make_queue_decider` seam (turnReview → queue → `answer_turn`) is **unchanged** —
  it already routes to "whoever is the Director," human-session or daemon. The
  lights-out logic lives in the *Director's head* (prompted by `DIRECTOR.md` +
  `PRINCIPLES.md`), not in `decider.py`. Slice-2 deliverables, buildable + testable
  now: `docs/PRINCIPLES.md` (structure + a Claude-authored seed), a `DIRECTOR.md`
  lights-out section (the procedure above + the §2 revision), the **park /
  "awaiting human"** board+queue contract (largely the existing `escalate`
  disposition + a board marker so a human can drain the parked set), the mode-model
  reframe, plus the two small code items 2b (progress comment) and 2c (`issueUpdate`
  ceiling).
- **The Daemonized Claude Code is OUT of scope** (separate track). Slice 2 builds the
  contracts it will consume; live end-to-end lights-out validation waits for it. The
  artifacts are independently testable (principle-consultation is Director-prompt
  behavior verifiable on a fork + doc; the park marker is unit-testable; 2b/2c are
  unit-testable).
- **`PRINCIPLES.md` is seeded now by Claude** from observed decision patterns
  (CLAUDE.md guidelines, this repo's decisions, this human's autonomy bias); the
  human refines it later and via the audit loop.
- **Revises `DIRECTOR.md §2`** (irreversible/outward-facing wording, per Decision 4)
  and adds a lights-out section. The `no-headless-director` memory **stands** — this
  ADR is where the daemon-vs-spawn distinction is recorded; do not rewrite the memory.
- **Live risk to watch:** the Director simulating taste via `PRINCIPLES.md` could
  over-confidently decide an *uncovered* taste call. Fail-safe is conservative — when
  the doc does not clearly determine it, **park**. The audit loop catches misfires
  and sharpens the doc; the confidence threshold stays high. This is the lights-out
  analog of ADR 0002's "a wrong autonomous taste call costs more than one escalation."
- Runs the `product-design → execplan → completion-gate` flow; the spec links this
  ADR. Roadmap is the derived view of the slice tags ([[0001-recursive-decomposition]]).
