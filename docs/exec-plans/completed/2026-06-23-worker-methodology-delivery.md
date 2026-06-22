---
status: completed
last_verified: 2026-06-23
owner: Director (master, dogfooded inline)
type: exec-plan
description: Vendor the methodology plugin (8 skills + 6 review agents) into each worker workspace so a worker — not just the Director — runs the full execplan gate, on either runtime.
base_commit: 901a1b1f6bd750c56977ee98103a9254b65b9a70
review_level: standard
---
# Worker methodology delivery — both plugins, both runtimes, by default

## Goal
A worker spawned with `install_skills` on receives the **full** agent-harness
methodology in its workspace, not just the git/PR/Linear workspace skills: the 8
methodology **skills** (`architecture-setup`, `docs-nav`, `docs-tree`, `execplan`,
`garden`, `harness-init`, `harness-lint`, `product-design`) AND the 6 methodology
**agents** (`review-spec-compliance`, `review-code-quality`, `review-arch`,
`review-reliability`, `review-security`, `doc-gardener`), copied into BOTH runtime
roots (`<ws>/.codex/` and `<ws>/.claude/`). Observable definition of done:
`director.run.install_worker_methodology(ws)` populates `<ws>/{.codex,.claude}/skills/`
with all 14 skills (6 workspace + 8 methodology) and `<ws>/{.codex,.claude}/agents/`
with all 6 agents; the worker can therefore **dispatch the review personas** its
execplan completion gate requires — the one thing today's delivery silently omits.
PR hygiene (`.git/info/exclude`), symlink-refusal safety, and idempotency hold for
the agents dirs exactly as they do for skills.

## Context
- Design principle (user, 2026-06-23): the Director is a *human-대행* (human proxy /
  orchestrator) — it decides **what**, never **how**. ALL real work (research,
  spec-design, plan-writing, execution, QA) is the worker's. Therefore both plugins
  — `agent-harness` (methodology) and `agent-harness-workspace` (git/PR/Linear) —
  must be available **by default to the worker**, which does all the job.
- Today's delivery: `director/run.py:install_workspace_skills` copies only
  `plugin-workspace/skills/` (6 skills) into `<ws>/.codex/skills/` + `<ws>/.claude/skills/`,
  gated by the `install_skills` knob (off by default; host opts in). See
  `.claude/DIRECTOR.md` "Installed-skill set" bullet (~574).
- The worker protocol (`director/taxonomy.py:_IMPL_TEMPLATE` + `TAXONOMY` `methodology_refs`)
  ALREADY drives the worker through execplan + `python3 plugin/scripts/check.py` +
  self-QA, referencing the methodology **by repo path** (self-hosting: the dogfood
  workspace IS an agent-harness clone, so the paths resolve). The protocol is complete;
  the gap is purely **delivery**.
- The methodology plugin: `plugin/skills/` (8 dirs) + `plugin/agents/` (6 `*.md`).
  The execplan completion gate (`plugin/skills/execplan/SKILL.md`) dispatches the
  review personas via the Task tool `subagent_type`, currently documented ONLY in the
  plugin-namespaced form (`agent-harness:review-*`).
- Memory: [[cc-codex-appserver-drop-in-verified]] (config-only adoption; both runtimes
  read the same vendored methodology from `.codex/` vs `.claude/`),
  [[mid-session-agents-not-dispatchable]] (a runtime registers agents from its `agents/`
  dir, not an arbitrary repo path — the root cause of the dispatch gap),
  [[parallel-sessions-share-master-index]] (stage only own paths at commit).

## Approach (self-generated alternatives)
- **A — Install the methodology as a *plugin* in the worker** (write the worker's
  `.claude/settings.json` enabledPlugins + a marketplace entry; Codex equivalent).
  Tradeoff: subagent namespace matches the Director (`agent-harness:review-*`), zero
  skill-text change — BUT requires the marketplace reachable from the worker. Trivial
  for the self-clone dogfood (`path: "."`), but breaks for a production host repo that
  has no agent-harness marketplace, and diverges from the existing vendoring mechanism
  Codex relies on (it reads `.codex/skills/`, not an installed plugin). Fragile,
  runtime-coupled.
- **B — Extend the existing vendoring** (copy `plugin/skills/*` + `plugin/agents/*`
  into both runtime roots, exactly as workspace skills are copied today). Tradeoff:
  robust on any host repo, offline, no marketplace dependency, identical to the
  proven mechanism + memory ("adoption is config-only"). Cost: vendored project-level
  agents resolve by **bare name** (`review-arch`), so the execplan skill's
  plugin-namespaced dispatch note must be made runtime-agnostic (a small, honest edit
  that *also* makes the published skill correct for non-plugin runtimes).
- **Chosen: B.** It is consistent with the established delivery path, the user's "simple
  copying" steer, and works for both runtimes and any host repo. The bare-name wrinkle
  is a one-line documentation fix, not an architectural cost. (Decision logged.)

