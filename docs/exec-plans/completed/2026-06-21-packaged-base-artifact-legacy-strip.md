---
status: completed
last_verified: 2026-06-21
owner: harness
type: exec-plan
description: Ship the capstone packaged base — a checked-in, inspectable, legacy-free base/ tree rendered from the seed templates, a SETUP.md to bring it to life, and a blocking drift-check lint that keeps the hand-synced base honest against the seed-template set + the live plugin component list.
base_commit: b0fa90c143b723a7641c92c7f8569f14fa25fc8f
review_level: full
phase: packaging/06-base-artifact
---
# Packaging Slice 6 — the packaged base artifact + legacy strip (capstone)

## Goal
A new project can **open one folder — `base/` — and see the whole clean harness
system**, legacy-free, and bring it to life from a from-scratch read; a blocking
lint keeps that hand-synced folder honest against its source. Observable
definition of done:

1. A checked-in **`base/`** tree mirrors the host layout a `harness-init` adoption
   produces: `AGENTS.md`, `CLAUDE.md`, `.harness.json`, `ARCHITECTURE.md` at root;
   the full `docs/` guidance tree (CHARTER, PLANS, DESIGN, PRINCIPLES,
   KNOWLEDGE_FORMAT, PRODUCT_SENSE, QUALITY_SCORE, RELIABILITY, SECURITY,
   `design-docs/` + core-beliefs, the `adr/`/`design-docs/`/`product-specs/`/
   `references/`/`exec-plans/{active,completed}` index guides, tech-debt-tracker,
   logs) — each file the **rendered seed template** with `{{COMPONENTS}}` and the
   `adr` `{{CATEGORY}}` substituted and `{{PROJECT}}`/`{{TODAY}}` preserved as
   fill-markers.
2. `base/SETUP.md` exists and guides bringing the base to life + pointing the
   centralized Director at it (reusing `.claude/DIRECTOR.md` §0).
3. The base is **legacy-free**: it contains none of `docs/symphony-original/`,
   `EDUCATION.md`, `docs/superpowers/`, `docs/generated/`,
   `docs/design-docs/okf-comparison.md`, or `docs/design-docs/symphony-parity-gap.md`.
4. A new **`plugin/scripts/lint_base.py`**, wired into `check.py`, **blocks** when
   `base/` drifts from its source — a missing/extra/edited base file vs. the
   rendered seed templates, or a stale `{{COMPONENTS}}` table vs. the live plugin —
   and is a **no-op** when `base/` is absent (a ported host). A test proves it
   catches each drift class and passes on the in-sync base.
5. `python3 plugin/scripts/check.py` is GREEN (incl. the new `base` step).

