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
- [x] M2 (PoC) Phase 2 → docs router. DONE — new `plugin/scripts/dream_router.py`:
  a READ-ONLY agent (`Read,Glob,LS`) atomizes the selected stage-1 outputs into
  claims and emits a JSON routing plan; a deterministic applicator appends ONLY
  onto an allowlist (tracker rows / design-doc Decision-log + Open-decisions /
  `docs/journal/YYYY-MM.md`), re-redacting secrets, demoting any out-of-allowlist
  target to a journal `[held]` note. `dream_run` picks router (self-hosting) vs the
  sandbox `dream_phase2` (bare host) by `docs/design-docs/` presence. 18 tests.
  Acceptance MET: live Sonnet over one seeded real-session memory → atomized 2
  claims → a `Major` tracker row (durable debt) + a journal `[held]` line
  (episodic), status `routed`; `check.py` GREEN (158 tests). Reuses the Phase 1
  engine + sqlite store unchanged.
- [x] M3 Migrate + retire `docs/memory/`. DONE — `knowledge/recursion-guard.md`
  → `docs/design-docs/` (registered); `archive/sessions/*` → `docs/journal/archive/`;
  `limitations/progress-staleness` → a tracker row (the durable rule);
  `openq/memory-loop-redesign` → resolved by this pivot, its still-open READ-PATH
  question moved to `memory-architecture.md` Open decisions; `openq/tracker-fixed-
  traceability` + `progress/current.md` dropped (already a tracker row / the
  completed ExecPlans ARE that history). `docs/journal/2026-06.md` records the
  migration provenance. `docs/memory/` now holds only `MEMORY.md` (the bootloader,
  M4). Gate GREEN. Residual dangling `memory-loop-redesign` refs in `agent-harness.md`
  + `SECURITY.md` are cleared by their M4/M5 rewrites.
- [x] M4 Rewire bootloader + lint (self-host scope). DONE — bootloader role folded
  into AGENTS.md (operating-model step 1: orient from active ExecPlans + design-docs
  index + latest journal); self-host `docs/memory/MEMORY.md` + the empty tree
  deleted. `tidy_stop` (the live Stop hook) sentinel repointed
  `docs/memory/MEMORY.md` → `docs/design-docs/agent-harness.md` (else deleting the
  bootloader silently disables the gate) + its test. Journal lint: `journal/` added
  to SIZE_EXEMPT + D4-stale-exempt (append-only). `docs-tree` skill + `agent-harness.md`
  taxonomy rewritten to the collapsed homes (now ONE taxonomy with the router). The
  host-generic MANAGED_ROOTS / PROTECTED_PATHS / MEMORY.md lint handling is KEPT
  (still valid for ported hosts — see the scope decision). Gate GREEN (158 tests).