## Assumptions & open questions (self-interrogation)
- Assumption: a worker runtime registers dispatchable agents from its `agents/` dir
  (`.claude/agents/` for the cc-harness Claude worker as a *project* agent → bare-name
  `subagent_type`; `.codex/agents/` for Codex, "same plugin structure" per the user).
  What breaks if wrong: the agents land but aren't dispatchable — delivery is inert.
  Mitigated by mirroring the exact dir convention skills already use, and by the
  bare-name dispatch note so the worker targets the right `subagent_type`.
- Assumption: workspace-skill names and methodology-skill names are disjoint, so both
  sets coexist in one `<root>/skills/` dir. Verified: {commit,debug,land,linear,pull,push}
  ∩ {architecture-setup,docs-nav,docs-tree,execplan,garden,harness-init,harness-lint,
  product-design} = ∅.
- Assumption: the methodology skills/agents reference agent-harness repo docs
  (`docs/PLANS.md`, `ARCHITECTURE.md`, …) by path; for the **dogfood** (workspace = a
  clone of this repo) those resolve. Full self-containment for an arbitrary production
  host repo (vendoring the grounding docs too) is OUT OF SCOPE — a recorded deferral,
  not a silent gap.
- Open: rename `install_workspace_skills` → `install_worker_methodology`? Resolved
  autonomously YES — the function now installs the whole methodology, not just
  workspace skills; the name would mislead. One production caller + 6 test references,
  all edited here.
- Open: change `taxonomy.py` methodology_refs from repo paths to invocable-skill
  references? Resolved autonomously NO — the refs are "read this doc" pointers valid in
  the self-hosting workspace, the protocol already drives the gate, and rewriting them
  is a production-host-repo concern bundled with the docs-vendoring deferral above.
- Non-goal (user-deferred to phase 3): the review-OVERLAP de-duplication (worker gate
  vs merger gate vs Director review). Untouched here.

## Milestones
- **M1 — Delivery (`director/run.py`).** Generalize the install so it vendors three
  sources — `plugin-workspace/skills/` (→ `skills/`), `plugin/skills/` (→ `skills/`),
  `plugin/agents/` (→ `agents/`) — into each of `(.codex, .claude)`. Symlink-refusal
  covers every dest parent (`<root>`, `<root>/skills`, `<root>/agents`); unlink-before-copy
  and idempotency preserved; `_exclude_injected_skills` writes `/.codex/skills/`,
  `/.codex/agents/`, `/.claude/skills/`, `/.claude/agents/`. Rename
  `install_workspace_skills` → `install_worker_methodology`; update the caller (run.py:249).
  At the end: the function delivers 14 skills + 6 agents per root. Run:
  `python3 -c "import tempfile,director.run as r; ..."` (and the unit tests in M3);
  expect every methodology skill + agent present under both roots, none staged by `git add -A`.
- **M2 — Dispatch note (`plugin/skills/execplan/SKILL.md`).** Reword the parenthetical
  so `subagent_type` is documented for both modes: `agent-harness:review-*` when the
  methodology is plugin-installed (the Director), bare `review-*` when vendored into the
  workspace's `agents/` (a worker). At the end: one skill text correct for both runtimes.
  Run: `python3 plugin/scripts/check.py` (D-rule lint on the skill); expect GREEN.
- **M3 — Tests (`tests/test_director_run.py`).** Extend the install tests: methodology
  skills (`execplan`, `product-design`) and agents (`review-spec-compliance.md`,
  `review-arch.md`) present under both `.codex` and `.claude`; the workspace `qa`-retired
  assertion stays; exclude patterns now include `/.codex/agents/` + `/.claude/agents/`
  with idempotency. Repoint all 6 `install_workspace_skills` refs to the new name.
  Run: `python3 -m unittest tests.test_director_run -v`; expect all green.
- **M4 — Docs (`.claude/DIRECTOR.md` + QUALITY_SCORE if graded).** Rewrite the
  "Installed-skill set" bullet to describe BOTH plugins (workspace skills + the 8
  methodology skills + 6 review/gardener agents) delivered to both roots, the bare-name
  dispatch consequence, and the new function name; note the production-host docs-vendoring
  deferral. At the end: the doc matches the code. Run: `python3 plugin/scripts/check.py`;
  expect GREEN (D-rules + drift).
- **M5 — Completion gate.** Full `check.py` GREEN; behavioral check (M1 temp-workspace
  install assertion captured); self-review diff vs base_commit; always-on
  review-spec-compliance → review-code-quality; standard risk personas review-arch +
  review-reliability. Process P1 (fix+rerun) / P2 (tech-debt-tracker). Complete + `git mv`
  to completed/; commit.

## Progress log
- [x] (2026-06-23) Explored: run.py install machinery (`_SKILLS_SRC`/`_SKILL_ROOTS`/
  `install_workspace_skills`/`_exclude_injected_skills`, caller gated by `install_skills`),
  taxonomy.py worker protocol (`_IMPL_TEMPLATE` self-hosts by repo path — gap is delivery,
  not protocol), plugin/{skills,agents} inventory, install tests, DIRECTOR.md bullet,
  execplan dispatch note. Confirmed the 6 review agents loaded as dispatchable plugin
  agents this session.
