---
status: stable
last_verified: 2026-06-19
owner: harness
phase: knowledge-format/04-charter-roadmap
type: product-spec
tags: [methodology, knowledge-format, roadmap, charter, nav]
description: A top-level authored CHARTER (mission + locked human-AI assumptions, the Orient anchor against long-session intent-drift) plus a derived progress map — nav.py projects initiative/phase/status from frontmatter instead of a hand-maintained roadmap.
---
# Charter & derived progress map (the intent layer)

> **Update (2026-06-27):** the charter's *section structure* was reframed by
> [Charter restructure](2026-06-27-charter-restructure.md) (5 sections → 4;
> Locked assumptions → Core Axioms; doneness folded into Mission). This spec
> remains the record of the intent layer's original design.

## Problem

In long agent sessions the work fans out — subproject after subproject — and the
**initial big picture, planning, and planning intent get buried.** A session that
started with a clear goal drifts, because nothing durable holds the original
intent in front of every turn. The fix the methodology already endorses is a
strong **upfront human specification**: the more sharply the early intent and the
human↔AI assumptions are surfaced, the less misalignment accumulates downstream.
Two things are unsatisfied today:

1. **No top-level intent anchor.** This repo has principles (`design-docs/`),
   per-capability specs (`product-specs/`), and execution (`exec-plans/`), but no
   single durable doc stating *why this project exists, what "done" is at the
   highest level, and which assumptions are locked.* It is the "ultimate goal"
   layer `CLAUDE.md`'s metacognition rule refers to. The closest artifact is
   buried at `docs/superpowers/specs/2026-06-12-agent-harness-v1-design.md`. An
   agent has nothing to re-read at Orient to re-anchor on intent.

2. **The derived roadmap is promised but unbuilt.** `PLANS.md` §"When" (the
   recursive-decomposition paragraph) says "a parent spec just indexes its
   children and any roadmap is a **derived view** of them," and the
   `product-design` skill says to "tag each child with its phase/slice as a
   **structured field** so the roadmap is a derived view (group-by), never
   hand-maintained." Yet **every phase label lives in prose today** ("Phase 4 첫
   슬라이스", "재배치(2026-06-16)…") inside `product-specs/index.md`. There is no
   `phase` frontmatter field, so `nav.py` cannot group-by and no command answers
   "where are we, against the macro design, right now." The promise is unkept.

The shape of the answer follows the thesis the nav work already proved
(`KNOWLEDGE_FORMAT.md` §2.2, `2026-06-19-nav-derived-hierarchy.md`): **structure
is a projection of metadata, not a hand-maintained artifact.** So exactly one
thing is authored — the charter (the irreducible human seed) — and the
roadmap, the progress state, and the pivot/evolution log are all *derived*.

## Requirements

- **R1 — Repo charter.** `docs/CHARTER.md` exists with `type: charter` and these
  five sections:
  - **Mission** — why the repo exists / the ultimate goal.
  - **What "done" looks like** — top-level success, observable.
  - **Design philosophy (기획의도)** — the connected product-conception reasoning:
    *why the product is shaped this way* and the deliberate tradeoffs consciously
    taken. Each strand is one line + a pointer to the design-doc/ADR that
    elaborates (depth stays behind the pointer — map, not encyclopedia; no new doc
    type). This is the layer **pivots mutate**, so it pairs with the derived
    evolution view (R6).
  - **Locked assumptions** — the fixed **axioms** taken as given and *not
    re-litigated* (the anti-drift floor). Distinct in kind from Design philosophy:
    an axiom is a given we don't revisit; a philosophy strand is *chosen reasoning*
    we believe in but that may mature or pivot. (A strand that turns out to be
    truly fixed graduates into an assumption; a "given" we find ourselves
    re-arguing was really a philosophy strand.)
  - **Initiatives** — one line per major initiative, each linking its parent spec.

  Verifiable: file exists, all five sections present, gate GREEN.
- **R2 — Orient wiring.** The self-host `AGENTS.md` operating-model step 1
  ("Orient") names the charter as the first read; the `harness-init`
  `agents-md.md` template does the same (host-agnostic wording). Verifiable: both
  reference the charter.
- **R3 — `charter` type.** `charter` joins the `type` vocabulary in
  `KNOWLEDGE_FORMAT.md` §2.3 with its meaning; lint treats it like any other type
  (permissive — D3 unchanged). Verifiable: KF doc lists it; the charter lints
  clean.
