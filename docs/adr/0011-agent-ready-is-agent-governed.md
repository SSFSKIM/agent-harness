---
status: accepted
last_verified: 2026-06-29
owner: harness
type: adr
tags: [autonomy, agent-ready, dispatch, director, partner, least-human-in-loop]
description: agent-ready is an agent-governed readiness signal, not a human-permission gate — Director and Partner set it autonomously (most tickets agent-ready); the human curates at the edges. Refines ADR 0009's "the one bit a human still owns" framing toward least-human-in-loop.
---
# agent-ready is agent-governed — least human in loop

[[0009-collapse-dispatch-taxonomy]] collapsed the dev-stage taxonomy to a single
`agent-ready` dispatch label and framed it as *"whether an agent should pick it up is the
one bit a human **still owns**."* When the Partner role was first built, that framing was
read literally — the Partner created briefs **without** `agent-ready` and a human had to
mark them to admit the work, and the Claude Code auto-mode permission classifier even
**denied** an agent trying to set the label. The human (2026-06-29) rejected this: it
contradicts the project's **least-human-in-loop** north star. This ADR reframes the
ownership of `agent-ready`.

## Decision

**`agent-ready` is an *agent-governed readiness signal*, not a human-permission gate.**
The central agents — the **Director** and the **Partner** — set and govern `agent-ready`
**autonomously**, as part of governing ticket status. The expected default is that **most
tickets are `agent-ready`**: a ticket that represents real, ready agent work carries the
label, set by whoever shaped it (an agent or a human). The human governs **at the edges**
— curating the board (remove `agent-ready` to veto or pause a direction, redirect, close),
sharpening `docs/PRINCIPLES.md` — **not** as a per-ticket admission gate.

Three things make this concrete:

1. **The dispatch-gate *mechanism* (ADR 0009) stands, unchanged.** `dispatch_requires_label`
   stays default-on; `orchestrator.eligible_tickets(require_label=True)` still admits only
   `agent-ready` tickets. It still does its real job — keeping non-agent noise (Linear's
   default onboarding issues, a half-shaped human draft no agent has marked ready) out of
   the worker pipeline. **Only the *ownership framing* flips:** "the one bit a human still
   owns" → "an agent-governed readiness signal, human-curated at the edges."

2. **The Partner becomes symmetric with the Director** — both autonomous central agents,
   the human at the edges, differing by *domain* (Partner = the front/ideation, Director =
   the middle/operations), not by *autonomy posture*. The Partner **marks its own briefs
   `agent-ready`** (it admits its own proposals to the pipeline) and **proactively surfaces
   new directions for *awareness/veto* (a `PushNotification`), not for permission**. This
   **removes** the Partner's prior "no lights-out / surface-never-enact / direction is the
   human's" framing: like the Director, the Partner decides mechanical and
   PRINCIPLES-covered calls itself and **parks only a genuinely-uncovered taste fork**
   (the lights-out fail-safe both central agents share).

3. **The orchestrator-owns-lifecycle-*state* invariant (ADR 0003 `issueUpdate` ceiling) is
   untouched.** That invariant is about **race-freedom**, not human-gating: a second writer
   transitioning lifecycle *state* would race the orchestrator's claim/reconcile. Agents
   set the `agent-ready` **label**; the orchestrator owns the lifecycle **state**. Governing
   `agent-ready` does not breach the ceiling.

## Why

- **Least-human-in-loop is the north star** ([[0002-graduated-autonomy]]: "human at the
  edges, autonomous in the middle"; [[0003-lights-out-director]]). A per-ticket human
  *admission* gate is exactly the per-turn bottleneck those ADRs removed, reintroduced one
  layer down. Making `agent-ready` human-owned silently re-grows the human into the middle.
- **The guardrails are the floor, not the human's vigilance.** The sandbox, the
  `authority.py` mutation allowlist, and the serialized merger bound what *any* actor can
  do (ADR 0003). Within that floor an agent governs ticket status freely; a human admission
  gate buys no safety the guardrails don't already provide — it only adds latency.
- **Scarce human time goes to the edges.** `PRODUCT_SENSE.md` makes human attention the
  scarce resource; spending it curating direction at the board edges (and via PRINCIPLES.md)
  has far more leverage than gating each ticket's admission.
- **It resolves the Partner's internal contradiction the right way.** The Partner's
  original handoff was internally inconsistent (it claimed "human owns direction" yet
  "orchestrator auto-claims"). There were two ways to resolve it — add a human gate, or let
  the agent govern autonomously. The first was chosen first and was wrong against the north
  star; this ADR chooses the second.

## Consequences

- **`.claude/PARTNER.md` reframed:** the Partner marks its briefs `agent-ready` by default,
  surfaces new directions for awareness/veto (not permission), and gains the lights-out
  fail-safe (decide mechanical/PRINCIPLES-covered; park only uncovered taste) — symmetric
  with the Director. `G1`/`G4`/`G5` and the Identity reframed; `G2` (stop at the brief — no
  spec/code/merge) and `G3` (not a worker tool / not vendored) stand.
- **[[0010-cabinet-of-central-roles]] reframed:** the coupling is board-mediated and
  agent-governed (not human-gated); the "Partner has no lights-out autonomy" consequence is
  reversed.
- **[[0009-collapse-dispatch-taxonomy]] gets a dated pointer** to this reframe; its
  mechanical decision (the single `agent-ready` gate, default-on) is unchanged.
- **Permission (a user action, not landed here):** for a real Director/Partner session to
  govern `agent-ready` without a human prompt, the session's settings need an allow rule for
  the Linear write tools (`mcp__plugin_linear_linear__save_issue` + `create_issue_label`).
  This ADR does **not** land that rule: the auto-mode classifier correctly refuses to let an
  agent widen its *own* permissions (a sound self-modification guard — distinct from, and not
  to be confused with, the mis-framed *admission* denial this ADR fixes). The user adds the
  allow rule (or approves the prompt); it is recorded here as the needed posture. (The
  orchestrator-owns-lifecycle-state discipline stays a *role-doc* rule, not a mechanism —
  agents are trusted central actors with board access via `LINEAR_API_KEY`.)
- **Live note:** the ideation-partner dogfood (LIN-31) created an un-`agent-ready` brief
  under the old framing; under this ADR the Partner would mark it `agent-ready`. The
  dogfood record is corrected (the classifier denial was downstream of the wrong framing,
  not a validation of it).
- Human directive, 2026-06-29. Refines 0002/0003/0009; supersedes none.
