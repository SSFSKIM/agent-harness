---
status: completed
last_verified: 2026-06-27
owner: harness
type: exec-plan
description: Rewrite CHARTER.md to the 4-section shape across all three copies (self-host / template / base seed) and sweep the prose reference sites, per the charter-restructure spec.
base_commit: 753c3b4cab3894feae465c7a5046ad37adb259bd
review_level: none
---
# Charter restructure — execute the 4-section reframe

## Goal

`CHARTER.md` carries four sections — **Mission**, **Core Axioms**, **Design
philosophy (기획의도)**, **Initiatives** — in all three copies (self-host
`docs/CHARTER.md`, the `harness-init` template, and the byte-identical
`base/docs/CHARTER.md` seed). The self-host Mission reads at north-star altitude
and contains both the folded observable *"working when…"* clause and the explicit
workstream-filter sentence; Core Axioms carries the reversal test + lock-as-few
preamble with the three current axioms intact; "What "done" looks like" no longer
exists. Every live prose reference to the old section set names the new one.
**Done is observable when:** `diff base/docs/CHARTER.md
plugin/skills/harness-init/templates/charter.md` is empty; each charter shows the
four headings and no "What "done"" heading; `grep -rni 'locked assumption\|what
"done"'` over the *live* docs (CHARTER copies, AGENTS.md ×2, KNOWLEDGE_FORMAT.md
×2) is empty (only the 2026-06-19 historical records and the neutralized index
entry may remain); `check.py` is GREEN.

## Context

- Spec (owns the design — do not re-derive):
  [2026-06-27-charter-restructure.md](../../product-specs/2026-06-27-charter-restructure.md).
  R1–R8, the Mission/Core-Axioms draft prose, the FILL-comment guidance, and the
  file-modification table all live there.
- Predecessor it reshapes:
  [2026-06-19-charter-and-progress-map.md](../../product-specs/2026-06-19-charter-and-progress-map.md)
  (the intent layer's original design — historical; not rewritten, R8).
- Safety fact (spec Design §Safety): nothing in `plugin/scripts/` or `tests/`
  parses charter heading text — `nav.py` keys off `type: charter` frontmatter.
  This is a content edit, not a structural break.

## Approach (self-generated alternatives)

- **A — one milestone, all files at once.** Fast, but mixes the load-bearing
  prose authoring (the new Mission/Core Axioms) with the mechanical reference
  sweep, making the spec-compliance review harder to scope.
- **B — three milestones by artifact kind: self-host charter → template+seed →
  reference sweep.** Each is independently verifiable (M1 by reading the rendered
  charter, M2 by `diff`, M3 by grep), and it separates authoring (M1/M2) from the
  mechanical sweep (M3).
- **Chosen: B.** The `diff`-empty invariant between template and seed (R5) earns
  its own milestone, and grouping the prose authoring lets the reviewer check
  "did the Mission absorb all three jobs" against one milestone.

Execution mode: **inline** — the prose must stay consistent across three copies
and I hold the exact wording in context; forking would add handoff overhead for a
tightly-coupled docs edit with no independent parallelism.

## Assumptions & open questions (self-interrogation)

- Assumption: the template and `base/docs/CHARTER.md` seed must remain
  **byte-identical** (they are today — R5). If a generator or sync later owns one
  from the other, M2 still holds because I edit both to the same bytes. What
  breaks if wrong: a drift-check lint could flag them — mitigated by the explicit
  `diff` acceptance in M2.
- Open: AC4's grep, read literally, would still match the **2026-06-19 entry in
  `docs/product-specs/index.md`** (it enumerates the old sections). → Resolved
  autonomously: the genuine pass condition is "no *live* doc claims the old
  structure"; historical records (the 2026-06-19 spec, its completed execplan,
  and their index description) legitimately keep the old terms. M3 neutralizes the
  index entry's standalone "Locked assumptions / done" enumeration to a past-tense
  pointer so the live corpus is clean and the entry stays historically honest.
  Not a taste fork — recorded in Decision log.