- [x] M5 Security shift + loop convergence. DONE (most of the "shift" was absorbed
  by M2's read-only-agent + applicator = containment by construction). SECURITY.md
  rewritten: status banner = the memory-as-docs router (primary) + the sandbox
  fallback, reactivating T1/T2/T4/T6/T7; **T2** split into the router (no sandbox to
  revert — the read-only agent can't write, the applicator only appends onto an
  allowlist; residual = a bounded, git-visible, revertible misleading entry) + the
  sandbox fallback (the post-hoc filesystem scope check); **T7** now covers the
  router agent's DATA guard (`router_system.md`). The old feeder/imprint/dream/garden
  loop is re-documented as dormant→retired across AGENTS / ARCHITECTURE /
  agent-harness / SECURITY; the actual code retirement is the portable follow-on
  (scope A). Last dangling `memory-loop-redesign` ref (SECURITY banner) cleared. Gate
  GREEN (158 tests).
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
- 2026-06-14: M2 done (`dream_router.py` + router templates + 18 tests + dream_run
  wiring + S1 allowlist). Live Sonnet PoC PASSED (one seeded real-session memory →
  1 Major tracker row + 1 journal `[held]`, status `routed`); gate GREEN.
- 2026-06-14: M3 done. `docs/memory/` content migrated to docs homes (recursion-guard
  → design-docs; sessions → journal/archive; limitations → tracker row; the
  memory-loop-redesign open Q → memory-architecture Open decisions) and the layer
  emptied to just `MEMORY.md`. Gate GREEN (158 tests). Finding: the lint does not
  validate cross-doc links, so dangling refs to deleted pages don't fail the gate —
  cleared by the swept living docs; the two in agent-harness.md/SECURITY.md ride
  their M4/M5 rewrites.
- 2026-06-14: M4 done (self-host scope). Bootloader → AGENTS.md; MEMORY.md + tree
  deleted; tidy_stop sentinel repointed to agent-harness.md (+ test); journal lint
  exemptions; docs-tree + agent-harness taxonomy collapsed. Gate GREEN. The
  agent-harness + AGENTS dangling memory-loop refs are cleared (the SECURITY one
  rides M5).
- 2026-06-14: M5 done. SECURITY.md rewritten (banner + T2 split router/sandbox + T7
  router DATA guard); old loop re-documented dormant→retired; last dangling ref
  cleared. Gate GREEN. Docs-only (containment already built in M2).

## Surprises & discoveries
- 2026-06-14 (M1): routing must be per-CLAIM, not per-insight. A Phase 1
  raw_memory bundles several claims; the third validation sample ("we discovered
  git rename detection hid a forgetting cue; fix = --no-renames") split cleanly
  into a DURABLE design decision (→ dreaming-v2.md Decision log) and an EPISODIC
  retrospective (→ journal `[held]`). A per-insight router would have mis-filed
  the whole thing into one bucket. → Phase 2 must atomize before routing (M2).
- 2026-06-14 (M2): the live router self-deduped WITHOUT being given the dedupe as
  code. Fed a claim whose durable fact already lived in `dreaming-v2.md`, the agent
  Read that doc, found it ("already recorded in dreaming-v2.md line 62"), and chose
  a journal `[held]` provenance note over re-routing it into the design-doc — dedupe
  is emergent from the read-only-with-Read posture, not just the applicator's
  substring check.
- 2026-06-14 (M4): `docs/memory` is baked into the PORTABLE plugin layer, not just
  self-host docs — `scaffold.py` seeds the tree + bootloader, `feeder_*`/`imprint_*`
  embed its paths, `tidy_stop` (the live Stop hook) uses `docs/memory/MEMORY.md` as
  its "is-a-harness-repo" sentinel, and ~5 tests encode it. Because `docs-tree` is a
  shared skill, making the self-host coherent inevitably edits portable behavior.
  Deleting the bootloader would have silently disabled the gate (the sentinel).

## Decision log
- 2026-06-14: ledger = `docs/journal/YYYY-MM.md`, append-only monthly files. Why:
  episodic content is inherently chronological; monthly rotation bounds growth and
  stays progressive (only recent months load); append-only avoids rewrite churn.
- 2026-06-14: the journal is the conservative DEFAULT home (rule step 6). Why: a
  mis-classified claim then degrades to a harmless episodic journal entry, never
  pollution of a curated design-doc. Curated docs are touched only on a confident,
  typed, deduped match.
- 2026-06-14 (user, flagged): docs/memory is NOT mostly-duplicate — the docs-tree
  skill routes 4 first-class kinds (knowledge/adr/limitations/openq) into it. Chose
  MAXIMAL COLLAPSE: fold all into existing docs homes (knowledge/adr/openq →
  design-docs facets; limitations → tracker/RELIABILITY), leaving only docs/journal
  as residual; the docs-tree taxonomy + the routing rule are now ONE list. Why: the
  one-brain=docs thesis; a separate memory namespace was redundant once each kind
  has a docs home. This unifies M2's routing homes, M3's migration targets, and the
  M4 docs-tree rewrite.
- 2026-06-14 (M2): Phase 2 output = a READ-ONLY agent that emits a routing plan +
  a deterministic applicator that applies it (the threat-model "MemoryManager
  proposal tool" pattern), NOT an agent that writes docs directly. Why: the agent
  has no Write/Edit tool, so a transcript injection has no mechanism to write
  anything; the applicator only appends onto an allowlist. This is containment BY
  CONSTRUCTION and absorbs most of M5's "containment shift" — M5 narrows to the
  SECURITY.md rewrite + retiring the old loop. The old sandbox scope-check
  (`dream_phase2`) is kept only as the bare-host fallback.
- 2026-06-14: collapse the memory layer into `docs/` (one brain) — most of
  `docs/memory/` already duplicated `docs/`; the only residual docs cannot hold is
  episodic/provenance. Why: the harness thesis is docs-as-brain + progressive
  disclosure (matches the user's proven vault/LLM-wiki model); a separate memory
  layer was cargo-culted from systems without a docs library.
- 2026-06-14 (M4, scope): the pivot is SELF-HOST scope; the portable harness keeps
  `docs/memory` for now. Why: `docs-tree`/`scaffold`/`feeder`/`imprint` + their tests
  bake in `docs/memory`, so full propagation (scaffold seeds → journal/design-docs,
  retiring the dormant feeder/imprint, the bare-host default) is a separate body of
  work with its own design — tracked as a follow-on ExecPlan (tracker row added). The
  self-host's live surface (tidy_stop sentinel, bootloader, taxonomy) is fully cut
  over; the host-generic MEMORY.md lint handling stays valid for ported hosts.
- 2026-06-14: keep the PR2 dreaming ENGINE, change only the Phase 2 output target.
  Why: the extraction/curation/no-op machinery is sound; the defect was the flat
  parallel output, not the pipeline.
- 2026-06-14: converge the two memory loops into one docs-router (supersedes
  dreaming-v2 M6 "parallel"). Why: deprecating `docs/memory/` removes the thing
  the dreaming loop was parallel to.

## Feedback (from completion gate)

## Outcomes & retrospective
