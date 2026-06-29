---
status: accepted
last_verified: 2026-06-28
owner: harness
type: adr
tags: [director, partner, cabinet, agents, ideation, methodology]
description: The harness's central layer is a named-role cabinet, not a single Director — the Director (operations) gains a sibling, the Partner (ideation/strategy, the front-of-pipeline human surface). Supersedes DIRECTOR.md §14's "exactly two kinds of agent".
---
# Cabinet of central roles — the Director is one of several

Until now the harness had exactly one central agent — the Director — and `DIRECTOR.md`
§14 stated it plainly: "the harness runs **exactly two** kinds of agent" (the Director +
the Codex workers). That was true while the Director was the only trusted agent the human
talked to. This ADR reframes the center as a **named-role cabinet**: the Director keeps
its job, and a second central role — the **Partner** — owns the part of the pipeline the
Director never did.

## Decision

**The harness's central layer (the trusted agents the human converses with, distinct from
the sandboxed workers) is a named-role cabinet, not a single Director.** Two members
today, with room for more:

- **Director — operations / conductor.** The *middle* of the pipeline: it receives worker
  turn-end reports, answers or escalates them, and orchestrates execution and merge
  (`.claude/DIRECTOR.md`). Unchanged by this ADR.
- **Partner — ideation / strategy.** The *front* of the pipeline: a persistent
  human-surface role that crystallizes a raw human (or AI) intuition into a **pre-spec
  brief** through dialogue (optionally researching, optionally invoking `scout`), delivers
  it as an **`agent-ready`** board ticket, and on a self-scheduled pass produces `agent-ready`
  briefs and surfaces next initiatives for awareness/veto. It **stops at the brief** — it never writes a spec, decomposes, codes, or
  merges (`.claude/PARTNER.md`).

This ADR establishes the **category**, not a fixed roster — future human-surface roles get
their own role doc and join the cabinet the same way. It **supersedes** `DIRECTOR.md`
§14's "exactly two kinds of agent" count; the *config model* is unchanged — each central
agent is configured by an identity half in `.claude/` plus its guide, and the worker by
`director/config.py` `DEFAULTS` (§14's two-profile config detail still stands for the
Director and the worker).

**Coupling is loose, board-mediated, and agent-governed.** The Partner and Director share no
session and no state; they coordinate only through the board — the Partner `issueCreate`s a
brief ticket and **marks it `agent-ready` itself**
([[0011-agent-ready-is-agent-governed]]: `agent-ready` is an agent-governed readiness signal,
not a human gate), and the orchestrator claims and executes it on its next poll. The Partner
**sets** the `agent-ready` label (which it governs) but never **transitions** lifecycle state
(the orchestrator's — [[0003-lights-out-director]] `issueUpdate` ceiling, a *race-freedom*
invariant) — so the coupling stays race-free; the human curates at the board edge (removing
`agent-ready` to veto/pause), not as a per-ticket gate.

## Why

- **The front of the pipeline had no owner.** Turning a half-formed intuition into
  executable work was nobody's job: `scout` is one-shot ("propose, never enact"),
  `product-design` deliberately *avoids* human dialogue ("draft autonomously, not a human
  dialogue"), and the Director is operational (it answers turn-ends, it does not decide
  what the project should pursue). A single "Director" silently conflated two jobs that
  want two different agents and two different human surfaces.
- **It matches how human time should be spent.** `PRODUCT_SENSE.md` makes human attention
  the scarce resource; the highest-leverage use of it is high-bandwidth dialogue with a
  thinking partner at the front, not per-turn operational adjudication. Splitting the
  surface lets the Partner own the dialogue and the Director own the throughput.
- **The runtime is now cheap.** [[0003-lights-out-director]] named the "Daemonized Claude
  Code" — a persistent, human-attachable, event/schedule-woken full session — as a
  separate, in-development track. It is now a shipped platform primitive (`claude daemon`
  / `claude agents`, verified live on Claude Code v2.1.195), so a second persistent central
  session costs almost nothing to stand up. The cabinet is buildable now, not speculative.
- **It does not re-open the rejected pattern.** The Partner is a **stateful persistent
  session** (the daemon-vs-spawn distinction [[0003-lights-out-director]] §2 records), not
  a `claude -p` per-decision spawn — [[no-headless-director-codex-owns-approval]] stands.

## Consequences

- **`DIRECTOR.md` §14 is reframed** (this change): the "exactly two kinds of agent"
  sentence becomes "the central agents form a named-role cabinet (Director + Partner …)",
  cross-linking this ADR. The Director's role, config split, and env contract are
  otherwise untouched.
- **New role doc `.claude/PARTNER.md`** — central, never host-seeded (like `DIRECTOR.md`).
  Built from the [ideation-partner-cabinet spec](../product-specs/2026-06-28-ideation-partner-cabinet.md);
  ExecPlan `docs/exec-plans/completed/2026-06-28-ideation-partner-cabinet.md`.
- **The Partner joins the `scope: director` worker-vendoring exclusion** — `PARTNER.md`
  and the Partner's skills are not copied into worker runtimes (it sets direction; a
  worker does not). Rides the tracked tech-debt the `scout` skill already names.
- **Doc-only v1.** No `.harness.json:partner` config block yet (schedule/team live in
  `PARTNER.md` prose); a declarative block is deferred until a second host needs it.
- **The Partner is autonomous, symmetric with the Director** (revised by
  [[0011-agent-ready-is-agent-governed]]). It governs `agent-ready` and sets direction within
  the guardrails; its proactive pass marks briefs `agent-ready` and surfaces new directions
  for *awareness/veto* (not permission); and it shares the Director's lights-out fail-safe —
  decide what `docs/PRINCIPLES.md` and the merits cover, **park** only a genuinely-uncovered
  high-stakes taste fork. The human governs at the edges.
- **Reuses `docs/PRINCIPLES.md`** — the Partner consults the same externalized-taste layer
  the Director does; no new taste artifact.
- Runs the standard ExecPlan completion gate (spec-compliance + code-quality +
  review-arch).