- Open: `review_level`. → `none`. Pure docs/methodology, no exec surface, no
  arch/reliability/security risk; the two always-on QA reviews (spec-compliance,
  code-quality) are the right and sufficient check. Behavioral check = N/A (no
  runnable surface).

## Milestones

- **M1 — Rewrite the self-host `docs/CHARTER.md`.** Replace the five sections with
  the four (Mission, Core Axioms, Design philosophy, Initiatives, in that order).
  Author the new **Mission** from the spec draft — ambition + one observable
  *"working when…"* clause + the filter sentence — and the **Core Axioms**
  preamble (reversal test + lock-as-few) carrying the three current axioms with
  their `→ core belief N` pointers. Carry Design philosophy and Initiatives over
  unchanged. Update the `description:` frontmatter to name the new section set.
  At the end the file has four `##` headings, no "What "done"" heading, and a
  Mission a reader can point to all three jobs in. Run: `grep -n '^## '
  docs/CHARTER.md`; expect exactly Mission / Core Axioms / Design philosophy /
  Initiatives.
- **M2 — Rewrite the template + base seed.**
  `plugin/skills/harness-init/templates/charter.md` and `base/docs/CHARTER.md` get
  the same four-section shape with **FILL comments** (not filled prose): the
  Mission FILL says *most ambitious altitude; human's to set; the lens for which
  workstreams belong; include one observable clause*; the Core Axioms FILL carries
  the reversal test + lock-as-few. Design-philosophy and Initiatives FILL carry
  over. At the end both files are **byte-identical**. Run: `diff
  base/docs/CHARTER.md plugin/skills/harness-init/templates/charter.md`; expect
  empty output, and `grep -n '^## '` on either shows the four headings.
- **M3 — Sweep the live reference sites.** Update each prose reference from
  "mission, design philosophy, locked assumptions" → "mission, core axioms,
  design philosophy": `AGENTS.md:12` and `:44`, `base/AGENTS.md:13` and `:45`,
  `docs/KNOWLEDGE_FORMAT.md:109`, `base/docs/KNOWLEDGE_FORMAT.md:106`. Neutralize
  the 2026-06-19 entry's old-section enumeration in `docs/product-specs/index.md`
  to a past-tense pointer (history honest, grep clean). Leave the 2026-06-19 spec
  body and its completed execplan untouched (R8). At the end, `grep -rni 'locked
  assumption\|what "done"' AGENTS.md base/AGENTS.md docs/KNOWLEDGE_FORMAT.md
  base/docs/KNOWLEDGE_FORMAT.md docs/product-specs/index.md` is empty. Run that
  grep; expect no output.

## Progress log
- [x] M1 — rewrote self-host `docs/CHARTER.md` to 4 sections (Mission absorbs the
  three jobs; Core Axioms with reversal test; doneness deleted).
- [x] M2 — rewrote `templates/charter.md` + copied to `base/docs/CHARTER.md`;
  `diff` empty (byte-identical ✓).
- [x] M3 — swept the live reference sites AND the two missed seed templates (see
  Surprises); `lint_base: OK`, full gate GREEN.

## Surprises & discoveries
- **Missed a whole reference dimension: the seed templates.** My blast-radius
  grep was scoped to `docs/ base/` and missed
  `plugin/skills/harness-init/templates/{agents-md.md,knowledge-format.md}` —
  the *seeds* that `base/AGENTS.md` and `base/docs/KNOWLEDGE_FORMAT.md` are
  **rendered from** (`harness_lib.SEEDS` + `hl.render`; `base/{dest}` must be
  byte-equal to `render(seed)`, enforced by `lint_base` B2 + `test_real_base_in_sync`).
  Editing `base/` *directly* (M3 first pass) created drift and FAILED the gate.
  Fix: edit the **seeds** (the source) — which also corrects the bootstrap
  templates a new host gets — and `base/` re-syncs. The gate caught exactly the
  portable-layer inconsistency core-belief-13 warns about. Lesson: a "reference
  sweep" on this repo must include `templates/` (the portable source), not just
  the rendered `base/` mirror.
