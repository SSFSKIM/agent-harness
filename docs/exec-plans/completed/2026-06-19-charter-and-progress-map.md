---
status: completed
last_verified: 2026-06-19
owner: harness
type: exec-plan
base_commit: a11091efa56051dee2e174c834c3601e2a833ee9
review_level: standard
description: ExecPlan that built the charter + derived progress-map intent layer — authored CHARTER, KF v1.1 phase key, and nav.py roadmap/map.
---
# Charter & derived progress map — build

## Goal

Ship the intent layer from
[the spec](../../product-specs/2026-06-19-charter-and-progress-map.md): one
authored top-level `docs/CHARTER.md` (`type: charter`; Mission / Done / Design
philosophy (기획의도) / Locked assumptions / Initiatives) wired into Orient, plus an
all-derived progress map — `python3 plugin/scripts/nav.py roadmap` projects
initiative→phase→`status:` from a new optional `phase` frontmatter key (KF v1.1)
and the typed link graph, with pivots surfaced inline from supersedes/refines
edges. Done = `nav.py roadmap` prints ≥2 real initiatives with phase-ordered
specs/plans and live status; the charter exists and is the Orient anchor; the
`phase` key + `charter` type + charter template propagate to ported hosts; full
gate (`python3 plugin/scripts/check.py`) GREEN.

## Context

- Spec (owns the design): `docs/product-specs/2026-06-19-charter-and-progress-map.md`.
- Predecessor (the typed graph this projects over):
  `docs/product-specs/2026-06-19-nav-derived-hierarchy.md` →
  `plugin/scripts/nav.py` (`relations`/`INVERSE`/`_infer_rel`/`tree`).
- Format contract to bump: `docs/KNOWLEDGE_FORMAT.md` + host variant
  `plugin/skills/harness-init/templates/knowledge-format.md` (NOT byte-identical
  — keep the template's host-agnostic wording + `{{TODAY}}`; apply the same
  *semantic* v1.1 additions to both).
- Seeding: `plugin/scripts/scaffold.py` `SEEDS` + `tests/test_scaffold.py`.
  Charter is a seeded FILL template (like `AGENTS.md`), NOT a MACHINE_DOC /
  PROTECTED_PATH (`hl.MANAGED_DOCS` unchanged). A fresh host must stay lint-GREEN,
  so the template's links point only to seeded docs (`core-beliefs.md`) or are
  FILL placeholders.
- Orient wiring: self-host `AGENTS.md` step 1 + `templates/agents-md.md`.
- `lint_docs.py` does NOT validate `type` values and `charter` is not in an
  INDEXED_DIR → no lint change for the new type/key (D3 stays permissive).

## Approach (self-generated alternatives)

- A: `phase` as a structured frontmatter key + `nav.py roadmap` group-by;
  parent linkage reused from the existing `implements`/`refines` edges. — keeps
  the projection thesis, one new optional key, no new graph machinery.
- B: a `parent`/`roadmap` declared-edge frontmatter system. — richer, but
  re-opens declared typed edges (deferred KF minor) and adds hand-maintained
  structure the nav thesis rejects.
- Chosen: **A** — minimal, consistent with `nav-derived-hierarchy`, and matches
  the methodology's already-stated "phase as a structured field, roadmap as a
  derived view" (PLANS.md, product-design skill). (Mirrors spec NG5.)

## Assumptions & open questions

- Assumption: `read_frontmatter` reads `phase` as a scalar with no change (it is
  flat-but-list-aware). Breaks if `phase` ever needs a list — it does not.
- Assumption: exec-plans that implement a spec markdown-link it, so they inherit
  `phase` via the `implements` edge; plans that do not link a spec land in the
  advisory `(unphased)` bucket. Acceptable — backfill puts `phase` on specs, not
  on all 34 plans.
- Open: roadmap row universe → resolved autonomously as **product-spec +
  exec-plan only** (the "what/how" tier); design-docs/ADRs appear only as pivot
  annotations, not rows. Keeps the map about *work progress*.
- Open: phase string grammar → `<initiative>/<NN>-<slug>` (NN orders within an
  initiative; bare `<initiative>` = umbrella, sorts first; non-numeric NN sorts
  last). Documented in KNOWLEDGE_FORMAT §2.2.

## Milestones

