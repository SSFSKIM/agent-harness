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

## The residual ledger — `docs/journal/` (decided, M1)
A single append-only episodic record at `docs/journal/YYYY-MM.md` (monthly files:
bounded growth, progressive — only recent months load). It is BOTH the home for
what docs cannot hold AND the audit trail of what dreaming did. Each dreaming run
appends one dated block listing every distilled claim and where it went:

    ## 2026-06-14T10:30Z — dream run (sessions: S1, S2)
    - [routed]  design fact "scope check is post-hoc" -> docs/design-docs/dreaming-v2.md
    - [routed]  external "Claude slug = non-alnum->-" -> docs/references/claude-cli-headless-llms.txt
    - [held]    episodic "spent 3h on git rename detection" (no docs home)
    - [held]    feedback 1/2 "user prefers terse commits" (promote at 2x)

A `[routed]` line is provenance only (the content lives in its docs home); a
`[held]` line IS residual content (episodic / un-promoted, kept here). The journal
doubles as the promotion inbox: a `[held]` feedback line promotes to its docs home
on the second sighting. Machine state for dedupe/forgetting stays in sqlite
(`stage1_outputs` + a routed-target marker); the journal is its readable
projection plus the residual itself.

## Routing rule — per CLAIM, not per insight (decided, M1)
Phase 1 raw_memories bundle several claims, so Phase 2 ATOMIZES each into claims
and routes each claim to exactly one home. Ordered; first match wins. Route to a
docs home (1-5) ONLY when the claim is a confident, present-tense, durable truth;
anything uncertain, episodic, or novel-without-a-home falls to the journal (6). A
journal provenance line is appended either way.

1. A durable truth about how OUR system works — design rationale, a reusable
   how-it-works, a decision (+why), or an open question -> the relevant
   `docs/design-docs/*` page: body for rationale/how-it-works, its Decision log
   for a decision, its Open-decisions for an open question. (Absorbs the old
   `docs/memory/{knowledge,adr,openq}`.)
2. A known limitation / landmine / bug / debt -> `docs/exec-plans/tech-debt-tracker.md`
   (a row); a failure-mode/idempotency rule -> `RELIABILITY.md`. (Absorbs the old
   `docs/memory/limitations`.)
3. A fact about an EXTERNAL API/tool we depend on -> `docs/references/*` ONLY if it
   is a full llms.txt-style digest (vendored); a one-off discovered behavior is a
   how-it-works -> step 1, or, if minor, the journal.
4. A recurring user preference / "how we work" correction -> `docs/DESIGN.md` /
   `core-beliefs.md`, but only on the 2nd sighting (feedback-twice -> promote);
   the 1st sighting is a `[held]` journal line with a count.
5. Product intent / what we optimize -> `docs/product-specs/*` / `PRODUCT_SENSE.md`.
6. Otherwise (episodic story, low-confidence, no clear home) -> `docs/journal/`.

This list IS the docs-tree taxonomy after the 2026-06-14 collapse decision
(knowledge/adr/openq folded into design-docs; limitations into the tracker /
RELIABILITY); the `docs-tree` skill is rewritten to match in M4, so dreaming and
manual placement share ONE taxonomy. Before writing to a docs home, check the
claim is not already there (sqlite provenance + a content check) -> dedupe to a
no-op. Conservative by construction: curated docs are touched only on a confident
typed match, so a mis-classification degrades to a harmless journal entry, never
docs pollution.

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

## Open decisions
- (→ ExecPlan M3) migration order for the existing `docs/memory/*` content;
- (→ ExecPlan M2) how the Phase 2 prompt is given the claim-atomization + routing
  rule above so the episodic-vs-durable judgment is reliable — the hard part;
  M1 fixed the rule, M2 proves a model can apply it.