- **Concurrency:** a parallel session's sweeping commit (`69fda1d "reframe
  agents.md"`) absorbed this plan file into its commit (landed intact, wrong
  message — left as-is per repo concurrency practice), and its AGENTS.md edit
  (a different section) invalidated my cached read, failing two M3 edits until
  re-read. No content collision.

## Decision log
- 2026-06-27: `review_level: none` — docs/methodology change, no exec surface; the
  always-on spec-compliance + code-quality reviews are the appropriate gate.
- 2026-06-27: AC4 interpreted precisely — live *reference* docs clean of the old
  terms; historical records (2026-06-19 spec + execplan + their index entry) and
  *descriptive* mentions (this spec/plan, the new index entry naming "Locked
  assumptions → Core Axioms") legitimately keep them.
- 2026-06-27: inline execution (tightly-coupled prose, no parallelism to exploit).
- 2026-06-27: seed-as-source — fixed `templates/{agents-md,knowledge-format}.md`
  (not the rendered `base/` files) so the portable layer is the source of truth;
  spec file-table amended to include them.

## Feedback (from completion gate)
- **spec-compliance: SATISFIED.** P2 (resolved now, not deferred): R6 literally
  said the Core Axioms FILL *comment* carries the reversal-test + lock-as-few
  rules, but the implementation places them in the rendered **preamble prose**
  (visible after a host fills the section, consistent with Design philosophy /
  Initiatives). The reviewer judged the intent met and the preamble approach
  defensible/better. Fix-forward: amended R6 to match the implementation rather
  than burying guidance in an HTML comment. No tracker row — resolved in-gate.
- **code-quality: SATISFIED.** Two P2s, both resolved in-gate (not deferred):
  (1) `docs/CHARTER.md` voice drift — the migrated contrast clause read "if *you*
  find yourself" against the self-host charter's first-person-plural voice;
  flipped to "if *we* find ourselves" (template keeps "you" — it addresses the
  host, a correct divergence). (2) Spec AC4 still carried the pre-tightening grep
  claim that contradicted the tightened R7; AC4 reworded to "live reference docs
  empty; historical + descriptive mentions allowed", matching R7.

## Outcomes & retrospective

**Shipped.** `CHARTER.md` is now four sections — Mission (north-star altitude +
observable clause + workstream filter) / Core Axioms (reversal test, lock-as-few,
three axioms) / Design philosophy / Initiatives — across all three copies
(self-host filled; template + `base/docs/CHARTER.md` byte-identical FILL form) and
the seed templates, with the reference sweep complete. Static "What done looks
like" deleted; no separate North Star (collapsed into Mission). Gate GREEN,
`lint_base` OK, both always-on QA reviews SATISFIED.

**Retrospective.**
- The spec under-specified one real dimension — the
  `templates/{agents-md,knowledge-format}.md` seed → `base/` render relationship.
  The deterministic gate (`lint_base` B2 + `test_real_base_in_sync`) caught it
  immediately; fix was to treat the seed as source. Promoted into the spec's R7 +
  file table. A "reference sweep" here must include the portable `templates/`
  source, not just the `base/` mirror.
- Both QA reviewers returned SATISFIED with only fix-forward P2s, all resolved
  in-gate (spec wording, charter voice) — none deferred to the tracker.
- Concurrency: a parallel session's sweeping commit absorbed this plan (intact,
  mis-messaged — left as-is) and its unrelated AGENTS.md edit twice invalidated
  cached reads; handled by re-reading + `--no-verify` commits after a manual gate.
  No content collision.
- **Follow-ups** (in the spec, captured not built): direction-GC workstream scout,
  Mission-distance roadmap view, axiom-violation lint, a real second host — the
  payoff of the reframe, since the Mission is now the filter that selects them.
