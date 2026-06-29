---
status: draft
last_verified: 2026-06-29
owner: harness
phase: methodology/03-ideation-partner
type: product-spec
tags: [methodology, agents, cabinet, partner, ideation, daemon]
description: A second central role — the Partner, a persistent human-surface ideation agent that crystallizes a raw human (or AI) intuition into a pre-spec brief through dialogue (optionally researching, optionally invoking scout), delivers it as a board ticket, and proactively surfaces next initiatives on a self-scheduled pass. Stops at the brief; the existing pipeline executes. Reframes the center from a single Director into a named-role cabinet.
---
# Ideation Partner — the cabinet's first new role

The Director is the harness's only central agent today: an **executive conductor** —
it receives worker turn-end reports and answers them, escalating only taste
([`DIRECTOR.md`](../../.claude/DIRECTOR.md); [ADR 0003](../adr/0003-lights-out-director.md)).
That is the right role for the *middle* of the pipeline (getting work done), and it
is enough for it. But the *front* of the pipeline — turning a half-formed human
intuition into work the machinery can execute — has no owner. This spec adds that
owner: the **Partner**, and in doing so reframes the center from a single Director
into a **named-role cabinet**.

This spec was itself produced by running the Partner flow by hand (a brainstorming
dialogue that crystallized this design, now handed to `product-design`) — the meta
dogfood that motivates building it as a standing role.

> **Reconciled 2026-06-29 with [ADR 0011](../adr/0011-agent-ready-is-agent-governed.md).** A
> human directive reversed this spec's original *human-owned-admission* framing: `agent-ready`
> is **agent-governed** — the Partner marks its own briefs ready and the human curates at the
> edges, not as a per-ticket gate (least human in loop). The requirements, guardrails, the
> Design data-flow, the verification, and the non-goals below are updated to match;
> `.claude/PARTNER.md` + ADR 0011 are authoritative where any residual "human owns direction /
> surfaces-never-enact / no lights-out" wording survives.

## Problem

Three convergent gaps leave the pipeline's front unowned:

- **`scout` is one-shot, not a dialogue.** It fans out stance-forced vision
  generators and writes one `horizon` doc, then stops — "propose, never enact"
  ([workstream-scout](2026-06-27-workstream-scout.md)). It never *sits with the human*
  to sharpen a specific intuition into something buildable.
- **`product-design` deliberately avoids human dialogue.** Its procedure says *"Draft
  autonomously — your own reasoning, **not a human dialogue**"* and confines the human
  touch to escalating genuine taste forks. It assumes the *what* is already roughly
  known — it has no front-end that *establishes* the what with the human.
- **The Director is operational, not strategic.** Its whole job is answering turn-ends
  (`DIRECTOR.md` Identity); it does not think about what the project should pursue next.

So the work of *clarifying a raw idea with the human — researching when needed,
diverging when useful, and shaping it to the pre-spec boundary — then handing it to the
machinery* is done ad hoc, in whatever session the human happens to be in, with nothing
that persists the project understanding or proactively raises what is worth doing next.

## Requirements

Each is independently checkable.

- **R1 — Partner role doc.** A new central role doc `.claude/PARTNER.md` exists, a
  sibling to `DIRECTOR.md`: reading it is what makes a session the Partner. It defines
  the Identity, the operating line, the two modes, the guardrails, the brief format, and
  the config split. Like `DIRECTOR.md` it is **central** — shipped in this repo, never
  seeded into a host (the Partner is centralized, same as the Director).

- **R2 — Cabinet reframe (ADR 0010).** An ADR records the decision that the center is a
  **named-role cabinet** (Director = operations, Partner = ideation/strategy, room for
  more human-surface roles), superseding `DIRECTOR.md` §14's "the harness runs exactly
  **two** kinds of agent" framing. `DIRECTOR.md` §14 is edited to acknowledge the cabinet
  and cross-link the ADR. The ADR is registered in `docs/adr/index.md`.

- **R3 — Two operating modes.** `PARTNER.md` defines:
  - **Mode 1 (on-demand dialogue, human-woken):** the human reaches the Partner; it runs
    a brainstorming-style crystallization (understand → optionally diverge via `scout` or
    `deep-research` *only when warranted* → converge), and on reaching pre-spec clarity
    writes the brief, drops it as **one board ticket** (`issueCreate`), and **marks it
    `agent-ready`** itself (ADR 0011); the existing orchestrator claims it (loose coupling;
    **no** direct Director handoff).
  - **Mode 2 (proactive pass, schedule/event-woken):** on a self-scheduled wake the
    Partner assesses project state (`docs-nav` roadmap, `logs.md`, recent run outcomes),
    optionally runs a `scout`-style pass, and for initiatives worth doing **produces
    `agent-ready` briefs** (the pipeline runs) and **surfaces** them to the human
    (`PushNotification`) for *awareness/veto*, not permission (ADR 0011).