- **M1 — KF v1.1 (format).** Add `phase` to KNOWLEDGE_FORMAT §2.2 optional keys
  (scalar, the roadmap group-by, grammar note) and `charter` to the §2.3 type
  vocabulary; bump §1/§6/conformance to **v1.1**. Apply the same semantic edits
  to the host template (preserving its host-agnostic wording). `build_index`
  records a `phase` field. At the end: both format docs read v1.1, `nav.py
  catalog --json` shows a `phase` field; run `python3 plugin/scripts/check.py`;
  expect GREEN.
- **M2 — charter + Orient + portability.** Author `docs/CHARTER.md` (5 sections,
  the human-confirmed philosophy/assumptions). Add
  `templates/charter.md` (FILL, `{{PROJECT}}`/`{{TODAY}}`, links only to seeded
  docs). Wire `scaffold.py` `SEEDS` (`charter.md` → `docs/CHARTER.md`) +
  `test_scaffold.py` (seeded-files list + propagation). Name the charter in the
  Orient step 1 and Map of self-host `AGENTS.md` and `templates/agents-md.md`. At
  the end: a fresh scaffold produces a lint-GREEN host with `docs/CHARTER.md`;
  run `check.py` + `python3 -m pytest tests/test_scaffold.py` (or unittest);
  expect GREEN.
- **M3 — `nav.py roadmap`.** Add `roadmap(records)` (group product-spec/exec-plan
  by resolved phase→initiative; plan inherits phase via `implements`; pivots from
  supersedes/refines via `INVERSE`), `_emit_roadmap`, and the `roadmap` CLI
  subcommand (`--json`). Document it in `docs-nav/SKILL.md`. Add `test_nav.py`
  cases: grouping, status, phase inheritance, unphased bucket, pivot annotation,
  JSON, empty corpus. At the end: `nav.py roadmap` renders; run the gate; expect
  GREEN.
- **M4 — dogfood backfill.** Add `phase:` to the parent + child product-specs of
  the two main initiatives (Symphony orchestration, knowledge-format) so the map
  renders real phases with live status; author the charter's Initiatives links to
  the two parent specs. At the end: `nav.py roadmap` shows ≥2 initiatives with
  phase-ordered children and correct statuses; gate GREEN.

## Progress log
- [x] (2026-06-19) M1 — KF v1.1: `phase` key + `charter` type in both format docs;
  `build_index` records `phase`. Gate GREEN; `catalog --json` shows `phase`.
- [x] (2026-06-19) M2 — `docs/CHARTER.md` authored (5 sections); `templates/charter.md`
  FILL seed; `scaffold.py` SEEDS + `test_scaffold.py`; Orient step 1 + Map in
  self-host AGENTS.md and the host template. Verified: fresh-host scaffold seeds
  CHARTER, no unrendered tokens, host lint OK.
- [x] (2026-06-19) M3 — `nav.py roadmap` (`roadmap`/`_phase_key`/`_emit_roadmap`
  + CLI), phase inheritance via `implements`, pivot annotation; 9 roadmap tests;
  `docs-nav` SKILL documents it. Gate GREEN; empty corpus safe.
- [x] (2026-06-19) M4 — `phase:` backfilled into 22 product-specs (metadata-only,
  no `last_verified` bump). `nav.py roadmap` renders 3 initiatives (symphony,
  knowledge-format, methodology) with phase-ordered children + live status.

## Surprises & discoveries
- **Dogfooding caught a pivot-noise bug (M4).** The first `roadmap` render flooded
  every parent spec with `[refined-by …]` (15 on the orchestration parent) plus
  duplicates — because `product-spec→product-spec` infers `refines`, and a parent
  linked by all its children accumulates the inverse. Fix: a pivot is a
  **supersession only** (a newer page → an `archived` page of its kind), never a
  structural `refines`; `supersedes` generalized from adr→archived-adr to any
  same-type→archived-same-type; pivots deduped. Roadmap is now clean. Spec R6
  narrowed to match.
- **R7 "byte-identical" was wrong.** The host `knowledge-format.md` template is a
  host-agnostic *variant* (generic examples, `{{TODAY}}`), not a byte copy of
  canon — there is no test enforcing equality. Applied the v1.1 additions to both
  with their own wording; corrected R7 + the design table.
- The `(unphased)` bucket is mostly historical exec-plans whose Context does not
  markdown-link their spec, so they cannot inherit a phase — honest, advisory.
  Backfilling `phase` onto plans (or linting plan→spec links) is possible future
  work, not this scope.

