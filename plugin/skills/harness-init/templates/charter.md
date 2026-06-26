---
status: stable
last_verified: {{TODAY}}
owner: harness
type: charter
tags: [charter, intent, mission]
description: The top-level intent of {{PROJECT}} — mission (the ambition it steers by), core axioms, and design philosophy; the Orient anchor every session re-reads to resist long-session drift.
---
# CHARTER — {{PROJECT}}

The durable statement of *what this project is for and why it is shaped the way
it is.* Read it first at **Orient** — in a long, fanned-out session the original
big picture gets buried, and this page re-anchors it. Keep it a **map**:
headlines + pointers, depth in the linked docs. For *where we are against this
intent right now*, run `<plugin>/scripts/nav.py roadmap` (a derived view, never
hand-maintained).

## Mission

*The ambition you steer by — and the lens for which work belongs.*

<!-- FILL: one paragraph at the most ambitious altitude — the wide-reaching
     end-state this project steers by (it may be bigger than the artifact itself).
     THIS IS THE HUMAN'S TO SET. Include one observable "you can tell it is working
     when…" clause, and one sentence naming the Mission as the lens for deciding
     which workstreams belong. -->

## Core Axioms

*The few immovable claims the project is built on.* Test before locking one:
**reverse it — would this still be the same project?** No → it is an axiom; Yes →
it is a Design-philosophy strand (it can mature) or just an ADR. **Lock as few as
possible** — every axiom is a thing you have chosen not to re-examine, so the bar
is identity-defining, not merely "currently true". An axiom does not move, so it
never appears in the evolution view.

<!-- FILL: the few identity-defining claims (often the human↔AI assumptions this
     project locks in up front). One line each → the doc that grounds it. -->

## Design philosophy (기획의도)

*Why the product is shaped this way.* Chosen reasoning you believe in — it can
mature, and when it does the pivot shows in `nav.py roadmap` (the evolution
view). One line per strand, each pointing to the doc that elaborates it. (Distinct
from the axioms above: a strand can move; if you find yourself re-arguing an
axiom, it was really a strand.)

<!-- FILL: 3-6 strands. Shape (use a real markdown link to the rationale doc):
     - **<principle>.** <one line on why>. See design-docs/core-beliefs.md. -->

## Initiatives

The major arcs — one line each, pointing to the parent spec that indexes its
children; live phase/status is the derived `nav.py roadmap`.

<!-- FILL: one bullet per initiative, linking its parent product-spec. -->
