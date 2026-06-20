---
status: active
last_verified: 2026-06-21
owner: harness
type: exec-plan
description: Mature the harness-init seed-template layer into the self-describing strict base — author the missing PRINCIPLES template, give references/product-specs/exec-plans dedicated guided indexes, redirect the ARCHITECTURE template to the architecture-setup skill, and rewire scaffold.py so a fresh scaffold gates GREEN with no blank stubs.
base_commit: de93b76c51670aafbf9ceac0322010ac20cb10b6
review_level: standard
---
# Strict-base docs + guidance enrichment (packaging/02)

## Goal

A fresh `python3 plugin/scripts/scaffold.py --root <tmp>` produces a base where
**every shipped doc teaches how to write itself** (no blank stub, no
agent-harness instance content), and `python3 plugin/scripts/check.py --root
<tmp>` is GREEN with no `FILL` surviving outside intended `<!-- FILL -->`
markers. Concretely, the slice closes the verified gaps in the seed-template
layer: the missing `PRINCIPLES.md` template, the generic (non-guided)
`references/` and `product-specs/` indexes, the absent `exec-plans/active|completed`
lifecycle guides, and the over-long `ARCHITECTURE.md` template that should be a
pointer to the `architecture-setup` skill. Definition of done: the tmp-scaffold
read-through shows each strict-base doc is self-describing, both gates are GREEN,
and the self-host repo remains a working harness (`check.py` GREEN).

## Context

- **Parent spec:** `docs/product-specs/2026-06-21-harness-packaging-portable-template.md`
  — Slice 2 is requirements **R2.1–R2.6** there. This plan builds from that
  design; it does not re-derive it. Slice 1 (memory retirement) is complete
  (`docs/logs.md`); the `memory/`→`adr/`+`logs.md` docs shape it fixed is the
  baseline this slice enriches.
- **The packaging model (spec "Design"):** three content natures — *guidance
  docs* (authored, each teaches how to write itself), *the machine* (referenced,
  never copied), *config + profiles* (pre-filled defaults + `<!-- FILL -->`).
  Slice 2 operates entirely in the **guidance-docs** layer (the seed templates
  under `plugin/skills/harness-init/templates/`) plus the `scaffold.py` wiring
  that copies them.
- **Where the templates live / how they ship:** `plugin/skills/harness-init/templates/*`
  are rendered by `plugin/scripts/scaffold.py` (`SEEDS` = template→destination;
  `TOP_INDEXES` = dirs that get the generic `category-index.md`; `render()`
  substitutes `{{TODAY}}`/`{{PROJECT}}`/`{{COMPONENTS}}`). `seed()` is idempotent
  (never overwrites). Template `.md`/`.txt`/`.py` files are NOT themselves
  D-linted (they live under `plugin/`, not `docs/`); the only real validation is
  a fresh scaffold + gate, which is this plan's behavioral acceptance.
- **Lint contract this slice must respect (verified against `lint_docs.py` /
  `harness_lib.py` at base_commit):**
  - `INDEXED_DIRS = (adr, design-docs, product-specs, references)` — D8 requires
    each to have an `index.md`. `exec-plans` is **not** indexed.
  - `MACHINE_DOCS` includes `ARCHITECTURE.md` (D10 = must exist) — the redirect
    must keep the file present; the current template is frontmatter-free and
    GREEN, so a pointer in that same style stays GREEN.
  - `PRINCIPLES.md` is in neither `MACHINE_DOCS` nor `MANAGED_DOCS` → it is a
    normal governed top-level `docs/` page (D3 frontmatter + D4 staleness + D5
    links), modeled on `CHARTER`/`PRODUCT_SENSE` (both carry frontmatter).
  - `index.md` is `RESERVED` in `nav.py` (excluded from catalog/roadmap), so a
    lifecycle guide at `exec-plans/active/index.md` cannot pollute the roadmap as
    a fake plan; `exec-plans` not being indexed means D8 won't demand it register
    the plans either.
- **The instance-leak trap:** the self-host `docs/PRINCIPLES.md` hard-links
  `adr/0003-lights-out-director.md`. A fresh host has no such ADR, so the
  *template* must describe the Director's role generically with **no link that
  would break D5** in a scaffolded host.

## Approach (self-generated alternatives)

For the exec-plans "structured template" (R2.6) and the ARCHITECTURE template
(R2.4), the design space is "duplicate vs point":

- **A — Literal duplication.** Seed a copy of the PLANS.md plan skeleton into
  `exec-plans/active/`, and keep the full FILL skeleton in the ARCHITECTURE
  template. Tradeoff: matches the spec wording most literally, but creates a
  *second source* of both the plan skeleton and the architecture guide that
  drifts from PLANS.md / the `architecture-setup` skill — the exact no-drift
  failure `docs/DESIGN.md` ("skills point, docs explain"; referenced-not-copied)
  warns against, and it would feed Slice 6's drift-check more surface to police.
