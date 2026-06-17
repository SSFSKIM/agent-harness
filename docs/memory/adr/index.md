---
status: stable
last_verified: 2026-06-12
owner: imprint-job
---
# ADR index

Decisions + why. Register every page here (lint D8).

- [Recursive decomposition suffices — no higher-order spec system](0001-recursive-decomposition.md)
  — large work decomposes recursively via product-design + execplan (the
  brainstorming scope rule, applied at the spec level too); run-time fan-out is
  the ticket DAG, not a new spec subsystem.
- [Graduated autonomy — human at the edges, autonomous in the middle](0002-graduated-autonomy.md)
  — move the Director from per-turn judge to exception-handler; take Symphony's
  autonomy bet on the middle/worker axes, keep our board-ownership + serialized
  merger (correctness, not control). Two ordered slices: worker-protocol depth
  (gap #5) → selective-escalation decider.
