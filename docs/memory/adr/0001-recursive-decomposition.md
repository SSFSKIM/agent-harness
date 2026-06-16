---
status: accepted
last_verified: 2026-06-16
owner: harness
---
# Recursive decomposition suffices — no higher-order spec system

## Decision

Work too large for one spec is handled by **recursive decomposition with the two
tools we already have** (`product-design` spec + `execplan`), not by any new
meta-spec artifact, format, or hierarchy tooling. The rule is already in
PLANS.md "Scope check": too big → split into linked pieces, *this one as the
parent index*, before filling Milestones. Applied **recursively** it scales
without limit — each sub-project gets its own `spec → ExecPlan → implementation`
cycle, and a sub-project that is itself too big decomposes the same way. A
"capability / parent spec" is just a Product Design spec that happens to index
children, not a distinct type.

This is the superpowers brainstorming **scope** rule verbatim: *"If the project
is too large for a single spec, decompose into sub-projects — what are the
independent pieces, how do they relate, what order — then [build] the first
sub-project through the normal flow. Each sub-project gets its own
spec → plan → implementation cycle."* We adopt it as-is; nothing above it is
needed.

## Why

- Feature-sized `spec → ExecPlan` is enough because large work *is* feature-sized
  children once decomposed. Depth is emergent from the breakdown, not a
  prescribed ladder, and practically bounded (ARCHITECTURE → capability spec →
  feature spec → ExecPlan), so building for "infinite nesting" is YAGNI.
- A separate spec-hierarchy system would duplicate the orchestrator: **run-time
  sequencing of many child work-units is the ticket DAG + Director**
  (`docs/product-specs/2026-06-14-symphony-director-orchestration.md`), not a doc
  subsystem. The spec tree (design-time) and the ticket DAG (run-time) are the
  same tree.
- Confirmed three times (feedback-twice → promote): the Symphony parent spec with
  live children (`orchestrator-dispatch-loop`, `dag-aware-orchestration`),
  Lingual's `PEDAGOGY_ENGINE` capability cluster, and the brainstorming scope
  rule above.

## Consequences

- Do **not** add a meta-spec format/lint/tooling. Use product-design + execplan
  recursively; let the orchestrator own run-time fan-out.
- A parent spec **declares** its decomposition + order **as a structured field**
  — a phase/slice tag per child (PEDAGOGY's `targetPhase`, Symphony's `Phase N`),
  not scattered prose. Then any roadmap/status is a cheap *derived view*: a
  group-by of that tag, plus where each child ExecPlan lives (`active/` vs
  `completed/`), never a separately hand-maintained tracker. Tag the children at
  design time and the roadmap is free — that is what makes the decomposition
  intentional from the start rather than reconstructed later.
