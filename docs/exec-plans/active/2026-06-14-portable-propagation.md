---
status: active
last_verified: 2026-06-14
owner: harness
base_commit: 46ad95e
---
# Portable propagation — memory-as-docs across the portable layer

## Goal
After this, running `harness-init` / `scaffold.py` on a fresh host produces a
**memory-as-docs** repo — `docs/journal/` plus the existing design-docs /
exec-plans / references homes, with **AGENTS.md as the sole map/bootloader** —
and **no `docs/memory/` tree and no `MEMORY.md`**. That fresh host passes the
gate GREEN, proving a NEW port is born into the current architecture and
lint-clean (what the self-host-only migration structurally could not prove). The
dormant old read/write loop is **deleted** from the plugin (the SessionStart
feeder `feeder_*`, the imprint write loop `imprint_*`, the `dream` skill, the
`dreamer` agent); the 6 live dreaming templates move under `dream-rollouts/`.

Observable definition of done (reproducible):

    tmp=$(mktemp -d); git -C "$tmp" init -q
    python3 plugin/scripts/scaffold.py --root "$tmp"
    test ! -e "$tmp/docs/memory"            # no old tree
    test ! -e "$tmp/docs/memory/MEMORY.md"  # no bootloader file
    test -d "$tmp/docs/journal"             # residual ledger home seeded
    python3 plugin/scripts/check.py --root "$tmp"   # -> GREEN

…and `python3 plugin/scripts/check.py --root .` (self-host) stays GREEN at every
milestone.

## Context
Point precisely; do not duplicate.
- **Spec design (read first):** `docs/design-docs/memory-architecture.md` — the
  one-brain thesis, the per-claim routing taxonomy, the **Host adaptation**
  section (the flat self-contained store is the correct FALLBACK for a bare host
  with no docs library; output target is a *placement* decision, not a hardcode),
  and the **Read path — on-demand navigation, not a feeder** decision (the dormant
  feeder scripts retire with the rest of the old loop). This plan IMPLEMENTS those
  decisions in the portable layer; it adds no new conceptual design, so it gets no
  new design-doc (PLANS.md two-docs rule — this is pure implementation design).
