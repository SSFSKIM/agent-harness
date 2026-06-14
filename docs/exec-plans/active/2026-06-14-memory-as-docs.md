---
status: active
last_verified: 2026-06-14
owner: harness
base_commit: 34896c8
---
# Memory as docs — collapse the memory layer into the one docs brain

## Goal
After this, running the dreaming pipeline (`dream_run.py` / the `dream-rollouts`
skill) over past sessions no longer produces a flat
`.claude/harness/memories/MEMORY.md`. Each distilled insight instead lands in its
natural `docs/` home — a design-doc update, a `tech-debt-tracker.md` row, a
`references/` page — or, when it is purely episodic, an entry in a small residual
ledger inside `docs/`. The `docs/memory/` layer no longer exists (its content
migrated to those homes), and the read-path bootloader is `AGENTS.md`. Observable
end state: distill one real past session and see (a) a concrete routed edit/add in
`docs/`, (b) a provenance entry in the ledger, (c) `python3 plugin/scripts/check.py`
GREEN, (d) no `docs/memory/` tree and no `.claude/harness/memories/` flat store.

## Context
Spec design (the what/why, routing taxonomy, dividing line, containment shift):
`docs/design-docs/memory-architecture.md` — read it first. The dreaming ENGINE
that is reused unchanged (Phase 1 extract, no-op gate, usage curation, sqlite
store, discovery) is `docs/design-docs/dreaming-v2.md` + `plugin/scripts/{dream_*,
memories_*}.py`; only the Phase 2 OUTPUT contract changes here. This reactivates
the docs-memory write-path discipline (T1/T2 poisoning, lint frontmatter/index)
the threat model already defines; the post-hoc sandbox-revert scope check from
dreaming-v2 is retired for self-hosting (kept only as the bare-host fallback).

This plan runs in the agent-harness repo and follows `docs/PLANS.md`.

## Milestones
- [x] M1 (spec) Residual ledger + routing rule. DONE — `memory-architecture.md`
  now fixes the ledger (`docs/journal/YYYY-MM.md`, append-only, `[routed]`/`[held]`
  lines) and the 6-step per-claim routing rule with the journal as the conservative
  default. Acceptance MET: 3 sample claims each routed to exactly one home (debt →
  tracker; external-tool fact → references; a mixed insight SPLIT into a design-doc
  decision + an episodic journal line — the surprise that forced per-claim routing).
- [ ] M2 (PoC) Phase 2 → docs router. Replace the flat-MEMORY.md output with a
  router: Phase 2 reads selected stage-1 outputs and EITHER edits/creates the
  routed `docs/` page OR appends to the ledger (placement via the `docs-tree`
  skill), always recording provenance. Reuse the Phase 1 engine + sqlite store
  unchanged. Acceptance (command → output): `python3 plugin/scripts/dream_run.py`
  over one real past session → a concrete `docs/` edit/add + a ledger provenance
  entry; `check.py` GREEN. Technical contract: the new `consolidate()` output
  target, the `docs-tree` placement seam, the ledger-append function signature.
- [ ] M3 Migrate + retire `docs/memory/`. Move existing content to its docs homes
  per the taxonomy (progress → exec-plans/tracker; limitations → tracker/
  RELIABILITY; archive/sessions → ledger), then delete the layer. Touches
  persistent state → idempotence: gate on a pre-move inventory; re-runnable as a
  no-op once the tree is empty.
- [ ] M4 Rewire read-path bootloader + lint. Bootloader `docs/memory/MEMORY.md` →
  `AGENTS.md` (or a top-level `docs/MEMORY.md`); drop `memory` from
  `hl.MANAGED_ROOTS`; re-point D8 index + `lint_docs.PROTECTED_PATHS` bootloader.
  Acceptance: `check.py` GREEN with zero `docs/memory/` references; the feeder
  (when on) loads from the new bootloader.
- [ ] M5 Security shift + loop convergence. Flip containment from sandbox-revert to
  a docs path-allowlist + lint + T1/T2 poisoning guards; rewrite SECURITY.md's
  `docs/memory`-specific T1/T2/T4/T6/T7 framings to the ledger + routed paths;
  converge the old imprint/dreamer/gardener loop onto the dreaming engine (retire
  the parallel loop — the dreaming-v2 M6 "parallel" decision is superseded).
  review-security in scope.
- [ ] M6 Completion gate. self-review + review-arch + review-reliability +
  review-security (touches the live exec + memory write surface) + codex per
  CLAUDE.md, until all SATISFIED.

## Progress log
- 2026-06-14: plan created off `34896c8` (on the `dreaming-v2` branch, after the
  PR2 audit). Spec design captured in `design-docs/memory-architecture.md`; the
  dreaming-v2 design-doc carries a supersede banner on its output target.
- 2026-06-14: M1 done. Ledger = `docs/journal/YYYY-MM.md` (monthly, append-only,
  doubles as provenance log + promotion inbox); routing rule = 6-step per-claim
  ordered match, journal as conservative default. Both written into
  `memory-architecture.md`. Validated against 3 sample claims.

## Surprises & discoveries
- 2026-06-14 (M1): routing must be per-CLAIM, not per-insight. A Phase 1
  raw_memory bundles several claims; the third validation sample ("we discovered
  git rename detection hid a forgetting cue; fix = --no-renames") split cleanly
  into a DURABLE design decision (→ dreaming-v2.md Decision log) and an EPISODIC
  retrospective (→ journal `[held]`). A per-insight router would have mis-filed
  the whole thing into one bucket. → Phase 2 must atomize before routing (M2).

## Decision log
- 2026-06-14: ledger = `docs/journal/YYYY-MM.md`, append-only monthly files. Why:
  episodic content is inherently chronological; monthly rotation bounds growth and
  stays progressive (only recent months load); append-only avoids rewrite churn.
- 2026-06-14: the journal is the conservative DEFAULT home (rule step 6). Why: a
  mis-classified claim then degrades to a harmless episodic journal entry, never
  pollution of a curated design-doc. Curated docs are touched only on a confident,
  typed, deduped match.
- 2026-06-14: collapse the memory layer into `docs/` (one brain) — most of
  `docs/memory/` already duplicated `docs/`; the only residual docs cannot hold is
  episodic/provenance. Why: the harness thesis is docs-as-brain + progressive
  disclosure (matches the user's proven vault/LLM-wiki model); a separate memory
  layer was cargo-culted from systems without a docs library.
- 2026-06-14: keep the PR2 dreaming ENGINE, change only the Phase 2 output target.
  Why: the extraction/curation/no-op machinery is sound; the defect was the flat
  parallel output, not the pipeline.
- 2026-06-14: converge the two memory loops into one docs-router (supersedes
  dreaming-v2 M6 "parallel"). Why: deprecating `docs/memory/` removes the thing
  the dreaming loop was parallel to.

## Feedback (from completion gate)

## Outcomes & retrospective
