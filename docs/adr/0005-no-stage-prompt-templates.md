---
status: accepted
last_verified: 2026-06-25
owner: harness
type: adr
tags: [taxonomy, worker, methodology, prompt, autonomy]
description: Remove the per-stage prompt templates — the worker's whole methodology surface is WORKER_PROTOCOL (always injected) plus the host's auto-loaded AGENTS.md and invocable skills; the dev-stage label becomes dispatch/DAG metadata only.
---
# No per-stage prompt templates — WORKER_PROTOCOL + AGENTS.md is the whole methodology surface

## Decision

A worker's operating instructions are exactly two layers, and **no more**:

1. **`WORKER_PROTOCOL`** — the single, always-injected cross-cutting operating contract
   (the analog of Symphony's `WORKFLOW.md`). It now **also carries the implementation
   craft** previously in `_IMPL_TEMPLATE` — reproduction-first, acceptance-criteria
   mirroring, temp-proof-revert, the PR-feedback sweep, self-QA, gate cadence,
   sync-before-work, and rework-reset — phrased as *conditional* guidance ("when you
   implement / open a PR…"), since a purpose-unit ticket ([[0004-ticket-purpose-unit]])
   normally includes the build.
2. **The host repo's own `AGENTS.md`** (auto-loaded at session start) **+ its invocable
   skills** (`product-design`, `execplan`, …), which the worker reads and **calls by its
   own judgment**.

We **remove** the per-stage prompt templates — `_PLANNING_TEMPLATE`,
`_RESEARCH_TEMPLATE`, `_DESIGN_TEMPLATE`, `_SPEC_TEMPLATE`, `_IMPL_TEMPLATE`.
`director.taxonomy.compose_worker_prompt` returns the ticket's own prompt **unchanged**;
every worker is framed only with `WORKER_PROTOCOL` + `TERMINAL_CONTRACT`
(`frame_first_turn`), **identically on the `director.run` and orchestrator paths**.

The dev-stage **label / `ticket_type` stays — as metadata only**: the dispatch filter
(`dispatch_requires_label`) and the typed DAG (`blocked_by` sequencing + observability).
It no longer shapes the prompt.

> **Superseded 2026-06-28 by [[0009-collapse-dispatch-taxonomy]].** A trace found this clause
> over-claimed: DAG sequencing is pure `blocked_by` (never `ticket_type`), and `child_types`
> was dead — so the taxonomy's only runtime use was the dispatch gate. The 5-value taxonomy is
> deleted and collapsed to a single `agent-ready` admission label (gate on by default). The
> rest of this ADR — no per-stage prompt templates — **stands.**

We add **no** methodology-pointer or "default posture" line to `WORKER_PROTOCOL`. Routing
the worker to product-design vs. an ExecPlan vs. a direct patch is **`AGENTS.md`'s job +
the worker's judgment**, not injected guidance.

## Why

- **Templates restrict more than they guide.** A label-keyed template forces a path — a
  `spec` ticket *must* "write a product-spec, then continue into an ExecPlan" — that
  mismatches real work: a small change needs no spec; some work is ExecPlan-only. A
  capable worker right-sizes the process better than a fixed per-stage template can.
- **Evidence — the LIN-29 dogfood (2026-06-25).** A claude worker given *only*
  `WORKER_PROTOCOL` + a self-contained ticket (no template — `director.run` skips
  `compose_worker_prompt` — and no `AGENTS.md` in the target repo) right-sized to a
  single `PLAN.md` + full build + 17 mocked tests + self-QA (an independent codex review
  caught a real reliability bug, fixed with regression tests) + a clean PR. Exactly the
  right process, with no forced spec ceremony. The stage template would have imposed a
  `docs/product-specs/` spec the task did not need.
- **It completes [[0004-ticket-purpose-unit]].** The load-bearing decomposition logic
  (don't-split-by-stage, two-trigger self-contained issuance) already lives in
  `WORKER_PROTOCOL`. The stage templates were left carrying only host-coupled methodology
  pointers (`docs/product-specs/` / `docs/exec-plans/` paths that don't resolve off an
  agent-harness host — the production-host brittleness tracked in the tech-debt tracker).
  Removing them deletes that coupling.
- **It converges the two dispatch paths.** `compose_worker_prompt` was the *only* thing
  that made `director.run` (which skips it) differ from the orchestrator (which applies
  it, `orchestrator.py`). Neutering it makes the two paths send an identical worker prompt
  — one contract, no surprise that a label "did nothing" under `run`.
- **It is Symphony's own model**, which the parity comparison endorsed: one operating
  manual (`WORKFLOW.md` ≈ `WORKER_PROTOCOL`), no per-stage templates; the host carries
  `AGENTS.md`. We stop duplicating a thin, host-coupled slice of the methodology in a
  prompt template and let the real methodology (AGENTS.md + skills) speak for itself.

## Consequences

- **Implemented by** `docs/exec-plans/active/2026-06-25-worker-methodology-surface.md`:
  `WORKER_PROTOCOL` absorbs the `_IMPL_TEMPLATE` craft (conditional); the five stage
  templates are deleted; `compose_worker_prompt` returns the raw prompt; `TAXONOMY` keeps
  `label`/`stage`/`child_types` as dispatch+DAG metadata (the `template` field and the
  host-coupled `methodology_refs`/`output` pointers drop). Tests and docs follow.
- **Explicit contract (Symphony-parity).** A host the Director drives is expected to carry
  **both halves**: `WORKER_PROTOCOL` (injected by the Director) AND `AGENTS.md` + the
  methodology in the repo (self-host has it; a production host gets it via the
  `harness-init` skill). A bare host with no `AGENTS.md` gives the worker only
  `WORKER_PROTOCOL` + its judgment — viable (dogfood-proven) but with ad-hoc doc artifacts,
  which is acceptable: we do not impose harness doc-conventions on a repo that has not
  adopted them.
- **Open dependency to verify at implementation:** the worker runtime **auto-loads
  `AGENTS.md`** at session start (the Claude Code / Codex convention). If a runtime does
  not, the "AGENTS.md directs it" premise needs a fallback (e.g. a one-line pointer in the
  first-turn frame). The ExecPlan verifies this on the claude worker before relying on it.
- **Supersedes** the per-template edits of [[0004-ticket-purpose-unit]] (its *decision*
  survives, carried by `WORKER_PROTOCOL`) and the dev-stage-taxonomy D-18/D-20 **template
  layer** (`docs/product-specs/2026-06-14-dev-stage-taxonomy.md`); the type *registry*
  (label → metadata) stands. Cross-links [[0001-recursive-decomposition]].