## Context
Implements **Slice 6 (`packaging/06`, capstone)** of
`docs/product-specs/2026-06-21-harness-packaging-portable-template.md`
(R6.1–R6.4 + acceptance #6). The spec owns the design; this plan owns the build.
Slices 1–5 are complete: the seed-template layer is the self-describing strict
base (Slice 2), the Director manual lives at `.claude/DIRECTOR.md` (Slice 3), the
two profiles are consolidated (Slice 4), and the manifests are clean (Slice 5).

Machinery a novice needs (all verified):
- **`plugin/scripts/scaffold.py`** renders + lays out the seed templates into a
  host. `SEEDS` = the 24 `(template, dest)` pairs (the authoritative seed set,
  incl. `("agent-harness.md", "docs/design-docs/agent-harness.md")`);
  `TOP_INDEXES = ("adr",)` seeds `docs/adr/index.md` from `category-index.md` with
  `{{CATEGORY}}`; `DIRS` includes `docs/generated` (created + `gen_inventory` run);
  `render(text, subs)` does `{{KEY}}`→value; `components_table(plugin)` builds the
  skill/agent table that fills `{{COMPONENTS}}`. `lint_base.py` will **import
  scaffold** and reuse `SEEDS`/`TOP_INDEXES`/`render`/`components_table`, so the
  base's expected file-set is the *same source* scaffold uses — drift-proof by
  construction.
- **Substitution surface**: `{{TODAY}}` is in 19/21 templates, `{{PROJECT}}` in 4,
  `{{COMPONENTS}}` only in `agent-harness.md`, `{{CATEGORY}}` only in
  `category-index.md`. Baking `{{TODAY}}` into the base would make the drift-check
  calendar-fragile, so the base **preserves `{{PROJECT}}`/`{{TODAY}}` as markers**
  and substitutes only `{{COMPONENTS}}` (the live machine index, whose drift R6.2
  wants caught) and the `adr` `{{CATEGORY}}`.
- **Lint pattern** (`lint_docs.py`/`gen_inventory.py`): `root = hl.repo_root()`,
  collect `errors`, print each, `sys.exit(1 if errors else 0)`; `check.py` runs the
  built-in steps (`structure`/`docs`/`generated`) with `cwd=root`. The new `base`
  step appends to that list. `gen_inventory --check` is the precedent for a
  self-host-gated check; `lint_base` gates on `base/` existence (the base only
  exists in the self-host) — present ⇒ blocking, absent ⇒ no-op pass.
- **Repo lints scan only `<root>/docs` + `plugin/`** (verified): `lint_docs` walks
  `<root>/docs`, `lint_structure`/`gen_inventory` walk `plugin/`. A top-level
  `base/` (with its own `base/docs/…`) is **not** scanned by them — no collision,
  no double-counting in `nav`.
- **Legacy-strip targets exist** in the self-host (`docs/symphony-original/`,
  `EDUCATION.md`, `docs/superpowers/`, `docs/generated/`, the three instance
  design-docs); scaffold never *produces* `symphony-original`/`EDUCATION`/
  `superpowers`/`okf-comparison`/`symphony-parity-gap`, so they are absent from a
  rendered base by construction — the base only actively differs from a full
  scaffold by **omitting `docs/generated/`** (regenerated per host at init).

## Approach (self-generated alternatives)
**How to render the base / drive the drift-check**
- A: **Rendered base, preserve `{{PROJECT}}`/`{{TODAY}}` markers, substitute
  `{{COMPONENTS}}`+`{{CATEGORY}}`; the drift-check renders each seed the same way
  and byte-compares.** No calendar dependence; the live component table is shown
  and its drift caught; the markers read honestly as fill-points. The expected
  file-set comes from `scaffold.SEEDS`, so a new/removed seed is auto-detected.
- B: **Fully-substituted render (incl. `{{TODAY}}`→a frozen date).** Literal to
  R6.1's "rendered," but bakes a date into 19 files; the drift-check must re-derive
  or normalize the date, and the hand-sync model means rewriting 19 dates on any
  template touch. Calendar-fragile, higher sync cost.
- C: **Raw templates verbatim (preserve ALL markers, incl. `{{COMPONENTS}}`).**
  Simplest checker, but the base then shows a `{{COMPONENTS}}` marker instead of the
  machine index — violating the Design table's "the base carries an index of what
  exists" and giving R6.2's component-list drift nothing to check.
- **Chosen: A** — it satisfies R6.1 (a rendered, inspectable tree showing the real
  component index), R6.2 (both drift sources: the seed-template set *and* the live
  component list), and stays robust (no calendar fragility) and cheap to hand-sync.

**Drift-check disposition**
- Blocking (self-host) vs. advisory: **blocking when `base/` exists**, no-op when
  absent. The base is a self-host-only artifact, so "blocking when present" == "the
  self-host keeps its own base honest" without ever reddening a ported host's gate
  (mirrors `gen_inventory`'s self-host gating). Chosen over advisory: a silent
  advisory note would let the base rot, defeating R6.2's purpose.

**`agent-harness.md` in the base (spec-ambiguity resolution)**
- R6.4 lists `agent-harness.md` among "instance design-docs" to strip, but it is
  also a `scaffold.SEEDS` entry (every host gets the *generic template* version,
  which carries the `{{COMPONENTS}}` machine index). Resolved: **the base INCLUDES
  the generic template `agent-harness.md`** (it is the base's machine-index doc and
  the carrier of the component-list drift R6.2 checks; a base without it would lack
  a D10 `MACHINE_DOC` and an adoptable host's required doc). R6.4's "agent-harness.md"
  is read as the **self-host INSTANCE** doc (`docs/design-docs/agent-harness.md` as
  it exists here — rich, self-host-specific), which the base does not copy. Recorded
  in the Decision log and flagged for spec-compliance to confirm; if it reads this as
  a misread, stripping it is a one-line P1 fix.

## Assumptions & open questions (self-interrogation)
- **Assumption — `base/` at repo root is invisible to existing tooling.** Verified:
  the lints/nav scan `<root>/docs` + `plugin/`, never `base/`. *If wrong* (some tool
  rglobs from root), `base/docs/*` frontmatter could pollute `nav`/`lint_docs`;
  mitigated by the verification milestone running `nav` + the full gate and
  confirming counts are unchanged.
- **Assumption — importing `scaffold` from `lint_base` is portable + S-lint-clean.**
  `scaffold.py` imports only `harness_lib` + stdlib and guards `main()` under
  `__main__`; importing it is side-effect-free. *If `lint_structure.check_imports`
  rejects a script-to-script import*, fall back to referencing `SEEDS` via a tiny
  shared accessor — but reuse (not a second copy of the seed list) is the goal.
  Checked in M2.
- **Assumption — preserving `{{TODAY}}` in `base/docs/*` is acceptable** even though
  it is not a valid date. The base is an **inspection reference, not a gated root**
  (the repo gate never scans `base/`; a real adoption renders dates via
  `harness-init`). SETUP.md states this. *If wrong* (someone expects
  `check.py --root base/` to pass), that is out of scope — adoption is via
  harness-init, not raw-copy; SETUP.md says so.
- **Open — base location/name?** Resolved autonomously: top-level **`base/`**
  (short, obvious "open one folder"). Not a taste fork.
- **Open — does `base/` ship a `.gitignore`/git-hook?** No — those are host *runtime*
  installed by `scaffold.gitignore()`/`git_hook()`, not seed *content*. The base is
  content-only; SETUP.md notes the hook is installed at adoption.
- **Open — escalate the `agent-harness.md`-in-base reading to the human?** No — it is
  a spec-text ambiguity resolvable by coherence (the base must carry the machine
  index for R6.2), not a product-taste fork. Recorded + flagged for review, per the
  methodology (resolve autonomously, let the gate's spec-compliance catch a misread).

## Milestones

- **M1 — The checked-in base artifact + SETUP.md (R6.1, R6.3, R6.4).** Scope: a new
  top-level `base/` tree + `base/SETUP.md`. Lay out every `scaffold.SEEDS` entry at
  its dest under `base/`, each file = `render(template, {"COMPONENTS": <live
  table>})` (so `{{COMPONENTS}}`→the real skill/agent table; `{{PROJECT}}`/`{{TODAY}}`
  preserved); add `base/docs/adr/index.md` = `render(category-index.md, {"CATEGORY":
  "adr"})`; create the `design-docs/`, `product-specs/`, `references/`,
  `exec-plans/{active,completed}` dirs (non-empty via their index guides). Do **not**
  create `base/docs/generated/` or a `base/.gitignore`/hook. Author `base/SETUP.md`
  (base-exclusive, not a seed): what the base is, how to bring it to life (fill the
  `{{PROJECT}}`/`{{TODAY}}`/`<!-- FILL -->` markers or run `harness-init`; run the
  gate, which regenerates `docs/generated/`), and how to point the centralized
  Director at the new project (reuse `.claude/DIRECTOR.md` §0). At the end `base/` is
  a complete, legacy-free, inspectable host skeleton. Run: `find base -type f | sort`
  (expect the SEEDS dests + `docs/adr/index.md` + `SETUP.md`, NO `docs/generated/`);
  `grep -rl 'symphony-original\|EDUCATION\|okf-comparison\|symphony-parity-gap' base/`
  (expect empty). Acceptance: every guidance doc present at its host path; SETUP.md
  reads as a from-scratch bring-to-life guide; zero legacy files.

- **M2 — The drift-check lint `lint_base.py` + check.py wiring + tests (R6.2).**
  Scope: a new `plugin/scripts/lint_base.py`, a `("base", …)` step in
  `plugin/scripts/check.py`, and `tests/test_lint_base.py`. `lint_base.main()`:
  `root = hl.repo_root()`; if `not (root/"base").is_dir()` → print a SKIP line and
  exit 0 (ported host no-op). Else `import scaffold`; build `subs = {"COMPONENTS":
  scaffold.components_table(plugin)}`; for each `(t, dest)` in `scaffold.SEEDS`,
  FAIL if `base/dest` is missing or `!= render(template_text, subs)`; for the `adr`
  `TOP_INDEXES` index, compare against `render(category-index.md, {"CATEGORY":"adr"})`;
  FAIL on any `base/` file **not** in the expected set (extra/legacy), on a present
  `base/docs/generated/`, and on a missing `base/SETUP.md` (presence-only — it is
  base-authored, not a seed). Print `B#`-coded errors + a `lint_base: OK/ N FAIL`
  line; `sys.exit(1 if errors else 0)`. Append the step to `check.py`. Tests
  (tmp-dir fixtures): (a) the real `base/` passes; (b) a deleted base file FAILs;
  (c) an edited base file FAILs; (d) a `{{COMPONENTS}}`-table change (simulated)
  FAILs; (e) an extra/legacy file FAILs; (f) a missing `SETUP.md` FAILs; (g) no
  `base/` ⇒ SKIP+exit 0. At the end the gate has a fourth blocking step that keeps
  the base honest. Run: `cd tests && PYTHONPATH=..:../plugin/scripts python3 -m
  unittest test_lint_base` (expect green); `python3 plugin/scripts/lint_base.py`
  (expect `lint_base: OK`). Acceptance: the lint passes on the synced base, FAILs on
  each injected drift, and is a no-op without `base/`.

- **M3 — Verification: legacy-free, drift-checked, from-scratch-readable, GREEN
  (R6 acceptance).** Scope: no new files — prove the capstone. Run the full gate
  (incl. the new `base` step) → GREEN; confirm `nav` page counts are unchanged
  (base/ not scanned); confirm the legacy-strip greps are empty; read `base/SETUP.md`
  + the `base/` tree as if no source repo existed and confirm an agent could bring it
  to life. Run: `python3 plugin/scripts/check.py` (GREEN);
  `python3 plugin/scripts/nav.py catalog --json | python3 -c "import sys,json;
  print(len(json.load(sys.stdin)))"` before/after sanity. Acceptance: gate GREEN; the
  base is inspectable + legacy-free + self-sufficient; the drift-check is part of the
  gate.

## Progress log
- [x] (2026-06-21) Plan created; scaffold/lint/gate machinery mapped; substitution
  surface scoped (preserve PROJECT/TODAY, substitute COMPONENTS/CATEGORY); base
  location (`base/`) + lint design settled.
- [x] (2026-06-21) M1 — `base/` built (24 seeds rendered at host dests + adr index +
  SETUP.md); COMPONENTS/CATEGORY substituted, PROJECT/TODAY preserved; legacy-free.
- [x] (2026-06-21) M2 — `lint_base.py` + the `base` step in check.py + 11 tests;
  promoted SEEDS/TOP_INDEXES/render/components_table to harness_lib (invariant 8).
- [x] (2026-06-21) M3 — full gate GREEN incl. the base step; nav shows 0 base/ paths.
- [x] (2026-06-21) Completion gate: GREEN (705 tests); reviews — spec-compliance,
  arch, security, code-quality all SATISFIED; reliability found 2 R22-totality P2s
  in `lint_base` → fixed (tolerant `_read` + B6 code + structural `allowed`) →
  re-reviewed SATISFIED. 2 trivial code-quality P2s applied (comment + B6 test);
  remaining P2s + proposed rules tracked. Codex stalling → Claude personas (sanctioned).

## Behavioral check
The runnable surface is `lint_base.py` (the new gate step) + the `base/` artifact.
Exercised: `python3 plugin/scripts/lint_base.py` → `lint_base: OK` on the synced base;
the 11 `test_lint_base` cases drive each FAIL class (B1 missing, B2 edited/stale-table/
non-UTF8, B3 extra, B4 generated, B5 missing SETUP, B6 unreadable template) + the
no-op-when-absent path; the full `check.py` gate runs the `base` step GREEN. No web
surface, so no playwright drive.

## Surprises & discoveries
- `{{TODAY}}` saturates the templates (19/21), which is what rules out a
  fully-substituted base — the drift-check would otherwise fight the calendar.
- R6.4's `agent-harness.md` strip-item collides with its being a live `SEEDS` entry;
  resolved by reading R6.4 as the self-host *instance* doc and keeping the generic
  template in the base (it carries the component index R6.2 must drift-check).

## Decision log
- 2026-06-21: base = rendered seeds with `{{COMPONENTS}}`/`{{CATEGORY}}` substituted,
  `{{PROJECT}}`/`{{TODAY}}` preserved (Approach A) — robust + shows the machine index.
- 2026-06-21: drift-check blocks when `base/` exists, no-ops when absent (self-host
  gating, `gen_inventory` precedent) — over a silent advisory that would let the base rot.
- 2026-06-21: `lint_base` imports `scaffold` to reuse `SEEDS`/`render`/`components_table`
  — the base's expected set is the same source scaffold uses (no second copy → drift-proof).
- 2026-06-21: base INCLUDES the generic template `agent-harness.md`; R6.4's strip-item =
  the self-host instance doc. Flagged for spec-compliance.
- 2026-06-21: base omits `docs/generated/` (regenerated per host) + ships no
  `.gitignore`/git-hook (host runtime, not content). `base/` is an inspection
  reference, not a gated root (SETUP.md says so).

## Feedback (from completion gate)
Five-persona full review. All SATISFIED. One round of R22 fixes (reliability); the
rest tracked in `docs/exec-plans/tech-debt-tracker.md`.

- **P2 (reliability, FIXED in-gate) — `lint_base` R22 totality.** Two reads could
  raise (`FileNotFoundError` on a missing seed template; `UnicodeDecodeError` on a
  non-UTF8 base file) instead of a clean coded FAIL — a written-R22 violation in a
  new gate lint. Fixed: a tolerant `_read` helper, a `B6` code for an unreadable
  template (dest skipped), and `allowed` computed structurally from `SEEDS` so a B6
  skip can't cascade into a false B3. +2 regression tests, re-reviewed → SATISFIED.
- **P2 (code-quality, FIXED) — dropped comment + B6 coverage.** Re-added the
  "tidy_stop sentinel" detail to the promoted `SEEDS` comment; added
  `test_missing_template_fails_b6_no_cascade`.
- **P2 (code-quality, tracked) — `expected_files` dual contract** (returns the dict
  AND appends to a caller `errors` list). A deliberate builder pattern (mirrors the
  `lint_docs` check_* functions); documented; acceptable. Tracked for taste only.
- **P2 (arch, considered — no change) — the B3 `docs/generated/` skip + the extra
  subprocess spawn on ported hosts.** The B3 skip is NOT dead code: it prevents B3
  from double-reporting `generated/` contents alongside B4. The per-gate subprocess
  spawn matches the `gen_inventory --check` precedent. Both correct as-is; noted.
- **Proposed rules (tracked):** (arch) write the script→script-import prohibition +
  a `base/` artifact discipline into DESIGN.md; (spec-compliance) amend the parent
  spec's R6.4 to name "the self-host *instance* `agent-harness.md`" (the base ships
  the generic template — confirmed correct); (reliability) widen R22's text from
  `lint_docs.py` to "every commit-gate lint step"; (security, optional) a one-line
  SECURITY T9 note that the checked-in `base/` is content-only.

## Outcomes & retrospective
Slice 6 — the capstone — delivered the tangible "open one folder and see the whole
system" artifact, and **completes the six-slice packaging spec**.

- **R6.1/R6.3/R6.4 — the base artifact.** A checked-in `base/` tree mirrors the host
  layout a `harness-init` adoption produces: the 24 seed templates rendered at their
  destinations (the live `{{COMPONENTS}}` machine index + the `adr` `{{CATEGORY}}`
  substituted; `{{PROJECT}}`/`{{TODAY}}` preserved as honest fill-markers) + a
  base-authored `SETUP.md` (bring-to-life + point the centralized Director, reusing
  `.claude/DIRECTOR.md` §0). Legacy-free: no `docs/generated/`, symphony-original,
  EDUCATION, superpowers, okf-comparison, or symphony-parity-gap.
- **R6.2 — the drift-check.** `plugin/scripts/lint_base.py` blocks when `base/`
  diverges from its source (a missing/extra/edited file, or a stale component table),
  no-ops when `base/` is absent (self-host gating, the `gen_inventory` precedent), and
  is R22-total. It derives the expected set from the SAME `harness_lib.SEEDS`/`render`/
  `components_table` that `scaffold.py` uses — so the base is **drift-proof by
  construction** (add a seed, the base is flagged missing it automatically).
- **The decisive design calls:** (1) substitute `{{COMPONENTS}}` but preserve
  `{{TODAY}}` — `{{TODAY}}` saturates 19/21 templates, so baking it would make the
  drift-check fight the calendar; preserving it keeps the check deterministic while
  still showing the live machine index. (2) Promote the seed primitives to
  `harness_lib` rather than `import scaffold` from `lint_base` — ARCHITECTURE
  invariant 8 (shared helpers in a core module, not a sibling private-import); arch
  confirmed `harness_lib` already carries the destination-side seed vocabulary
  (`MANAGED_ROOTS`/`MANAGED_DOCS`), so this is consistent factoring. (3) Resolved the
  R6.4 `agent-harness.md` ambiguity by keeping the generic template in the base (it
  carries the component index R6.2 drift-checks) and reading R6.4's strip-item as the
  self-host instance doc — spec-compliance verified the two files are materially
  different and called the resolution "defensible and correct."
- **Process:** the full review caught a real written-rule (R22) violation in fresh
  gate code; fixing it in-gate (rather than tracking) kept the capstone clean. Codex
  remained degraded — the Claude personas carried all five reviews (sanctioned).
- **Packaging spec COMPLETE.** All six slices (memory retirement → strict-base docs →
  Director relocation → two-profile consolidation → plugin cleanup → this base
  artifact) are landed and gated. The harness is now a portable, inspectable,
  drift-checked strict base, not just one instance of itself. Remaining follow-ups are
  doc-debt (the tracked proposed rules + the pre-existing retired-loop text in
  QUALITY_SCORE/RELIABILITY/SECURITY) for a gardening pass — and R5.3's public
  republish, still a separate human go/no-go.