- **R4 — `phase` key.** `phase` is documented in `KNOWLEDGE_FORMAT.md` as an
  optional scalar (convention `<initiative>/<NN>-<slug>`, e.g.
  `symphony/04-worker-authority`; a bare `<initiative>` is allowed). Lint stays
  permissive; `read_frontmatter` reads it (scalar — already supported). A spec or
  plan may carry it. KF bumps to **v1.1** (additive: one optional key + one type
  value). Verifiable: KF doc documents it and the version; a tagged page
  round-trips through nav.
- **R5 — `nav.py roadmap`.** A new command renders a derived progress map grouped
  by **initiative → phase**, each row a spec/plan with its `status:`, projected
  live from frontmatter + the typed link graph (directory-independent, nothing
  persisted). A plan lacking `phase` **inherits** it from the spec it
  `implements` (via the existing `relations()` edge). `--json` for machines.
  Verifiable: command groups real specs by phase with live status.
- **R6 — Pivots visible (the evolution view).** The roadmap annotates a node with
  its inferred `superseded-by` edge (deduped, reusing nav's `INVERSE`), so a
  genuine design pivot shows inline (e.g. `spec X  [superseded-by Y]`) and the
  rationale is one link away. A **pivot is a supersession** — a newer page
  retiring an `archived` page of its own kind — *not* a structural `refines`
  (a child building on a parent), which floods the map with noise (dogfooding,
  M4). `supersedes` is generalized from adr→archived-adr to any same-type page →
  an archived same-type page. This is the derived counterpart to the charter's
  **Design philosophy** strands — *how the 기획의도 moved over time*. No separate
  hand-maintained changelog. Verifiable: a superseded node renders its successor.
- **R7 — Portability (belief 13).** The `phase` key + `charter` type ship via
  `KNOWLEDGE_FORMAT.md` (a MACHINE_DOC), with the `harness-init` host template
  carrying the **same semantic additions** (the template is a host-agnostic
  variant — generic examples + `{{TODAY}}` — *not* byte-identical to canon); the
  `roadmap` command lives in `plugin/scripts/nav.py` so it travels; a **`charter`
  host template** is seeded by `harness-init` (FILL placeholders, idempotent
  never-overwrite — like `AGENTS.md`, *not* a verbatim MACHINE_DOC). Verifiable:
  scaffold seed + propagation test; a fresh-scaffolded host lints GREEN.
- **R8 — Dogfood backfill.** This repo's `docs/CHARTER.md` is authored, and the
  existing parent specs + their children carry `phase:` so `nav.py roadmap`
  renders the real initiatives (Symphony orchestration, knowledge-format) with
  live status. Verifiable: `nav.py roadmap` shows ≥2 initiatives with
  phase-ordered children and correct statuses.

## Design

**The split.** One authored seed (the charter) + four derived views (roadmap,
progress state, parent linkage, pivot log). Nothing about progress is
hand-maintained. The charter itself splits two kinds of content by *volatility*:
**Locked assumptions** are axioms (stable — they do not appear in the evolution
view because they do not move), while **Design philosophy (기획의도)** is chosen
reasoning that matures — each philosophy strand is exactly what a pivot mutates,
so the strand (authored, current) and the derived evolution view (R6, *how it
moved*) are two halves of the same thing.

**Components & changes**

| Artifact | Change |
|---|---|
| `docs/CHARTER.md` | **New, authored** (`type: charter`) — the Orient anchor. |
| `docs/KNOWLEDGE_FORMAT.md` | Add `charter` to the §2.3 type vocabulary; add `phase` to the optional-keys table; bump §6 to **KF v1.1**. Lint stays permissive. |
| `plugin/skills/harness-init/templates/knowledge-format.md` | Same semantic bump (host-agnostic variant — generic examples + `{{TODAY}}`, not byte-identical). |
| `plugin/skills/harness-init/templates/charter.md` | **New** host template (FILL placeholders for Mission / Done / Locked assumptions / Initiatives). |
| `plugin/skills/harness-init/scaffold.py` (+ `tests/test_scaffold.py`) | Seed `docs/CHARTER.md` from the template (idempotent, never overwrite); test it propagates. |
| `plugin/scripts/nav.py` | `roadmap(records)` builder + `_emit_roadmap` + CLI `roadmap` subcommand; phase inheritance via the `implements` edge; pivot annotation reusing `relations()`/`INVERSE`. |
| `tests/test_nav.py` | roadmap tests: grouping, status, phase inheritance, pivot annotation, `--json`, empty corpus. |
| `plugin/skills/docs-nav/SKILL.md` | Document `roadmap` in the intent→command table and the "inferred relationships" section. |
| `AGENTS.md` + `plugin/skills/harness-init/templates/agents-md.md` | Orient step 1 names the charter; add it to the Map table. |
| parent/child specs (Symphony, knowledge-format) | Backfill `phase:`. |

**Contracts**

- **`phase` format:** `<initiative>/<NN>-<slug>` or bare `<initiative>`. The
  roadmap groups by the initiative prefix (before `/`) and orders within an
  initiative by the numeric `NN`. A free-form value with no `/` is its own
  single-phase initiative.
- **Roadmap projection:** read frontmatter → bucket specs/plans by phase
  initiative → order phases by `NN` → each node renders `path · type · status`
  plus any inferred pivot edge. A plan with no `phase` inherits the phase of the
  spec it `implements` (the earliest phase, by initiative/`NN`, if it implements
  several — deterministic, not link-order); if still none, it lands in an advisory
  **`(unphased)`** bucket. Live per call, nothing persisted (consistent with nav).
- **Charter is a seeded template, not a MACHINE_DOC:** its *content* is
  host-specific and authored, so it is seeded once (FILL placeholders) and never
  overwritten — the byte-stable MACHINE_DOC path is for the format spec, not the
  charter. Existence is seeded; content is never gate-enforced (NG1).

**Errors & edges:** malformed `phase` → bucket under the raw value (fail-soft,
never an error); empty corpus → empty roadmap, no crash (same guard as `tree`,
`_emit_tree`'s `trees[0] if trees else None`); a `charter`-typed page with no
links is fine (it is the root anchor, not a graph leaf).

## Non-goals

- **NG1 — No enforcement.** `phase` and the charter are never a gate; presence
  is advisory, content permissive (consistent with D3 and core-belief 8).
- **NG2 — No query language.** `roadmap` is one more nav projection, not a DSL.
- **NG3 — No viz.html / rendered graph.** Agent-facing text + JSON only
  (`okf-comparison.md` rationale — navigation is query, not a picture).
- **NG4 — No auto-generated charter.** The charter is the irreducible authored
  seed; only the roadmap/state/pivot views are derived.
- **NG5 — No `parent` frontmatter field.** Parent linkage is the existing
  markdown link — `relations()` already infers `refines`/`implements`. Declared
  typed-edge keys remain deferred (a later KF minor, not this one).
- **NG6 — No file reorg.** Structure stays a projection; directories unchanged.
- **NG7 — No hand-maintained `logs.md`/changelog.** Pivots derive from
  `supersedes`/`refines` edges + ADR rationale + git history.

## Acceptance criteria

1. `docs/CHARTER.md` exists (`type: charter`) with Mission / Done / Locked
   assumptions / Initiatives; the self-host `AGENTS.md` and the host `agents-md.md`
   template Orient steps point to it; gate GREEN.
2. `KNOWLEDGE_FORMAT.md` (and the host template variant) document the
   `charter` type and the `phase` key and read **KF v1.1**; D3 stays permissive;
   existing format/lint tests stay green.
3. `python3 plugin/scripts/nav.py roadmap` prints ≥2 real initiatives (Symphony,
   knowledge-format), each with phase-ordered specs/plans and live `status:`;
   `--json` validates as the same structure.
4. A superseded node renders its `superseded-by` edge inline in the roadmap.
5. `tests/test_scaffold.py` confirms the charter template propagates to ported
   hosts; the new `nav.py roadmap` tests pass; the full gate
   (`python3 plugin/scripts/check.py`) is GREEN.

## Handoff

Build via the `execplan` skill (this is the spec; the plan owns the build). The
one human touch is **R1's Locked assumptions** — the agent drafts `CHARTER.md`,
but the locked human↔AI assumptions are the rare `PRODUCT_SENSE.md` call the
human confirms. Suggested phasing for the ExecPlan: **(A)** format + charter +
Orient + portability (R1–R4, R7); **(B)** `nav.py roadmap` + pivot view +
dogfood backfill (R5, R6, R8). Predecessor: `2026-06-19-nav-derived-hierarchy.md`
(the typed graph this projects over).