- **The debt + scope decision that spawned this plan:**
  `docs/exec-plans/completed/2026-06-14-memory-as-docs.md` — Decision log entry
  "2026-06-14 (M4, scope)" (the pivot was self-host scope; full propagation
  deferred to a follow-on with its own design) and the **Major** tracker row in
  `docs/exec-plans/tech-debt-tracker.md` ("memory-as-docs pivot is self-host-only
  …"). This plan closes that row.
- **Live engine (unchanged):** `docs/design-docs/dreaming-v2.md` +
  `plugin/scripts/{dream_discover,dream_phase1,dream_phase2,dream_router,dream_run,
  memories_db,memories_workspace}.py`. No engine logic changes here — only
  packaging (template location), scaffold seeds, lint constants, host-facing docs,
  and the deletion of dead code.
- **Two user decisions driving scope (2026-06-14):** (1) **hard-delete** the old
  loop now (git preserves history), not neutralize-in-place; (2) **plugin
  going-forward only** — fix the plugin so NEW ports are memory-as-docs; hosts
  already ported with `docs/memory/` (e.g. the Lingual test port) migrate on
  demand via a tracker row, NOT in this plan.

The blast-radius map (delete / relocate / rewrite / keep) was established this
session by reading hooks.json (only `Stop → tidy_stop` is wired — the feeder and
imprint are dormant code, no live importer), the three `load_templates()` sites,
`lint_docs.py` constants, `scaffold.py`, and the harness-init templates.

## Milestones
- [x] **M1 — Relocate the dreaming templates; retire the `dream` skill & `dreamer`
  agent.** `git mv plugin/skills/dream/templates/{router_input,router_system,
  stage_one_input,stage_one_system,consolidation_input,consolidation_system}.md
  plugin/skills/dream-rollouts/templates/`, then repoint the three loaders so the
  directory constant is `skills/dream-rollouts/templates`:
  `dream_phase1.load_templates` (currently `plugin/scripts/dream_phase1.py:185`),
  `dream_phase2.load_templates` (`:45`), `dream_router.load_templates` (`:48`).
  Delete `plugin/skills/dream/` (its `SKILL.md` dispatches the old `dreamer`
  agent and commits `docs/memory/`) and `plugin/agents/dreamer.md`. Update
  registration: drop the `dream` skill + `dreamer` agent rows from
  `docs/design-docs/agent-harness.md` and regenerate
  `docs/generated/component-inventory.md` (`gen_inventory.py`).
  Contract at end: all three `load_templates()` resolve to the new dir; the 6
  template files exist only under `dream-rollouts/templates/`. Idempotence: pure
  relocation — `dream_run` self-host (router) and bare-host (`dream_phase2`) paths
  must both still load their templates.
  Acceptance: `python3 -c "import sys; sys.path.insert(0,'plugin/scripts'); import
  dream_phase1,dream_phase2,dream_router; [m.load_templates() for m in
  (dream_phase1,dream_phase2,dream_router)]"` exits 0 (no FileNotFoundError); gate
  GREEN.

- [x] **M2 — Scaffold seeds memory-as-docs.** In `scaffold.py`: remove the six
  `docs/memory/*` entries from `DIRS` (`:19-20`) and add `docs/journal`; remove the
  `("memory-bootloader.md", "docs/memory/MEMORY.md")` and
  `("progress-current.md", "docs/memory/progress/current.md")` entries from `SEEDS`
  (`:30-31`); remove the `CATEGORY_INDEXES` loop (`:87-89`, the
  adr/knowledge/openq/limitations indexes under `docs/memory/`) — keep
  `TOP_INDEXES` (product-specs/references still use `category-index.md`). Delete the
  now-unused templates `harness-init/templates/{memory-bootloader.md,
  progress-current.md}`. Rewrite `tests/test_scaffold.py` to assert the new seed set
  (creates `docs/journal/`, `docs/design-docs/`, AGENTS.md; creates **no**
  `docs/memory` and **no** `MEMORY.md`).
  Idempotence: scaffold stays CREATE/SKIP idempotent and never overwrites.
  Acceptance: the Goal's `mktemp` block runs clean — `docs/journal` present, no
  `docs/memory`, `check.py --root "$tmp"` GREEN.

- [x] **M3 — Delete the dormant feeder + imprint.** `git rm` the five scripts
  `plugin/scripts/{feeder_sessionstart,feeder_firstprompt,imprint_enqueue,
  imprint_guard,imprint_run}.py` and the three tests
  `tests/{test_feeder_sessionstart,test_feeder_firstprompt,test_imprint_guard}.py`.
  (hooks.json wires only `tidy_stop`; nothing imports these — verified this
  session. `gen_inventory` scans skills/agents, not scripts, so no inventory
  change.) Grep-confirm zero remaining live importers before committing.
  Acceptance: `grep -rn "feeder_\|imprint_" plugin/scripts plugin/hooks` returns
  only matches inside comments/docs (no live import/invoke); gate GREEN.

- [ ] **M4 — Lint reconciliation.** In `lint_docs.py`: drop the four `memory/*`
  entries from `INDEXED_DIRS` (`:16-18`); drop `"MEMORY.md": 60` from `SIZE_LIMITS`
  (`:19`); drop `"docs/memory/MEMORY.md"` from `PROTECTED_PATHS` (`:34-35`); remove
  the three `p.name == "MEMORY.md"` special-cases (frontmatter-exempt `:76`,
  kebab-name-exempt `:127`, size tighten-only `:143`). Update/trim
  `tests/test_lint_docs.py`'s MEMORY.md D7/D4 cases. Confirm `MACHINE_DOCS` (`:24`)
  names no `docs/memory` path.
  Acceptance: gate GREEN; the Goal's fresh-temp-repo gate is still GREEN (a host
  with no `docs/memory` no longer trips a missing-index or missing-bootloader lint).

- [ ] **M5 — Host-facing docs + templates rewrite.** Rewrite the stale portable
  instructions to the memory-as-docs + on-demand-pull model:
  `plugin/skills/harness-init/SKILL.md` step 4 (migration mentions of `memory/`)
  and step 9 (drop "fill `docs/memory/progress/current.md`" and the two "feeder
  activates once `docs/memory/MEMORY.md` exists" hand-off lines → orient from
  active ExecPlans + design-docs index + latest journal, the AGENTS.md operating
  model); templates `agents-md.md`, `agent-harness.md`, `security.md`,
  `reliability.md`, and `references/migration.md` (drop `docs/memory` paths;
  describe the docs-home taxonomy, the journal ledger, and the pull read path).
  Add one tracker row: existing `docs/memory` hosts migrate on demand (the Scope
  decision). Pure-doc milestone — completion gate covers it.

- [ ] **M6 — Completion gate.** Self-review the full diff
  (`git diff 46ad95e..HEAD`) against the Goal. Dispatch review personas **as Opus
  4.8 high subagents (NOT codex — standing user override)**: review-arch +
  review-reliability always; **add review-security** (the diff edits `scaffold.py`,
  which writes `.git/hooks/pre-commit` + `.gitignore`, and deletes T-guarded
  dormant code). Run the docs-sync pass (`docs_sync.py run --base 46ad95e`).
  P1 → fix + rerun gate; P2 → Feedback + tracker. All SATISFIED → fill Outcomes,
  `status: completed`, `git mv` to `completed/`, update `QUALITY_SCORE.md` if grades
  changed, commit. Re-prove the Goal's fresh-temp-repo block end-to-end.

