---
status: active
last_verified: 2026-06-21
owner: harness
type: exec-plan
description: Slice 1 of the packaging spec — retire the disabled memory-loop subsystem (feeder/imprint/dream/dreamer/tidy_stop + docs/memory/) in favor of native Claude Code memory; surface docs/adr/, fold openq+limitations into the tech-debt tracker, add an on-demand docs/logs.md, and rewire the scaffold/lint machine off memory/.
base_commit: d72121b
review_level: standard
---
# Slice 1 — Memory subsystem retirement

## Goal

After this plan, the live repo tree contains **no `docs/memory/` directory** and
**no memory-loop machinery**. Specifically, a fresh checkout shows: ADRs at
`docs/adr/` (not `docs/memory/adr/`); the contents of the old `openq/` and
`limitations/` folded into `docs/exec-plans/tech-debt-tracker.md`; the
`recursion-guard` knowledge page at `docs/design-docs/`; a new on-demand
`docs/logs.md`; and the deletion of `feeder_*.py`, `imprint_*.py`, `tidy_stop.py`
+ its `Stop` hook, the `dream` skill, the `dreamer` agent, and the
`memory-bootloader.md` template. The scaffold and the lint gate are rewired so a
*fresh* `scaffold.py --root <tmp>` produces the new shape and `check.py --root
<tmp>` is GREEN. **Observable definition of done:** `git grep -l "docs/memory"`
over the live tree (excluding `exec-plans/completed/` history) returns nothing;
`python3 plugin/scripts/check.py` is GREEN; a from-scratch scaffold has `docs/adr/`
+ `docs/logs.md` + `docs/references/` and no `docs/memory/`.

## Context

- **Parent spec:** [Harness packaging — portable strict-base template](../../product-specs/2026-06-21-harness-packaging-portable-template.md),
  Slice 1 (R1.1–R1.8). The spec owns the design; this plan owns the build.
- **Why now:** the feeder→imprint→dream loop is already **disabled**
  (AGENTS.md: "the automatic feeder/imprint memory loop is disabled pending
  redesign"). Native Claude Code memory owns ephemeral continuity. The subsystem
  is dead weight in a "strict clean base" and the human confirmed full retirement.
- **Machine coupling (the hard constraint):** `plugin/scripts/scaffold.py` hard-codes
  `docs/memory/{adr,archive/sessions,knowledge,limitations,openq,progress}` in
  `SCAFFOLD_DIRS`/`SEEDS`/`CATEGORY_INDEXES`, and `plugin/scripts/lint_docs.py`
  hard-codes `memory/adr`,`memory/knowledge`,`memory/openq`,`memory/limitations`
  as indexed/managed roots with `MEMORY.md` special-cased throughout;
  `plugin/scripts/harness_lib.py` carries `MANAGED_DOCS`. Removing `docs/memory/`
  is therefore a **machine change**, not a file move — the lint's own **D5
  broken-link** and **D4 staleness** checks police completeness.
- **~40 files link `docs/memory/`** (incl. `AGENTS.md`, `ARCHITECTURE.md`,
  `docs/PLANS.md` line 50, `docs/KNOWLEDGE_FORMAT.md`, several specs/plans, and
  `director/taxonomy.py`). The bulk of these are archived `exec-plans/completed/*`
  history — those are left as historical record **unless** D5 flags them as
  broken (filesystem links must resolve), in which case the link path is updated
  (mechanical, not a decision rewrite).
- Gate command: `python3 plugin/scripts/check.py` (see
  `docs/design-docs/agent-harness.md`).

## Approach (self-generated alternatives)

- **A — One atomic commit** for the whole slice. Simplest GREEN story (no
  intermediate broken state), but a huge diff spanning machine + docs + tests,
  hard to review and bisect.
- **B — Staged commits at GREEN boundaries.** Retire the already-unwired dead
  machine first (it's gate-independent once the component inventory is
  regenerated), then the docs-reorg + lint/scaffold rewire as one *necessarily
  atomic* middle commit (the gate cannot be GREEN while `memory/` is half-removed),
  then the self-host narrative + fresh-scaffold verification.
- **Chosen: B.** Reviewable, each commit GREEN, and it isolates the irreducible
  atomic step (the reorg+rewire) from the cleanly-separable bookends. The
  lint/scaffold coupling means the middle commit is large by necessity, not by
  choice — that is recorded, not hidden.

## Assumptions & open questions (self-interrogation)

- **Assumption:** `feeder_*.py` / `imprint_*.py` are unwired — `hooks.json` only
  registers `Stop → tidy_stop.py`. *Breaks if wrong:* a live hook/settings entry
  points at a deleted script → **verify** by grepping `hooks.json`, `.claude/settings*.json`,
  and all `*.py` imports before deleting (M1 first step).
- **Assumption:** deleting the `dream` skill + `dreamer` agent won't hard-fail the
  gate once `gen_inventory.py` is rerun (inventory/coverage are the only consumers).
  *Breaks if wrong:* a `component_coverage`/`component_inventory` lint fails → regen
  fixes it; if a skill cross-references `dream`, update that prose.
- **Assumption:** D5 is filesystem-based and will flag **every** stale
  `docs/memory/...` markdown link, so a GREEN gate proves the link sweep is
  complete. *Breaks if wrong:* a bare-text mention (not a `[](…)` link) won't be
  flagged — those are cosmetic and handled by grep in M3.
- **Open:** delete vs relocate the 2 archived session digests
  (`docs/memory/archive/sessions/*-session-end.md`)? → **Resolved: delete.** They
  are memory-loop session-end artifacts; native memory replaces continuity and git
  history preserves them. (Decision log.)
- **Open:** how does the tracker absorb `openq/` + `limitations/`? → **Resolved:**
  add a dedicated "Open questions & limitations (migrated from retired
  `docs/memory/`)" section with one row per migrated page, preserving its content
  and original intent, sourced to this plan. (Decision log.)
