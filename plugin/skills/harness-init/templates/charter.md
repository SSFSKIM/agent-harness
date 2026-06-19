---
status: stable
last_verified: {{TODAY}}
owner: harness
type: charter
tags: [charter, intent, mission]
description: The top-level intent of {{PROJECT}} — mission, design philosophy, and locked assumptions; the Orient anchor every session re-reads to resist long-session drift.
---
# CHARTER — {{PROJECT}}

The durable statement of *what this project is for and why it is shaped the way
it is.* Read it first at **Orient** — in a long, fanned-out session the original
big picture gets buried, and this page re-anchors it. Keep it a **map**:
headlines + pointers, depth in the linked docs. For *where we are against this
intent right now*, run `<plugin>/scripts/nav.py roadmap` (a derived view, never
hand-maintained).

## Mission

<!-- FILL: one paragraph — why this project exists / the ultimate goal. -->

## What "done" looks like

<!-- FILL: top-level success in observable terms — what a user can do once this
     project has succeeded. -->

## Design philosophy (기획의도)

*Why the product is shaped this way.* Chosen reasoning you believe in — it can
mature, and when it does the pivot shows in `nav.py roadmap` (the evolution
view). One line per strand, each pointing to the doc that elaborates it.

<!-- FILL: 3-6 strands. Shape (use a real markdown link to the rationale doc):
     - **<principle>.** <one line on why>. See design-docs/core-beliefs.md. -->

## Locked assumptions

*Fixed axioms — taken as given and not re-litigated.* Distinct from the
philosophy above: an axiom does not move, so it never appears in the evolution
view; if you find yourself re-arguing one, it was really a philosophy strand.

<!-- FILL: the human↔AI assumptions this project locks in up front. -->

## Initiatives

The major arcs — one line each, pointing to the parent spec that indexes its
children; live phase/status is the derived `nav.py roadmap`.

<!-- FILL: one bullet per initiative, linking its parent product-spec. -->
