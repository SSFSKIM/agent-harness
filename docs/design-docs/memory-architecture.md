---
status: draft
last_verified: 2026-06-14
owner: harness
---
# Memory architecture — the docs tree is the one brain

## Thesis
This harness has ONE brain: the `docs/` tree, read by progressive disclosure
(AGENTS.md map → subtree indexes → leaf pages, loaded on demand). "Memory" is not
a separate layer or store; it IS the docs library. The dreaming pipeline (the PR2
engine) distills past sessions and AUTHORS into that library — a session-driven
gardener, not the producer of a parallel file.

This supersedes two earlier shapes, both of which re-encoded knowledge that
already has a home in `docs/`:
- the self-contained flat store `.claude/harness/memories/MEMORY.md`
  (dreaming-v2 M5 decision), and
- the `docs/memory/` subtree as a distinct memory layer.

See `dreaming-v2.md` for the engine that stays; only its OUTPUT TARGET changes.

## The dividing line — what docs cannot hold
A design-doc holds present-tense CURATED TRUTH ("the system is X") and is
overwritten toward current truth. The irreducible core of memory is the
opposite: HISTORICAL / append-only / provenance ("on 2026-06-12, session Y taught
us X"). Docs structurally cannot hold time / episode / source. So:
- anything expressible as present-tense curated truth → routes to its docs home;
- anything inherently episodic / provenance → the residual ledger (below).

This line IS the routing rule the dreaming author applies.

## Routing taxonomy (memory content → docs home)
- design / architecture decision → `docs/design-docs/*` + that doc's Decision log
- known limitation / debt → `docs/exec-plans/tech-debt-tracker.md`, `RELIABILITY.md`
- external API knowledge → `docs/references/*`
- feedback rule (given twice → promote) → `docs/DESIGN.md` / `design-docs/core-beliefs.md`
- product intent → `docs/product-specs/*`, `PRODUCT_SENSE.md`
- read-time map / bootloader → `AGENTS.md` (already the map; no separate MEMORY.md)
- RESIDUAL (episodic / provenance only) → the ledger

## The residual ledger (the only surviving "memory" structure)
A small append-only record inside `docs/` for what docs cannot express:
- session provenance — which past session produced which distilled insight (also
  what dreaming needs for dedupe + forgetting);
- an inbox of distilled learnings / feedback not yet promoted to a docs home;
- forgetting state.

Provisional home/name: `docs/journal/` (episodic, append-only). The FINAL name +
shape is the first decision of the follow-on ExecPlan. The sqlite `stage1_outputs`
store stays as internal staging (machinery, not the readable ledger).

## Dreaming's redefined role
Keep the PR2 engine wholesale (Phase 1 extract + no-op gate + usage curation +
sqlite store + discovery — well-designed, see `dreaming-v2.md`). Replace only the
Phase 2 OUTPUT CONTRACT: instead of writing one flat MEMORY.md into a sandbox,
Phase 2 ROUTES each distilled insight to its docs home (placement decided by the
`docs-tree` skill) and records provenance in the ledger. Dreaming becomes the
single session-distillation → docs router; the old imprint/dreamer/gardener loop
converges onto this engine. (The M6 "parallel, not a replacement" decision is
superseded — there is no separate `docs/memory/` loop left to be parallel to.)

## Containment shift (security)
The flat store's post-hoc "revert everything outside the sandbox" check works
because the workspace is disposable. Authoring into the real, git-tracked,
lint-governed docs tree flips containment back to the docs-memory discipline the
threat model already defines (currently dormant): writes path-allowlisted to the
ledger + the routed docs paths, gated by lint (frontmatter / index / D8) + the
T1/T2 poisoning guards, MemoryManager-owned proposal. Net win: output is
git-tracked → reviewable + revertible (closes the dreaming-v2 "not reviewable"
trade-off recorded in its decision log).

## Host adaptation (generality)
The flat self-contained store is the correct FALLBACK for a bare host with no docs
library (Codex's own situation). So the output target is a PLACEMENT decision, not
a hardcode: a host with a docs library (self-hosting) → author into it; a host
with none → fall back to the self-contained store. This matches the existing
`architecture-setup` / `harness-init` host-adaptation principle.

## Open decisions (→ follow-on ExecPlan, M1)
- ledger name/shape (`docs/journal/`?) and how provenance is recorded;
- the exact routing rule encoded in the Phase 2 prompt — the episodic-vs-stable
  judgment is the hard part, and a mis-route either pollutes a clean design-doc
  with history or loses the history;
- migration order for the existing `docs/memory/*` content.
