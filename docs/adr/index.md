---
status: stable
last_verified: 2026-06-28
owner: harness
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
- [Ticket = purpose unit — pipeline within, decompose only on size or surfaced work](0004-ticket-purpose-unit.md)
  — a ticket is a purpose/feature unit carrying the whole research→spec→plan→exec→QA
  pipeline within it (the `type` label says where work *starts*, not "one stage then
  hand off"); a worker issues a new ticket only on a genuine size split or surfaced
  deferred work (incl. in-scope tech debt), and every issued ticket is self-contained
  (provenance + title + description + acceptance). Revises dev-stage-taxonomy D-18/D-20;
  realigns the taxonomy with 0001's recursive-decomposition.
- [No per-stage prompt templates — WORKER_PROTOCOL + AGENTS.md is the whole methodology surface](0005-no-stage-prompt-templates.md)
  — remove the planning/research/design/spec/impl prompt templates; the worker's operating
  surface is `WORKER_PROTOCOL` (always injected, now carrying the impl craft) + the host's
  auto-loaded AGENTS.md + invocable skills, which the worker calls by judgment.
  `compose_worker_prompt` returns the raw ticket (converging the `director.run` and
  orchestrator paths); the dev-stage label stays as dispatch/DAG metadata only. Completes
  0004; supersedes its per-template edits and the dev-stage-taxonomy template layer.
  **Dispatch/DAG-metadata clause superseded 2026-06-28 by [0007](0007-collapse-dispatch-taxonomy.md)**
  — the 5-value taxonomy collapsed to a single `agent-ready` label; the rest of 0005 stands.
- [Collapse the dispatch taxonomy to a single `agent-ready` label](0007-collapse-dispatch-taxonomy.md)
  — a trace showed the 5-value dev-stage taxonomy (planning/research/design/spec/impl) earned
  no structure: DAG sequencing is pure `blocked_by`, `child_types` was dead, and the label never
  shaped the prompt (0005) — its whole runtime footprint was the dispatch gate. Delete the
  taxonomy code; admit a ticket iff it carries `agent-ready` (`orchestrator.DISPATCH_LABEL`),
  gate **on by default**. A ticket carries the goal; *whether* an agent takes it is the one bit
  a human owns — HOW (research/spec/ExecPlan/patch) is the worker's judgment. Supersedes the
  dispatch/DAG-metadata clause of 0005.
- [Observability dashboard may vendor an offline, checked-in JS asset](0006-observability-vendored-asset.md)
  — **superseded 2026-06-27**: the [graph-view re-skin](../product-specs/2026-06-27-project-graph-view-reskin.md)
  dropped the vendored library and hand-rolled the render (DOM+SVG), so the dashboard now
  serves **zero** assets and the `/assets/*` route is gone (invariants 1 & 3 moved stricter).
  *Historical:* a SCOPED relaxation that let the dashboard serve a fixed set of vendored,
  checked-in JS bundles (Cytoscape + dagre + cytoscape-dagre) from a constant `/assets/*`
  route — offline (never a CDN), zero-traversal (fixed map), Python stdlib-only untouched.
  Not a general license to add deps elsewhere under `director/`.
- [No Director-authored worker hooks — `features.hooks=false` is settled, not deferred](0007-no-director-authored-worker-hooks.md)
  — closes the codex-worker-config lineage's deferred "Phase 3 = Codex hooks": the Director
  authors no tool-use hooks for either worker. No symmetry to restore (neither worker gets
  vendored hooks today), the candidate payloads are already served elsewhere or proved weak
  (context-budget is model-dependent + can't read usage from a shell hook), and enabling
  `features.hooks=true` would re-open the clone-`.codex/hooks.json` RCE that the always-on
  disable closes (T16, load-bearing). Reversal trigger recorded; cross-links 0005.
- [One operating mode — Director ⟷ Board](0008-one-operating-mode.md)
  — refines 0002/0003: finishes the arc by removing the residual multi-mode *framing*.
  There is ONE operating mode (always-present Director adjudicating an always-present
  Board); `attended`/`lights-out` are a **property** (human present?), `batch`/`--once`
  and the pure-code `--autonomous` decider are **fixtures**, and the always-on **daemon
  is the default**. `--mock` defaults to the bounded loop (offline board has nothing to poll
  forever). No posture/security change; Daemonized-Claude runtime still a separate track.