- **B — Pointer guides (no-drift).** Ship *guides* that point to the single
  source: the exec-plans lifecycle guide says "copy the skeleton from PLANS.md /
  use the `execplan` skill", and the ARCHITECTURE template redirects to
  `architecture-setup`. Tradeoff: one extra hop to the skeleton, but zero
  duplication and zero drift by construction.
- **Chosen: B.** No-drift-by-construction is the governing principle of the
  packaging model (the machine is *referenced, never copied*). The skeleton stays
  single-sourced in PLANS.md; the architecture guide stays single-sourced in the
  `architecture-setup` skill. The seeds are self-describing *pointers*, which
  still satisfies R2.6/R2.4 ("self-describing, authors from the file alone")
  without minting drift surface. (Mirrored into the Decision log.)

For PRINCIPLES (R2.3): a pure-FILL stub vs a seeded guide. Chosen: a **seeded
guide** mirroring how `reliability.md`/`security.md` ship "small seeds" — explain
the doc's purpose + the principle shape (`### P# — title` / `**Why:**` /
`**Applied:**`) + 2–3 genuinely *universal* seed principles (the operating
consequences of the harness's own philosophy, marked "seed — adapt or delete") +
a `<!-- FILL -->` for the host human's own principles. Rationale: a blank
PRINCIPLES is useless to an adopting human; the universal seeds demonstrate the
shape and are defensible (they follow from PRODUCT_SENSE's "human attention is
scarce"), while staying clearly adapt-or-delete so they aren't this-repo content.

## Assumptions & open questions (self-interrogation)

- **Assumption:** template `.md` files are not D-linted directly, so the only
  validation that matters is a fresh scaffold + `check.py --root <tmp>`. *If
  wrong* (a lint scans templates), the tmp-scaffold gate would surface it — so
  the acceptance harness catches the assumption breaking.
- **Assumption:** removing `references` and `product-specs` from `TOP_INDEXES`
  and giving them dedicated SEEDS keeps D8 GREEN (each still gets an `index.md`,
  just a richer one). Verified by the tmp gate.
- **Assumption:** an `index.md` under `exec-plans/active|completed` passes the
  content lints with `category-index.md`-style frontmatter (status/last_verified/
  owner) and is excluded from roadmap (RESERVED). Verified by the tmp gate +
  `nav.py roadmap` spot-check on the tmp host.
- **Open → resolved autonomously:** "structured template for active/completed" =
  a lifecycle *pointer guide* (Approach B), not a skeleton copy. Recorded; not a
  taste fork.
- **Open → resolved autonomously:** PRINCIPLES seeds 2–3 universal principles
  (not zero, not all 8 self-host ones). Recorded.
- **Scope fence:** this slice touches ONLY the template layer + `scaffold.py`
  wiring. It does **not** modify the self-host's own `docs/ARCHITECTURE.md`,
  `docs/product-specs/index.md`, `docs/references/index.md`, or the self-host
  `exec-plans/` dirs (those are live instance content the review personas / nav
  rely on). No Director/profile/plugin-manifest work (Slices 3–5).

## Milestones

- **M1 — PRINCIPLES template (R2.3).** Author
  `plugin/skills/harness-init/templates/principles.md`: a self-describing guide
  (purpose: the central Director consults it at a taste fork to simulate the
  human's call; relationship to PRODUCT_SENSE/DIRECTOR; "it is alive" + audit
  loop), the principle shape, 2–3 universal seed principles marked adapt-or-delete,
  and a `<!-- FILL -->` for the host's own — frontmatter `status: draft / type:
  methodology / owner: harness / {{TODAY}}`, **no `adr/` link** (D5 trap). Add
  `("principles.md", "docs/PRINCIPLES.md")` to `scaffold.py` `SEEDS`. At the end:
  the template exists and a scaffold renders `docs/PRINCIPLES.md`. Run
  `python3 plugin/scripts/scaffold.py --root /tmp/h2 && grep -rn 'FILL' /tmp/h2/docs/PRINCIPLES.md`;
  expect a rendered, frontmatter-valid PRINCIPLES with only intended FILL markers.

- **M2 — Dedicated guided indexes + design-docs accuracy (R2.5, R2.6, R2.2).**
  Author `references-index.md` (a guide: *why* references exist — LLMs need
  external-API/source digests, the `llms.txt` convention — + D8 register-here),
  `product-specs-index.md` (a guide: phase/parent structure, how the roadmap is a
  derived group-by, starts empty), and `exec-plan-active-index.md` +
  `exec-plan-completed-index.md` (lifecycle pointer guides per Approach B). Wire
  all four into `SEEDS`; remove `references` and `product-specs` from
  `TOP_INDEXES` (leaving `("adr",)`). Fix the stale "memory loop" phrase in
  `design-docs-index.md` (Slice-1 residue → "native memory"). At the end: a
  scaffold renders rich `docs/references/index.md`, `docs/product-specs/index.md`,
  and both `exec-plans/*/index.md` guides. Run a scaffold to a clean tmp;
  expect all four present and self-describing.

- **M3 — ARCHITECTURE redirect (R2.4).** Rewrite
  `plugin/skills/harness-init/templates/architecture-md.md` from the full FILL
  skeleton to a short pointer: ARCHITECTURE is authored by the `architecture-setup`
  skill (harness-init step 7) from the host's real source; the template states
  what the skill produces (codemap + invariants + enforcement table) and that the
  file must exist (D10) but is filled by the skill, not by hand-copying a generic
  skeleton. Keep it frontmatter-free (matches the GREEN current style; D10 only
  needs existence). At the end: the template is a pointer, and a scaffolded
  `ARCHITECTURE.md` still satisfies D10.

- **M4 — Behavioral acceptance + R2.1 completeness (verify).** Scaffold a fresh
  tmp host end-to-end, run the gate, read every shipped doc, and confirm the
  strict-base set (R2.1) is complete and self-describing. Run:
  `rm -rf /tmp/h2 && mkdir -p /tmp/h2 && git -C /tmp/h2 init -q && python3 plugin/scripts/scaffold.py --root /tmp/h2 && python3 plugin/scripts/check.py --root /tmp/h2`
  → expect **GREEN**; `grep -rn 'FILL' /tmp/h2/docs /tmp/h2/*.md` → only intended
  `<!-- FILL -->` markers (no stray "TBD"/"handle later"); `python3
  plugin/scripts/nav.py roadmap --root /tmp/h2` (or equivalent) shows no fake
  plan from the exec-plans index guides; manual read-through confirms each doc
  teaches how to write itself with no agent-harness instance content. Finally
  `python3 plugin/scripts/check.py` on the self-host repo → GREEN. This is the
  plan's behavioral acceptance (a runnable surface — scaffold + gate), not N/A.

## Progress log
- [x] (2026-06-21) Plan created; spec R2.1–R2.6 read; lint constants + template
  layer surveyed; Explore audit reconciled (2 of 3 "critical" findings were false
  positives — design-docs-index entries are correctly seeded, exec-plans needs no
  index per D8). base_commit recorded de93b76. Plan committed e7f924d.
- [x] (2026-06-21) M1: authored `principles.md` template (3 universal seed
  principles, no `adr/` link), wired into SEEDS; tmp scaffold renders
  `docs/PRINCIPLES.md` with only the intended FILL marker.
- [x] (2026-06-21) M2: authored `references-index.md`, `product-specs-index.md`,
  `exec-plan-active-index.md`, `exec-plan-completed-index.md`; wired all four into
  SEEDS; trimmed `TOP_INDEXES` to `("adr",)`; fixed the stale "memory loop"
  phrase in `design-docs-index.md`.
- [x] (2026-06-21) M3: rewrote `architecture-md.md` from FILL skeleton to a
  redirect to the `architecture-setup` skill (frontmatter-free, D10-satisfying).
- [x] (2026-06-21) M4: fresh tmp scaffold gates GREEN (`check.py --root`); all 23
  R2.1 docs present; no stray FILL/TBD/unrendered tokens; `nav.py roadmap` shows
  0 plans (exec-plans index guides not mistaken for plans); updated the stale
  `test_scaffold` architecture test to the redirect contract; self-host gate GREEN.

## Surprises & discoveries
- `test_scaffold.test_architecture_template_guides_host_specific_codemap` asserted
  the OLD skeleton phrasing ("Bird's Eye View", "Invariant -> FORM"). R2.4 retires
  that skeleton, so the test encoded a now-dead contract — rewrote it as
  `test_architecture_template_redirects_to_architecture_setup` (asserts the
  redirect + a negative `<!-- FILL` assertion). A test failing because the spec
  *changed the contract* is correct TDD, not a workaround.
- The PRINCIPLES guide originally said "in the FILL block" in prose, tripping a
  naive `grep FILL` twice; reworded to "in the marker below" so the only "FILL"
  token is the actual `<!-- FILL -->` marker (keeps the M4 acceptance grep honest).

## Decision log
- 2026-06-21: **Pointer guides over duplication** (Approach B) for the exec-plans
  lifecycle templates and the ARCHITECTURE template — no-drift-by-construction is
  the packaging model's governing principle; the plan skeleton stays single-sourced
  in PLANS.md and the architecture guide in the `architecture-setup` skill.
- 2026-06-21: **PRINCIPLES template ships 2–3 universal seed principles** (not a
  blank stub, not all 8 self-host principles), marked adapt-or-delete — mirrors
  the reliability/security "small seed" pattern; demonstrates the shape without
  imposing this repo's content.
- 2026-06-21: **exec-plans lifecycle guides use `index.md`** (RESERVED in nav,
  excluded from roadmap; exec-plans not in INDEXED_DIRS so D8 won't require page
  registration) — keeps the dirs self-describing without minting a fake plan.
- 2026-06-21: **Template carries no `adr/` link** — the self-host PRINCIPLES
  links ADR 0003, but that link would break D5 in a fresh host; the template
  describes the Director generically instead.

## Feedback (from completion gate)

## Outcomes & retrospective