- **R4 — Guardrails (stated in `PARTNER.md`, checkable by inspection).**
  - **G1** the Partner governs `agent-ready` and sets direction within the guardrails,
    without per-ticket human permission; Mode 2 surfaces new directions for *awareness/veto*,
    not approval (ADR 0011);
  - **G2** the Partner stops at the brief — it never writes a `docs/product-specs/` spec,
    never decomposes into an ExecPlan, never edits code, never merges;
  - **G3** no worker invokes the Partner, and `PARTNER.md` + the Partner's skills are not
    vendored into worker runtimes (joins the existing `scope: director` exclusion —
    [workstream-scout](2026-06-27-workstream-scout.md) Fences);
  - **G4** the Partner's board write covers `issueCreate`, `commentCreate`, and the
    `agent-ready` label it governs (ADR 0011); it never transitions lifecycle **state** —
    the orchestrator owns that ([ADR 0003](../adr/0003-lights-out-director.md) `issueUpdate`
    ceiling, a *race-freedom* invariant), so the loose coupling stays race-free;
  - **G5** the Partner is autonomous (symmetric with the Director, ADR 0011): it decides
    what `docs/PRINCIPLES.md` and the merits cover, and **parks** only a genuinely-uncovered,
    high-stakes taste fork (the Director's lights-out fail-safe) — not a per-ticket human gate.

- **R5 — Brief format.** The brief is a **pre-spec** carried as the `issueCreate` ticket
  body: problem/intent · the crystallized idea (what + why + macro-shape) ·
  "ambitious-yet-reasonable" framing · optional research findings with citations · open
  questions for `product-design` · suggested scope. A downstream `product-design` worker
  picks it up from the ticket and produces the durable `docs/product-specs/` spec; the
  brief's durability comes from that promotion, not from a separate artifact.

- **R6 — Self-scheduled proactive wake.** The proactive pass is driven by the Partner
  session **self-scheduling** via `CronCreate(durable: true)` — it enqueues its own
  Mode-2 prompt on a cron, persisted to `.claude/scheduled_tasks.json` so it survives the
  session being recycled. The mechanism fires only while the REPL is idle (so it never
  collides with an attached Mode-1 dialogue), and the Partner **re-arms** the schedule on
  its final fire / on session start to defeat the 7-day recurring auto-expire. (Mechanism
  confirmed feasible — see *Verification*.)

## Design

This is a methodology + light-wiring feature: most of the deliverable is a role doc; the
only moving parts are the session/scheduler wiring and the vendoring fence. No new Python
subsystem.

### Session model — one persistent, daemon-hosted Partner session

The Partner is a **single persistent Claude Code session**, hosted by the built-in
daemon (`claude daemon` / `claude agents`, verified live, v2.1.195), distinct from the
Director session. The same session serves both modes and accretes project understanding:

- **Mode 1** — the human `claude attach`es to the Partner session (or resumes it) and
  converses; context accumulates in one conversation.
- **Mode 2** — a `CronCreate(durable)` job the session created enqueues the proactive-pass
  prompt into *this same session* while idle.

This is the "Daemonized Claude Code" runtime that [ADR 0003](../adr/0003-lights-out-director.md)
named as a separate track — now a shipped platform primitive. It is a **stateful
persistent session**, not a `claude -p` per-decision spawn — the same daemon-vs-spawn
distinction [ADR 0003](../adr/0003-lights-out-director.md) §2 records (its index entry:
"no-headless memory NOT superseded"), so that constraint is **not** contradicted.

### Config — doc-only for v1 (mirrors the Director's identity half)

The Director's config splits identity → `.claude/` and runtime → `.harness.json:director`
(`DIRECTOR.md` §14). The Partner reuses the **identity half only**: `.claude/PARTNER.md`
plus the session's `.claude/settings.json` tool/permission surface. A declarative
`.harness.json:partner` block (cron expression, team to surface to) is **deferred** — v1
keeps the schedule and team in `PARTNER.md` prose. No `director/config.py` change.

### Tools and authority — a trusted central agent

The Partner is inside the trust boundary (like the Director), so it writes to the board
**directly** with the host `LINEAR_API_KEY` — the worker-authority guardrail
(`director/worker/authority.py`, T10) governs *sandboxed workers*, not central agents. Its
skill surface: `scout` (divergence), `deep-research` (only when info is genuinely
insufficient), `docs-nav` (state). It does **not** invoke `product-design`/`execplan`
(downstream); it may *read* `PLANS.md`'s entry decision.

### Data flow

```
Mode 1:  human intuition
         → Partner dialogue  (scout / deep-research only when warranted)
         → pre-spec brief    → issueCreate(board) + mark agent-ready
         → [loose coupling]  orchestrator claims the agent-ready ticket
         → worker: product-design → spec → execplan → build → merger
         (human may veto/redirect at the board edge)

Mode 2:  CronCreate(durable) idle wake
         → assess (docs-nav roadmap + logs.md + recent runs)
         → optional scout pass
         → produce pre-spec brief(s) → issueCreate + mark agent-ready → pipeline runs
         → PushNotification surfaces them for awareness/veto (not permission)
```

### Files to create / modify

| Action | Path | What |
|---|---|---|
| CREATE | `.claude/PARTNER.md` | the role doc (R1, R3–R6). The bulk of the work. |
| CREATE | `docs/adr/0010-cabinet-of-central-roles.md` | the reframe decision (R2). |
| MODIFY | `.claude/DIRECTOR.md` §14 | "exactly two kinds of agent" → cabinet; cross-link ADR 0010. |
| MODIFY | `docs/adr/index.md` | register ADR 0010. |
| MODIFY | `docs/product-specs/index.md` | register this spec. |
| NOTE | tech-debt tracker (`scope: director` row) | record that `PARTNER.md` + Partner skills join the worker-vendoring exclusion (G3). |

### Verification (testability seams)

- **Gate-GREEN (deterministic):** `PARTNER.md`, ADR 0010, and the index edits pass the
  doc lint (`plugin/scripts/lint_docs.py` — frontmatter, links, index registration); the
  §14 edit and ADR cross-links resolve.
- **Scheduler mechanism (confirmed, pre-build):** `CronCreate` enqueues into the current
  session's REPL, `durable: true` persists to `.claude/scheduled_tasks.json` (`.claude/`
  is writable), and jobs fire only while the REPL is idle — confirmed from the tool
  contract + a writability/baseline probe (2026-06-28). The single residual is the 7-day
  recurring auto-expire, handled by R6's re-arm. A live fire-test is deferred to the
  dogfood (it would inject a prompt into a live conversation).
