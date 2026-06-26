---
status: active
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
- [ ] M1 — rewrite self-host CHARTER.md
- [ ] M2 — rewrite template + base seed (byte-identical)
- [ ] M3 — sweep live reference sites

## Surprises & discoveries

## Decision log
- 2026-06-27: `review_level: none` — docs/methodology change, no exec surface; the
  always-on spec-compliance + code-quality reviews are the appropriate gate.
- 2026-06-27: AC4 interpreted precisely — live corpus clean of the old terms;
  historical records (2026-06-19 spec + execplan + their index entry) keep them.
  M3 neutralizes the index entry so the live grep is literally empty.
- 2026-06-27: inline execution (tightly-coupled prose, no parallelism to exploit).

## Feedback (from completion gate)

## Outcomes & retrospective
