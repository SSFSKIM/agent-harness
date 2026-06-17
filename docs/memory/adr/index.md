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
- [Lights-out Director — human-absent autonomy via the Core Principle doc](0003-lights-out-director.md)
  — child of 0002 slice 2: split the mode bit into (Director present?)×(human
  present?); "autonomous" rebinds to *no-human* (Director-only), pure-code decider
  retreats to the no-agent niche. New `docs/PRINCIPLES.md` layer the Director
  consults to simulate the human's taste before escalating; discriminant is
  taste-vs-mechanical (not reversibility), guardrails are the hard floor.
  Daemonized Claude Code runtime is a separate track; no-headless memory NOT
  superseded.