## Decision log
- 2026-06-19: row universe = product-spec + exec-plan only — a roadmap is about
  work progress; philosophy/decision docs surface as pivots, not rows.
- 2026-06-19: charter is a seeded FILL template, not a MACHINE_DOC — its content
  is host-specific/authored; only existence propagates (spec contract).

## Feedback (from completion gate)

Reviews — all SATISFIED: review-arch + review-reliability (Claude personas,
parallel); review-spec-compliance + review-code-quality. The Codex spec-compliance
run (gpt-5.5/high per CLAUDE.md) stalled mid-investigation (output froze, no
verdict), so per the CLAUDE.md fallback both QA reviews ran as Claude
general-purpose agents carrying the persona rubric (the dedicated Claude
spec-compliance/code-quality subagents are not registered this session).

P2s fixed inline (cheap, self-introduced correctness):
- (code-quality) the multi-spec earliest-phase tie-break (`phase_of`'s `min`
  branch) was the one untested new branch → added
  `test_multispec_plan_inherits_earliest_phase_deterministically` (a plan linking
  beta before alpha lands under alpha). `roadmap()` docstring corrected to
  superseded-by only.
- (arch) `AGENTS.md` Map row said "KF v1.0" and omitted `phase` after the v1.1
  bump → updated to v1.1 + `phase`.
- (arch) `CHARTER.md`/spec/`docs-nav` cited `KNOWLEDGE_FORMAT §2.2` for the
  "structure = projection" thesis, but §2.2 had no such sentence → added the
  thesis line to §2.2 in both the canonical and host KF docs; the pointers now land.
- (reliability) a plan implementing multiple specs inherited a link-order-dependent
  phase → `phase_of` now picks the earliest phase deterministically (min by
  initiative/`NN`); spec contract updated.
- (spec-compliance, Codex interim) `roadmap --json` emission path was untested →
  added JSON-emit + round-trip assertions to `TestNavRoadmap.test_render_and_empty_corpus`.

P2s deferred to `tech-debt-tracker.md` (proposed rules/conventions, non-blocking):
- generalize RELIABILITY R12 to the nav.py projection surface (totality contract);
- KNOWLEDGE_FORMAT §2.2 `phase` `NN` uniqueness-within-initiative convention;
- decide open-vs-curated roadmap initiative set.

## Outcomes & retrospective

Shipped the intent layer in two halves, as specced. **Authored seed:**
`docs/CHARTER.md` (`type: charter`, 5 sections) is now the Orient anchor — named
first in both the self-host `AGENTS.md` step 1 and the host `agents-md.md`
template, and propagated to ported hosts as a FILL template (`charter.md` +
scaffold seed + test). **Derived everything-else:** KF bumped to **v1.1**
(optional `phase` key + `charter` type, in both the canonical and host KF docs,
lint still permissive), and `nav.py roadmap` projects the work tier into
initiative→phase→`status:` live from frontmatter + the typed graph — delivering
the methodology's long-unkept "roadmap is a derived view" promise. Dogfooded by
backfilling `phase:` onto 22 product-specs: `nav.py roadmap` renders the real
Symphony / knowledge-format / methodology initiatives with phase-ordered children
and live status, nothing hand-maintained.

Behavioral check: ran (CLI surface) — `nav.py roadmap` (+ `--json`), fresh-host
scaffold lints GREEN with a seeded CHARTER, `catalog --json` carries `phase`.

What dogfooding bought us (the highest-value moment): the first `roadmap` render
exposed that inferred `refines` is pure noise as a pivot signal (a parent spec
flooded with 15 duplicated `[refined-by]` edges). That forced a sharper, correct
definition — **a pivot is a supersession only** (a newer page → an `archived`
page of its kind) — and generalized `supersedes` beyond ADRs. The map is now
clean and a pivot annotation means something. Lesson re-confirmed: build the
consumer and run it on real data before declaring a projection done.

Follow-ups (recorded, not started): 3 proposed-rule P2s in the tracker (R12-for-nav
totality; `phase` `NN`-uniqueness convention; open-vs-curated initiative set);
historical exec-plans sit in `(unphased)` because their Context doesn't
markdown-link their spec — backfilling plan→spec links (or a lint) is future work.
