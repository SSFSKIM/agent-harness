---
status: stable
last_verified: 2026-06-27
owner: harness
type: charter
tags: [charter, intent, mission]
description: The harness's top-level intent — mission (the ambition it steers by), core axioms, and design philosophy (기획의도) — the Orient anchor every session re-reads to resist long-session intent-drift.
---
# CHARTER — agent-harness

The durable statement of *what this project is for and why it is shaped the way
it is.* Read it first at **Orient**: in a long, fanned-out session the original
big picture gets buried, and this page is what an agent re-reads to re-anchor.
It is a **map** — headlines + pointers; depth lives in the linked docs. For
*where we are against this intent right now*, run `python3 plugin/scripts/nav.py
roadmap` (a derived view, never hand-maintained).

## Mission

*The ambition we steer by — and the lens for which work belongs.*

Software development becomes something humans **govern by intent and taste**, not
by typing. The agent-harness is the portable substrate that gets there: any repo
can adopt it so an agent collective carries work from idea to landed change —
planning, implementing, reviewing, remembering — across many sessions, surfacing
only the genuine forks of human judgment. *You can tell it is working when* a
developer runs `harness-init` against any repo and agents drive multi-session
development end to end — picking the entry mode, writing the spec/plan,
implementing in-style, gating and reviewing themselves, carrying memory forward —
with the human touching only taste. **Every proposed workstream is measured
against this:** does it move us toward *govern-by-intent,
human-touches-only-forks*? ([`PRODUCT_SENSE.md`](PRODUCT_SENSE.md))

## Core Axioms

*The few immovable claims the project is built on.* Test before locking one:
**reverse it — would this still be the same project?** No → it is an axiom; Yes →
it is a Design-philosophy strand (it can mature) or just an ADR. **Lock as few as
possible** — every axiom is a thing we have chosen not to re-examine, so the bar
is identity-defining, not merely "currently true". An axiom does not move, so it
never appears in the evolution view.

- **Agents write everything.** Humans contribute prompts, reviews, and docs
  feedback — never code. → [core belief 1](design-docs/core-beliefs.md).
- **Not in the repo = does not exist.** Decisions made in chat or heads are
  invisible; encode them as versioned repo artifacts. → [core belief 2](design-docs/core-beliefs.md).
- **General by identity.** This self-hosting repo is the harness's *first host*,
  not its destination; any change to how the harness works lands in the portable
  layer (`plugin/` + `harness-init` templates + `scaffold.py`). → [core belief 13](design-docs/core-beliefs.md).

## Design philosophy (기획의도)

*Why the product is shaped this way.* Chosen reasoning we believe in — it can
mature, and when it does the pivot shows in `nav.py roadmap` (the evolution
view). Each strand → the doc that elaborates it. (Distinct from the axioms above:
a strand can move; if we find ourselves re-arguing an axiom, it was really a
strand.)

- **Minimal blocking gates, fix-forward.** Only the deterministic `check.py`
  blocks a commit; everything else is risk-budgeted or fix-forward. Cheap fixes
  beat long waits. → [core belief 8](design-docs/core-beliefs.md), [the harness page](design-docs/agent-harness.md).
- **Structure is a projection of metadata, not a hand-maintained artifact.**
  Indexes, hierarchy, and the roadmap are *derived* from frontmatter + the link
  graph, so they cannot rot. → [KNOWLEDGE_FORMAT §2.2](KNOWLEDGE_FORMAT.md), [the OKF comparison](design-docs/okf-comparison.md).
- **Graduated autonomy under a watched Director.** The harness is shaped to run
  unattended and self-correct, escalating only what needs a human — so it can go
  lights-out without losing a safety floor. → [ADR 0002](adr/0002-graduated-autonomy.md); the Director manual (`.claude/DIRECTOR.md`, central-agent config).
- **Map, not encyclopedia.** Entry points stay short and stable; depth lives
  behind pointers (progressive disclosure). → [core belief 3](design-docs/core-beliefs.md).

## Initiatives

The major arcs. One line each → the parent spec that indexes its children; live
phase/status is the derived `nav.py roadmap`.

- **Symphony orchestration** — a ticket-DAG of agents (Director + workers) doing
  multi-agent development. → [the parent spec](product-specs/2026-06-14-symphony-director-orchestration.md).
- **Knowledge format** — the agent-legible docs substrate: frontmatter contract,
  live navigation, derived hierarchy and roadmap. → [the parent spec](product-specs/2026-06-18-knowledge-format-evolution.md).
- **Methodology** — how the agent decides *what* to build before building it: a
  Product Design stage ahead of ExecPlan plus the three-way entry decision. → [the parent spec](product-specs/2026-06-14-product-design-phase.md).