## Progress log
- 2026-06-14: plan created off `46ad95e` (self-host gate GREEN, 212 tests).
  Brainstormed boundary via blast-radius map + 2 user decisions (hard-delete;
  plugin-going-forward-only). Spec design reused from `memory-architecture.md` (no
  new design-doc per PLANS.md two-docs rule).
- 2026-06-14: **M1 done.** `git mv` the 6 dreaming templates to
  `dream-rollouts/templates/`; repointed `dream_phase1/phase2/router.load_templates`
  to the new dir; deleted `plugin/skills/dream/` + `plugin/agents/dreamer.md`; pulled
  their two rows from the `agent-harness.md` component table + regenerated the
  inventory. Acceptance: all three `load_templates()` resolve (each returns its
  2-tuple) — no engine logic touched. Gate GREEN. Residual stale *prose* mentions of
  the retired `dreamer`/`dream` in self-host living docs (DESIGN.md, QUALITY_SCORE.md,
  core-beliefs.md, SECURITY.md, agent-harness prose, memory-architecture L100) are
  gate-safe and folded into M5's doc sweep.
- 2026-06-14: **M2 done.** `scaffold.py` no longer seeds `docs/memory/*` (DIRS +
  the two bootloader/progress SEEDS + the category-index loop removed); seeds
  `docs/journal/` instead. Deleted the now-unused `memory-bootloader.md` +
  `progress-current.md` templates. `test_scaffold.py` rewritten to the new seed set
  + a `test_memory_as_docs_no_legacy_memory_layer` asserting no `docs/memory` and no
  `MEMORY.md` anywhere. Acceptance MET end-to-end: `scaffold.py --root <fresh tmp>`
  → no `docs/memory`, no `MEMORY.md`, has `docs/journal`, and `check.py --root <tmp>`
  GREEN — a NEW port is born memory-as-docs AND lint-clean. Self-host gate GREEN (11
  scaffold tests).

## Surprises & discoveries
- 2026-06-14 (M2): the stale `memory/*` lint constants are already INERT on a
  memory-as-docs host — `check_indexes` skips non-existent/empty dirs
  (`lint_docs.py:154`) and the `MEMORY.md` size/protected entries only fire when
  that file exists. So M2 reaches a GREEN fresh-host gate WITHOUT M4; M4 is pure
  dead-constant cleanup, not a prerequisite. Confirms the milestones are
  independent (each gate-GREEN on its own).
- 2026-06-14 (M3): one live coupling beyond the dormant scripts — `imprint_guard`
  sat in `lint_structure.ALLOWED_IMPORTS` (the S1 inter-script import allowlist).
  Harmless to leave (an unused allowlist entry can't FAIL — S1 only rejects imports
  NOT in the set), but removed it as dead. The only OTHER remaining `feeder_/imprint_`
  references are the host-facing `agent-harness.md` TEMPLATE (unlinted plugin source
  → M5) and historical completed ExecPlans (immutable history).

## Decision log
- 2026-06-14 (user): **hard-delete** the old loop (feeder_* + imprint_* + the
  `dream` skill + `dreamer` agent + their tests), not neutralize-in-place — why:
  `memory-architecture.md` already decided to retire it; the dreaming-v2 router
  supersedes the `dreamer` CONSOLIDATE step; git preserves history, so lingering
  dead code is pure debt.
- 2026-06-14 (user): **plugin going-forward only** — why: fixing the plugin makes
  every NEW port correct, the bounded reviewable change; a migration tool for
  already-`docs/memory` hosts is a second body of work (the self-host version was a
  whole milestone) and those hosts can re-port/migrate on demand. Tracked as a row,
  not built here.
- 2026-06-14: the `dream` *directory* hosts 6 LIVE templates (`stage_one_*` loaded
  by `dream_phase1` on BOTH paths, `consolidation_*` by the bare-host
  `dream_phase2`, `router_*` by `dream_router`) — so retiring the old loop means
  RELOCATING templates into `dream-rollouts/` and repointing the loaders, not
  deleting the dir blindly. Why it matters: a blind delete would break the live
  bare-host fallback.
- 2026-06-14: **`doc-gardener` / `garden` stays live** — it is the orthogonal
  docs-GC persona (owner of the tracker; referenced across core-beliefs / DESIGN /
  SECURITY / index), not part of the retired read/write memory loop. Only the
  `dreamer` CONSOLIDATE persona retires.
- 2026-06-14: **bare-host default = keep `dream_phase2` flat store** (no new code)
  — why: `memory-architecture.md` Host-adaptation decided the flat store is the
  correct fallback for a host with no docs library; once scaffold seeds
  `docs/design-docs/`, a ported host is auto-detected as self-host
  (`dream_run._has_docs_library`) and routes via `dream_router`, so the flat store
  is reached only when `dream_run` runs in a repo that never ran `harness-init`.

## Feedback (from completion gate)

## Outcomes & retrospective