- **Open:** `recursion-guard.md` frontmatter `type` once under `design-docs/`? →
  **Resolved:** keep filename; set `type` to whatever conforms there (`design-doc`
  or `knowledge`) so D-rules pass; fix its own inbound/outbound links.
- **Open:** `docs/memory/openq/memory-loop-redesign.md` — migrate or close? →
  **Resolved: close, do not carry.** The loop is retired, not redesigned (spec
  Non-goals); record its closure as a tracker line, not an open question.

## Milestones

- **M1 — Retire the dead memory-loop machine.** Scope: the gate-independent
  deletions. First verify the unwired assumption (grep `hooks.json`,
  `.claude/settings*.json`, and `import` sites). Then delete
  `plugin/scripts/{feeder_firstprompt,feeder_sessionstart,imprint_enqueue,imprint_guard,imprint_run,tidy_stop}.py`;
  remove the `Stop` hook block from `plugin/hooks/hooks.json` (leaving a valid
  empty `hooks` object); delete `plugin/skills/dream/` and
  `plugin/agents/dreamer.md`; delete the
  `plugin/skills/harness-init/templates/memory-bootloader.md` template; regenerate
  the component inventory (`python3 plugin/scripts/gen_inventory.py` or via the
  gate). At the end these files no longer exist, `hooks.json` registers no hooks,
  and `docs/generated/component-inventory.md` reflects the smaller component set.
  Run: `python3 plugin/scripts/check.py` → GREEN; `git grep -n
  "feeder_\|imprint_\|tidy_stop\|dreamer\|skills/dream" -- '*.py' '*.json'` shows no
  live references. Commit.

- **M2 — Reorganize the docs system + rewire the lint/scaffold machine (atomic).**
  Scope: the irreducible GREEN transition. Move `docs/memory/adr/*` →
  `docs/adr/*` (`git mv`, fix the index, update inbound links incl. `docs/PLANS.md`
  line 50 and the spec index); migrate `docs/memory/openq/*` +
  `docs/memory/limitations/*` content into
  `docs/exec-plans/tech-debt-tracker.md` then delete those dirs; `git mv`
  `docs/memory/knowledge/recursion-guard.md` → `docs/design-docs/` (fix its
  frontmatter + links) and drop `docs/memory/knowledge/index.md`; create
  `docs/logs.md` (light, milestone-grained, on-demand, with a self-describing
  header); delete the remainder of `docs/memory/` (`MEMORY.md`, `progress/`,
  `archive/`). Rewire `plugin/scripts/lint_docs.py` (make `adr` a top-level
  managed+indexed root; drop the `memory/*` roots and the `MEMORY.md`
  special-cases), `plugin/scripts/scaffold.py` (`SCAFFOLD_DIRS`/`SEEDS`/`CATEGORY_INDEXES`/`TOP_INDEXES`
  off `memory/`, onto `docs/adr/` + `docs/logs.md` + `docs/references/`),
  `plugin/scripts/harness_lib.py` (`MANAGED_DOCS`). Bulk-update every **live** doc
  linking `docs/memory/*`; update `tests/test_nav.py` + `tests/test_scaffold.py`
  fixtures/expectations. At the end `docs/memory/` does not exist, ADRs are at
  `docs/adr/`, the tracker holds the migrated openq/limitations, and the machine
  expects the new shape. Run: `python3 plugin/scripts/check.py` → GREEN (D4/D5,
  structure, 699+ tests). Commit.

- **M3 — Self-host narrative + fresh-scaffold verification.** Scope: the prose
  model + proof the porting path produces the new shape. Update `AGENTS.md`
  "Memory (read/write paths)" to describe the native-CC-memory + `docs/adr/` +
  `docs/logs.md` + tech-debt model (and the `Map` table row for `docs/memory/`),
  and `ARCHITECTURE.md` memory references; grep for any surviving bare-text
  `docs/memory` mentions in live docs and fix. Then run a from-scratch scaffold
  into a temp dir and assert the new shape. At the end the self-host docs describe
  the retired-loop model and a fresh host scaffolds correctly. Run:
  `python3 plugin/scripts/scaffold.py --root /tmp/mem-retire-check && ls
  /tmp/mem-retire-check/docs` (expect `adr logs.md references` …, **no** `memory`);
  `python3 plugin/scripts/check.py --root /tmp/mem-retire-check` → GREEN;
  `python3 plugin/scripts/check.py` → GREEN. Commit.

## Progress log
- [ ] M1 — retire dead machine
- [ ] M2 — docs reorg + machine rewire (atomic)
- [ ] M3 — narrative + fresh-scaffold verification

## Surprises & discoveries

## Decision log
- 2026-06-21: Staged GREEN commits (Approach B) — reviewability; the lint/scaffold
  coupling forces M2 into one atomic commit but M1/M3 separate cleanly.
- 2026-06-21: Delete the 2 archived session digests — memory-loop artifacts,
  superseded by native memory; git history preserves them.
- 2026-06-21: tech-debt-tracker absorbs openq+limitations as a migrated section
  (one row per page, content preserved, sourced to this plan); `memory-loop-redesign`
  open-question is closed (loop retired, not redesigned), recorded as a tracker line.

## Feedback (from completion gate)

## Outcomes & retrospective
