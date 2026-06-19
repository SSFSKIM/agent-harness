---
status: stable
last_verified: 2026-06-19
owner: harness
type: charter
tags: [charter, intent, mission]
description: The harness's top-level intent — mission, design philosophy (기획의도), and locked assumptions — the Orient anchor every session re-reads to resist long-session intent-drift.
---
# CHARTER — agent-harness

The durable statement of *what this project is for and why it is shaped the way
it is.* Read it first at **Orient**: in a long, fanned-out session the original
big picture gets buried, and this page is what an agent re-reads to re-anchor.
It is a **map** — headlines + pointers; depth lives in the linked docs. For
*where we are against this intent right now*, run `python3 plugin/scripts/nav.py
roadmap` (a derived view, never hand-maintained).

## Mission

A **portable agentic harness**: a substrate any repo can adopt so that AI agents
run long, self-correcting software development — planning, implementing,
reviewing, remembering — with the **minimum possible human touch**
([`PRODUCT_SENSE.md`](PRODUCT_SENSE.md)).

## What "done" looks like

A developer runs `harness-init` against any repo and agents can drive
multi-session development end to end: choosing the entry mode and writing the
spec/plan, implementing in-style, gating and reviewing themselves, and carrying
memory forward — the human touching only genuine taste/product forks. The
corpus stays **fresh** (gate GREEN) and **self-navigable** (`nav.py` answers
"what exists, what depends on what, where are we") without bulk-reading.

## Design philosophy (기획의도)

*Why the product is shaped this way.* Chosen reasoning we believe in — it can
mature, and when it does the pivot shows in `nav.py roadmap` (the evolution
view). Each strand → the doc that elaborates it.

- **Minimal blocking gates, fix-forward.** Only the deterministic `check.py`
  blocks a commit; everything else is risk-budgeted or fix-forward. Cheap fixes
  beat long waits. → [core belief 8](design-docs/core-beliefs.md), [the harness page](design-docs/agent-harness.md).
- **Structure is a projection of metadata, not a hand-maintained artifact.**
  Indexes, hierarchy, and the roadmap are *derived* from frontmatter + the link
  graph, so they cannot rot. → [KNOWLEDGE_FORMAT §2.2](KNOWLEDGE_FORMAT.md), [the OKF comparison](design-docs/okf-comparison.md).
- **Graduated autonomy under a watched Director.** The harness is shaped to run
  unattended and self-correct, escalating only what needs a human — so it can go
  lights-out without losing a safety floor. → [ADR 0002](memory/adr/0002-graduated-autonomy.md), [the Director manual](DIRECTOR.md).
- **Map, not encyclopedia.** Entry points stay short and stable; depth lives
  behind pointers (progressive disclosure). → [core belief 3](design-docs/core-beliefs.md).

## Locked assumptions

*Fixed axioms — taken as given and not re-litigated.* (Distinct from the
philosophy above: an axiom does not move, so it never appears in the evolution
view. If we find ourselves re-arguing one, it was really a philosophy strand.)

- **Agents write everything.** Humans contribute prompts, reviews, and docs
  feedback — never code. → [core belief 1](design-docs/core-beliefs.md).
- **Not in the repo = does not exist.** Decisions made in chat or heads are
  invisible; encode them as versioned repo artifacts. → [core belief 2](design-docs/core-beliefs.md).
- **General by identity.** This self-hosting repo is the harness's *first host*,
  not its destination; any change to how the harness works lands in the portable
  layer (`plugin/` + `harness-init` templates + `scaffold.py`). → [core belief 13](design-docs/core-beliefs.md).

## Initiatives

The major arcs. One line each → the parent spec that indexes its children; live
phase/status is the derived `nav.py roadmap`.

- **Symphony orchestration** — a ticket-DAG of agents (Director + workers) doing
  multi-agent development. → [the parent spec](product-specs/2026-06-14-symphony-director-orchestration.md).
- **Knowledge format** — the agent-legible docs substrate: frontmatter contract,
  live navigation, derived hierarchy and roadmap. → [the parent spec](product-specs/2026-06-18-knowledge-format-evolution.md).