- [x] (2026-06-23) Plan authored + creation-time self-review. Gate GREEN; plan committed (9b5825e).
- [x] (2026-06-23) M1 — run.py: `_VENDORED_SOURCES` data-drives the 3-source install
  (workspace skills + methodology skills → `skills/`; agents → `agents/`) into both roots;
  symlink-refusal + exclude generalized to both subdirs; `_VENDORED_SUBDIRS` DERIVED from
  the sources (no drift); renamed `install_workspace_skills` → `install_worker_methodology`
  (caller + help + docstrings updated). Behavioral check: temp-workspace install → 14 skills
  + 6 agents per root, 4 exclude patterns, idempotent.
- [x] (2026-06-23) M2 — execplan SKILL.md dispatch note now documents both `subagent_type`
  forms (plugin-namespaced for the Director, bare for a vendored worker).
- [x] (2026-06-23) M3 — test_director_run: methodology skills + agents asserted in both
  roots; agents exclude patterns + idempotency; all call sites renamed. 32 tests green.
- [x] (2026-06-23) M4 — DIRECTOR.md "Installed methodology" bullet rewritten (both plugins +
  agents + bare-name dispatch + deferral); last_verified → 2026-06-23. Full gate GREEN.
- [x] (2026-06-23) M5 — gate GREEN; QA review pass complete (spec-compliance, arch,
  reliability all SATISFIED; code-quality SATISFIED-on-merits, its only blocker the
  forward-link D5 resolved by this completion's `git mv`). P2s fixed inline (see Feedback);
  deferral + 2 proposed rules tracked. Completed + `git mv` to completed/.

## Surprises & discoveries
- The worker protocol was already complete; the dispatch failure is a *delivery* gap
  (agents not registered in a runtime `agents/` dir), exactly the class in
  [[mid-session-agents-not-dispatchable]] — repo-path presence ≠ dispatchable.

## Decision log
- 2026-06-23: Chose vendoring (Approach B) over plugin-install (A) — consistency with
  the proven mechanism, both-runtime + any-host-repo robustness, "config-only adoption".
- 2026-06-23: Rename `install_workspace_skills` → `install_worker_methodology` — the
  name must tell the truth now that it installs the whole methodology.
- 2026-06-23: Leave `taxonomy.py` methodology_refs as repo paths — valid in the
  self-hosting workspace; rewriting belongs to the deferred production-host-repo work.

## Feedback (from completion gate)
All four required reviews returned SATISFIED (review-spec-compliance, review-arch,
review-reliability; review-code-quality SATISFIED on the merits of the diff — its sole
blocker was a forward-reference D5 (the tech-debt row links the plan into `completed/`
before this completion's `git mv`), which resolves on the move).
- **P1: none** on the code.
- **P2 fixed inline** (all the "rename = grep the surviving bodies, not just the links"
  class — an incomplete rename, not deferrable debt): `director/config.py:84` DEFAULTS
  comment + `director/orchestrator.py:1183` `--install-skills` help still named only
  `.codex/skills`/`.claude/skills` (omitting the now-delivered `agents/`); `_SKILL_ROOTS`
  → `_WORKER_ROOTS`; `_exclude_injected_skills` → `_exclude_injected_methodology` (+ its
  test method) since it now excludes both `skills/` and `agents/`.
- **Tracked (tech-debt-tracker.md, fix-forward):** (1) the production-host docs-vendoring
  deferral — methodology skills/agents reference agent-harness repo docs by path, so they
  self-contain only on an agent-harness clone (the dogfood), not an arbitrary host repo;
  (2) proposed DESIGN.md rule — document both `subagent_type` forms at a dual-scope persona
  dispatch site (already satisfied by the SKILL.md edit); (3) proposed RELIABILITY rule —
  the PR-hygiene exclude should cover the worktree git layout (`.git`-as-file), not only a
  `.git/` dir (pre-existing, host-config-dependent, already tracked).

## Outcomes & retrospective
**Delivered:** `install_worker_methodology` now vendors BOTH plugins (workspace skills +
the 8 methodology skills + the 6 review/gardener agents) into each worker's `.codex/` and
`.claude/`. A worker — not just the Director — can now run the whole execplan completion
gate, because its review personas are registered in a runtime `agents/` dir (the load-
bearing fix). Verified: a temp-workspace install yields 14 skills + 6 agents per root, the
4-pattern PR-hygiene exclude, and idempotency; the full gate is GREEN; 32 run-tests pass.
**Key discovery:** the worker protocol was already complete — the failure was a pure
*delivery* gap (agents not dispatchable from a repo path), the class in
[[mid-session-agents-not-dispatchable]]. **Design:** vendoring (B) over plugin-install (A)
kept adoption config-only and any-host-repo robust; the bare-name-vs-namespaced dispatch
seam is documented in the execplan skill. **Retro:** the only review findings were
stale-sibling-surfaces of my own rename — the very rule I'd authored — a good argument for
a mechanical "rename sweep" check; the production-host self-containment is the real next
step, now tracked. The Director stays a pure orchestrator; the worker now owns the methodology.