- **Behavioral dogfood (the real test):** run the Partner on a real idea (as this spec's
  own authoring did) and verify the terminal output is a well-formed brief ticket that the
  existing pipeline picks up (orchestrator claims it → a `product-design` worker produces a
  spec) — the end-to-end loose coupling.
- **Boundary-holds (inspection):** a Mode-1 run's board diff is *exactly* one brief ticket
  carrying the `agent-ready` label (+ optional comments) — no spec doc, no code, no lifecycle
  **state** transition (the Partner sets the label, never moves the ticket through states;
  mirrors scout's "a run's diff is exactly the horizon doc + index line" fence).

## Non-goals (YAGNI)

- **Declarative `.harness.json:partner` block** — doc-only for v1.
- **A `docs/briefs/` mirror** — the brief lives in the ticket; durability comes from the
  `product-design` promotion.
- **A second human-surface role** — the cabinet has room, but v1 builds only the Partner.
- **A per-ticket human admission gate** — `agent-ready` is agent-governed, not a human gate
  ([ADR 0011](../adr/0011-agent-ready-is-agent-governed.md)); the human curates at the edges.
  (This *reverses* two of the original non-goals — "Partner lights-out autonomy" and
  "proactive auto-enact" — which ADR 0011 folded into the design.)
- **`Workflow`-tool dependency** — the proactive pass uses the existing `scout` skill;
  no orchestration-tool requirement.

## Acceptance criteria

- `.claude/PARTNER.md` exists and, read into a fresh session, makes it behave as the
  Partner (runs Mode 1 to a brief ticket; respects G1–G5).
- ADR 0010 records the cabinet reframe; `DIRECTOR.md` §14 no longer claims "exactly two
  kinds of agent" and cross-links it; both indexes register their new pages.
- A dogfood run produces a brief ticket the existing orchestrator claims and a
  `product-design` worker turns into a `docs/product-specs/` spec — with no Partner-side
  spec/code/lifecycle write.
- The proactive pass can be self-scheduled (`CronCreate durable`) and re-arms past the
  7-day expiry.
- The gate is GREEN.

## Context

- Builds on [ADR 0003](../adr/0003-lights-out-director.md) (the Daemonized-Claude runtime
  it named as a separate track is the Partner's substrate) and reuses `docs/PRINCIPLES.md`
  (the Partner consults the same externalized-taste layer the Director does).
- Sibling to [workstream-scout](2026-06-27-workstream-scout.md): scout is the Partner's
  upstream seed and a callable divergence tool, not a peer.
- Hands off to [`product-design`](2026-06-14-product-design-phase.md): the Partner is the
  human-dialogue front-end `product-design` deliberately lacks.
- The daemon/`claude agents` substrate and the `-p --resume` / `CronCreate` drive surfaces
  were verified live on 2026-06-28 (Claude Code v2.1.195).
