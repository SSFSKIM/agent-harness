---
status: completed
last_verified: 2026-06-21
owner: harness
type: exec-plan
description: Consolidate the two scattered agent profiles (Director + Codex worker) into one settable source + one guide each — reconcile app_server's hardcoded worker defaults to config.DEFAULTS (drift-proof, drift-tested), retire the redundant qa workspace skill, and author the two profile guides.
base_commit: 6132f9a455360c3c918de1f04b789c0076045a0f
review_level: standard
phase: packaging/04-two-agent-profiles
---
# Packaging Slice 4 — two agent profiles consolidated

## Goal
Each of the two agents the harness runs — the **Director** (the watched main
session) and the **Codex worker** (one per ticket) — has exactly **one settable
source of truth + one discoverable guide**, with the worker's posture
**drift-proof by construction**. Observable definition of done:

1. `director/worker/app_server.py`'s fallback defaults for `approval_policy` and
   `sandbox` **derive from `config.DEFAULTS["worker"]`** (no second hardcoded
   copy), so they cannot drift from the single source. A new test asserts the
   equality and **fails on the pre-change code** (where `app_server` says
   `"untrusted"` while `config.DEFAULTS` says `"on-request"`).
2. The redundant `director/workspace_skills/qa/` skill is **gone** and no longer
   installed into a worker workspace; the worker's self-QA discipline survives
   **inline** in `taxonomy._IMPL_TEMPLATE` (and rides the execplan completion
   gate the worker already runs — spec-compliance + code-quality + behavioral).
3. `.claude/DIRECTOR.md` carries a **§14 "The two agent profiles"** guide naming
   the Director profile's two halves + env contract and the worker profile's
   single source + override surface + installed-skill bundle.
4. No `agents/director/` or `agents/worker/` directories are created.
5. `python3 plugin/scripts/check.py` GREEN; the full `director` test suite green.

## Context
Implements **Slice 4 (`packaging/04`)** of the parent spec
`docs/product-specs/2026-06-21-harness-packaging-portable-template.md`
(R4.1–R4.3 + acceptance #4). The spec owns the design; this plan owns the build.
Prior slices: Slice 1 (memory retirement), Slice 2 (strict-base docs), Slice 3
(Director relocation `docs/DIRECTOR.md`→`.claude/DIRECTOR.md` + launcher
retirement) are complete. The Director manual now lives at `.claude/DIRECTOR.md`.

Key existing surfaces a novice needs:
- **`director/config.py`** — OWNS `DEFAULTS` (module docstring: "single source of
  truth"). `DEFAULTS["worker"] = {"approval_policy": "on-request", "sandbox":
  "workspace-write", "auto_review": True, "network": True, "tools": "none",
  "install_skills": False}`. A host overrides via `.harness.json`
  `director.worker`. The posture rationale (on-request + auto_review + network,
  human decision 2026-06-15, SECURITY T11) is in the `DEFAULTS` comment +
  `director/worker/autonomy.py`.
- **`director/worker/app_server.py`** — the Codex app-server JSON-RPC client.
  `thread_start(...)` (line ~348) hardcodes `approval_policy="untrusted",
  sandbox="workspace-write"`; `run_turn(...)` (line ~359) hardcodes
  `approval_policy="untrusted"`. These are **fallbacks for direct/test callers** —
  every production caller (`director/run.py:243,247,334,350`) passes the resolved
  posture **explicitly**, so the defaults are never exercised in a real run. The
  `"untrusted"` literal is the pre-2026-06-15 conservative value, now **stale**
  vs. `config.DEFAULTS["worker"]["approval_policy"]="on-request"`.
- **`director/worker/autonomy.py`** — already sources `APPROVAL_POLICY` /
  `SANDBOX` from `config.DEFAULTS["worker"]` (the precedent pattern this plan
  mirrors into `app_server`). `worker/__init__.py` is a docstring only (no eager
  imports), so `from director import config` inside `app_server` cannot create an
  import cycle — confirmed; `autonomy` already does exactly this.
- **`director/workspace_skills/`** — the vendored Codex-worker skill bundle,
  installed into each worker workspace by `director/run.py:install_workspace_skills`
  (globs the whole tree). `commit/push/pull/land/linear/debug` are vendored from
  Symphony (`ATTRIBUTION.md`); **`qa/` is harness-authored** (not in
  ATTRIBUTION) and so is safe to retire on its own.
- **`director/taxonomy.py`** — `_IMPL_TEMPLATE` frames every impl worker. Lines
  ~45-47 tell the worker to follow `plugin/skills/execplan/SKILL.md` and run the
  completion gate; lines ~66-85 inline a 5-step SELF-QA discipline; line ~69
  points at the `qa` skill for test-writing detail.
- **`.claude/DIRECTOR.md`** — the central Director manual. §0 (standing up), §11
  (`.harness.json director` config block, incl. the `director.worker` posture
  override + `$VAR` indirection naming `DIRECTOR_TEAM`). §13 is currently last.
- Env contract surfaces (read via `os.environ`, falling back to repo-root `.env`,
  gitignored): `LINEAR_API_KEY` (`director/board/linear.py`,
  `director/worker/tools.py`), `GH_TOKEN` (worker gh ops, declared in
  `.harness.json` `worker_policy.worker_env`), `DIRECTOR_TEAM` (the `team` knob
  via `$VAR`). The human confirmed the QA-process redundancy directly: "QA
  process is sort of already-woven into execplan steps — code quality review,
  spec compliance review, and behavioral tests as needed."

## Approach (self-generated alternatives)
Two axes: how to make app_server drift-proof, and where the two guides live.

**App_server reconciliation**
- A: **Source the default args from `config.DEFAULTS["worker"]`** —
  `from director import config` and set
  `approval_policy=config.DEFAULTS["worker"]["approval_policy"]`,
  `sandbox=config.DEFAULTS["worker"]["sandbox"]` as the parameter defaults
  (evaluated once at import; there is exactly one value, in config). Cannot drift
  by construction. Tradeoff: changes the direct-caller fallback from `"untrusted"`
  → `"on-request"` (safe — no production caller relies on it; the mock ignores
  policy values, so no test breaks; the change makes the fallback *match* the
  documented, human-sanctioned default rather than the stale pre-decision one).
- B: **Keep the literal defaults, add a guard/test** asserting they equal
  `config.DEFAULTS`. Tradeoff: detects drift but does not prevent it — two copies
  still exist, and the test would have to be written to *currently fail* (they
  disagree today), forcing the literal to change anyway. Strictly worse than A.
- **Chosen: A** — "cannot drift by construction" is the project's governing
  principle (no-drift-by-construction; `autonomy.py` already sets the precedent).
  B's two-copies-plus-detector is exactly what A eliminates.

**Guide placement**
- A: **One new `.claude/DIRECTOR.md` §14 "The two agent profiles"**, two
  subsections (Director / Worker), each pointing to its single source (§0/§11/
  `.env`; `config.DEFAULTS`/§11/`workspace_skills/`) rather than duplicating
  values. Tradeoff: DIRECTOR.md is outside the `docs/` lint scope (no D5 safety
  net on its links), so link accuracy is on me.
- B: **A new `docs/design-docs/agent-profiles.md`** in the knowledge graph
  (navigable, D5-linted). Tradeoff: adds a docs-graph node + index entry + its
  own drift surface; splits the worker guide away from §11 (which already
  documents `director.worker`) and the Director guide away from §0/§11.
- **Chosen: A** — co-locating both guides in the central manual operators already
  read mirrors the spec's "the two agent profiles" framing exactly, keeps each
  guide beside the config it explains, and avoids a new drift-prone docs node
  ("skills point, docs explain" / no-drift-by-construction). I will hand-verify
  the few internal references since D5 does not cover `.claude/`.

## Assumptions & open questions (self-interrogation)
- **Assumption — the app_server defaults are fallbacks only.** Verified: all four
  production call sites (`run.py:243,247,334,350`) pass `approval_policy`/`sandbox`
  explicitly from the resolved posture. *If wrong* (some path relied on the
  `"untrusted"` fallback), flipping to `"on-request"` would widen that path's
  posture. Mitigated: grep of every `.thread_start(`/`.run_turn(` caller confirms
  explicit posture in production; the reliability persona re-checks.
- **Assumption — flipping the default breaks no test.** Verified: every
  `app_server`/`seam` test drives `_mock_app_server.py`, which dispatches on the
  `scenario` argv and never reads `approvalPolicy`/`sandbox` (line 69). So the
  approval scenario still fires regardless of the default. *If wrong*, a seam test
  would fail at M1's gate — caught immediately.
- **Assumption — retiring `qa` loses no worker capability.** The execplan
  completion gate (which every impl worker runs) already does spec-compliance +
  code-quality + behavioral checks; `_IMPL_TEMPLATE` inlines the 5-step SELF-QA
  discipline + the PR-self-description requirement (via the `push` skill). The
  `qa` skill only elaborated test-writing detail already summarized inline. Human
  confirmed. *If wrong* (some unique, load-bearing instruction lived only in
  `qa`), I relocate it inline before deleting — checked during M2.
- **Open — does `run.py` need editing to stop installing `qa`?** Resolved
  autonomously: **no.** `install_workspace_skills` globs the whole
  `workspace_skills/` tree, so deleting the `qa/` directory removes it from
  installation with zero code change.
- **Open — should the worker guide duplicate the `DEFAULTS["worker"]` knob
  values?** Resolved: **no** — the guide *points* to `config.DEFAULTS["worker"]`
  as the single source (values would be a second copy = the very drift this slice
  removes). Not a taste fork; recorded here.

## Milestones

- **M1 — Worker posture drift-proofed (R4.2 code + drift test).** Scope:
  `director/worker/app_server.py` + a new test. Add `from director import config`
  and replace the two hardcoded `"untrusted"` literals (and the `"workspace-write"`
  literal) in `thread_start` / `run_turn` signatures with
  `config.DEFAULTS["worker"]["approval_policy"]` / `["sandbox"]`, leaving the
  inline `# SandboxMode enum (hyphenated)` clarity comment and updating the stale
  comments. Add `tests/test_director_app_server.py::test_app_server_defaults_match_config`
  that introspects `AppServerClient.thread_start` / `run_turn` signature defaults
  (via `inspect.signature`) and asserts each equals the corresponding
  `config.DEFAULTS["worker"]` value. At the end, the app_server fallback posture
  is a *view* of the single source (no second copy), and the new test proves it.
  Run: `cd tests && PYTHONPATH=..:../plugin/scripts python3 -m unittest
  test_director_app_server` — expect green, incl. the new test; and confirm the
  new test FAILS against `git stash` of the change (drift caught). Acceptance: the
  new test passes on HEAD and would have failed pre-change ("untrusted"≠"on-request").

- **M2 — `qa` skill retired (R4.3).** Scope: delete
  `director/workspace_skills/qa/SKILL.md` (and the now-empty dir) via `git rm`;
  edit `director/taxonomy.py` `_IMPL_TEMPLATE` step (3) to drop the "follow the
  `qa` skill" pointer while keeping the inline test guidance (smoke/unit always +
  e2e via playwright/playwright-cli with graceful fallback) — the discipline stays,
  the standalone skill goes; update
  `tests/test_director_taxonomy.py::test_impl_prompt_includes_self_qa_and_pr_procedure`
  so it no longer asserts the `qa`-skill reference (keep the `SELF-QA` + PR-procedure
  assertions; add a negative assertion that the impl prompt no longer points at a
  separate `qa` skill, locking the retirement). At the end, no worker workspace
  installs a `qa` skill, the impl worker still self-QAs inline, and the test
  reflects the new contract. Run: `cd tests && PYTHONPATH=..:../plugin/scripts
  python3 -m unittest test_director_taxonomy` — expect green; and
  `find director/workspace_skills -name 'qa' -o -path '*qa*'` returns nothing.
  Acceptance: `grep -rn "qa skill\|workspace_skills/qa" director --include=*.py`
  returns nothing live; `_IMPL_TEMPLATE` still contains "SELF-QA".

- **M3 — The two profile guides (R4.1 + R4.2 docs).** Scope: `.claude/DIRECTOR.md`
  — add **§14 "The two agent profiles"** after §13, with two subsections.
  *Director profile* names the two halves — (a) agent identity → `.claude/`
  (`settings.json` + this manual); (b) orchestrator runtime → `.harness.json`
  `director` block (→ §11); secrets → `.env` — and the env contract:
  `LINEAR_API_KEY` (board auth), `GH_TOKEN` (worker gh ops, via
  `worker_policy.worker_env`), `DIRECTOR_TEAM` (the `team` knob via `$VAR`).
  *Worker profile* names the single source `config.DEFAULTS["worker"]` (and that
  `app_server`'s fallbacks now derive from it — cannot drift), the per-host
  override surface `.harness.json` `director.worker`, and the installed-skill set
  `director/workspace_skills/` (qa retired). Both subsections **point** to their
  sources; they do not duplicate knob values. At the end, each agent has exactly
  one discoverable guide naming exactly one settable source. Run: `python3
  plugin/scripts/check.py` — expect GREEN. Acceptance: §14 exists; a reader can
  locate every settable knob for each agent from it; no `agents/director/` or
  `agents/worker/` dir exists (`ls director ..` — none created).

## Progress log
- [x] (2026-06-21) Plan created; surface mapped (app_server drift, qa footprint,
  guide homes); import-safety + test-impact verified.
- [x] (2026-06-21) M1 — app_server `thread_start`/`run_turn` defaults sourced from
  `config.DEFAULTS["worker"]` via `_DEFAULT_APPROVAL_POLICY`/`_DEFAULT_SANDBOX`;
  `DefaultsDriftTest` added (proven to fail on the old `"untrusted"` literal).
- [x] (2026-06-21) M2 — `qa` skill `git rm`'d; `_IMPL_TEMPLATE` step (3) qa-pointer
  dropped (discipline kept inline); `test_director_taxonomy` + `test_director_run`
  updated (negative assertions lock the retirement).
- [x] (2026-06-21) M3 — `.claude/DIRECTOR.md` §14 "The two agent profiles" authored.
- [x] (2026-06-21) Completion gate: GREEN (694 tests); reviews — spec-compliance
  (codex) SATISFIED, arch SATISFIED, reliability SATISFIED (+1 P2), code-quality
  (codex) round 1 NOT-SATISFIED (P1: §14 prose overclaim) → fixed → round 2
  SATISFIED. P2s tracked.

## Surprises & discoveries
- The worker self-QA discipline is NOT only in the `qa` skill — it is inlined in
  `_IMPL_TEMPLATE` (steps 1-5) AND ridden by the execplan completion gate the
  worker runs. The `qa` skill was a third, redundant copy of test-writing detail.
  Human confirmed the redundancy directly.
- `app_server` already has the precedent for the fix next door: `autonomy.py`
  sources its `APPROVAL_POLICY`/`SANDBOX` constants from `config.DEFAULTS["worker"]`,
  and its docstring *declares* app_server's posture values "owned by
  `config.DEFAULTS`" — so the `"untrusted"` literal was genuinely stale, not an
  intentional fallback. `app_server` simply never adopted the precedent.
- **A second, INTENTIONAL `"untrusted"` lives one layer up** — `director/run.py`
  (`drive`/`run_ticket`) and `director/orchestrator.py` (`run_once`/`run_forever`)
  default a *bare* call to the conservative `"untrusted"` posture (documented at
  `run.py:232-234`, pinned by `test_default_posture_is_untrusted`). This is a
  deliberate two-tier design: every real run resolves config and passes
  `on-request` explicitly; the driver's bare-call fallback is the *most
  conservative* posture as a fail-safe. So reconciling those four to
  `config.DEFAULTS` would WIDEN a deliberate fail-safe and break its test — the
  wrong move. Code-quality's round-1 P1 was my §14 prose overclaiming "no second
  copy"; the fix was to make the prose tell the truth about the layering, NOT to
  touch run.py/orchestrator.py.
- **The git-add stale-pathspec trap struck a THIRD time** (Slices 2, 3, now 4):
  listing the just-`git rm`'d `qa/SKILL.md` in a later multi-path `git add` aborted
  the whole staging (`git add` is all-or-nothing), so the first commit captured
  only the deletion. Caught immediately via `git show --stat`; landed the rest in a
  follow-up. The durable rule (strengthened in memory): after `git rm <path>`, never
  name that path again — stage only paths still on disk.
- **codex ran the spec-compliance AND code-quality reviews synchronously this time**
  (real verdicts), unlike Slice 2 where `/codex:rescue` dispatched a background task
  and ended its turn verdict-less. The explicit "run SYNCHRONOUSLY, return the verdict
  in your final message, do not dispatch a background task" instruction worked.

## Decision log
- 2026-06-21: app_server defaults → derive from `config.DEFAULTS["worker"]`
  (Approach A) — drift-proof by construction over drift-detection (B); mirrors
  `autonomy.py`. Side effect: direct-caller fallback `approval_policy` changes
  `"untrusted"`→`"on-request"`; safe (no production caller uses the fallback; the
  mock ignores policy; the new value is the human-sanctioned default, not a
  widening past it).
- 2026-06-21: both guides → `.claude/DIRECTOR.md` §14 (Approach A) over a new
  design-doc (B) — co-located with the config they explain, mirrors the spec's
  "two profiles" framing, no new drift-prone docs-graph node. Accept that D5 does
  not lint `.claude/`; hand-verify references.
- 2026-06-21: do NOT edit `run.py` for the qa retirement — `install_workspace_skills`
  globs the tree, so deleting the dir suffices.
- 2026-06-21: worker guide POINTS to `config.DEFAULTS["worker"]`; does not copy
  the knob values (a copy would be the drift this slice removes).

## Feedback (from completion gate)
All four reviews SATISFIED. One P1 was caught and fixed in-gate; two P2s + two
proposed rules are tracked (also in `docs/exec-plans/tech-debt-tracker.md`).

- **P1 (code-quality round 1, FIXED) — §14 prose overclaim.** `.claude/DIRECTOR.md`
  §14 said the worker posture has "no second copy," but `director/run.py:225,260`
  and `director/orchestrator.py:522,818` default a bare call to `"untrusted"`.
  Resolution: those literals are *intentional* (a conservative fail-safe, pinned by
  `test_default_posture_is_untrusted`), so the fix was to reword §14 to state the
  truth (resolved runs pass posture explicitly; the wire client's fallback derives
  from config; the driver's bare-call default is conservative-by-design), NOT to
  change run.py/orchestrator.py. Fixed in `ec894ac`, re-reviewed → SATISFIED.
- **P2 (reliability) — driver-layer posture-default tier is unnamed.** The
  intentional conservative `"untrusted"` at `run.py:225,260` + `orchestrator.py:522,818`
  was re-flagged by reviewers as a drift surface because it is an un-named literal
  that re-states a posture string. Consider promoting it to a named constant (e.g.
  `run.CONSERVATIVE_POSTURE`) and/or a one-line doc so a future reviewer reads it as
  a deliberate second tier, not drift; or make the driver posture a required kwarg so
  no fallback literal exists. Tracked.
- **P2 (code-quality) — stale `qa` pointers in a historical spec.**
  `docs/product-specs/2026-06-16-worker-qa-and-serialized-pr-merge.md:109,128` (Korean
  Design/components prose) point at the now-deleted `director/workspace_skills/qa/SKILL.md`;
  the same spec already carries pre-Slice-3 `docs/DIRECTOR.md` mentions (122,131) left
  untouched. D5-clean (prose, not links); instance-history not shipped in the base
  (Slice 6 R6.4 strips instance specs). Doc-gardening pass: add a one-line supersession
  note or accept as historical (the Slice-3 precedent left such mentions). Tracked.
- **Proposed rule (review-arch) — codify signature-default aliasing.** ARCHITECTURE
  invariant 5's "alias from `DEFAULTS`, no second copy" examples are all module-level
  constants; this slice extends it to a *function-signature parameter default* sourced
  via a module constant (`approval_policy: str = _DEFAULT_APPROVAL_POLICY`). Name this
  form under invariant 5 so it reads as sanctioned, not a fresh judgment call. Tracked.

## Outcomes & retrospective
Slice 4 delivered exactly its Goal: the two agents the harness runs each have one
settable source + one guide, with the worker posture drift-proof by construction.

- **R4.2 (the real code change) — worker posture single-sourced.**
  `director/worker/app_server.py` now derives its `thread_start`/`run_turn` fallback
  posture from `config.DEFAULTS["worker"]` (module constants `_DEFAULT_APPROVAL_POLICY`/
  `_DEFAULT_SANDBOX`), eliminating the stale `"untrusted"` literal (predated the
  2026-06-15 `on-request` decision). `DefaultsDriftTest` asserts the equality and is
  non-vacuous — proven to fail on the old literal. No production behavior changed (every
  real caller passes posture explicitly; the mock ignores it; 694 tests green).
- **R4.3 — `qa` skill retired.** Deleted with the worker self-QA discipline preserved
  inline (`taxonomy._IMPL_TEMPLATE`) + ridden by the execplan completion gate the worker
  runs; install/taxonomy tests updated with negative assertions that lock the retirement.
- **R4.1 + R4.2 guides — `.claude/DIRECTOR.md` §14 "The two agent profiles."** Director
  profile (two config halves + env contract: GH_TOKEN/LINEAR_API_KEY/DIRECTOR_TEAM) +
  worker profile (single source + override surface + installed-skill bundle), each
  pointing to its source rather than copying knob values. No `agents/*` directory created.
- **What the reviews bought:** the value was the *interpretation*, not the mechanics —
  distinguishing app_server's genuinely-stale `"untrusted"` (reconcile, R4.2) from the
  driver layer's *intentional* conservative `"untrusted"` (leave; reconciling would widen
  a fail-safe). The §14 prose overclaim was the honest casualty of that nuance, caught by
  code-quality and fixed.
- **Process note:** the git-add stale-pathspec trap recurred a third time — the durable
  fix is mechanical discipline (never re-list a `git rm`'d path), now imperatively stated
  in memory. Codex reviews ran synchronously with explicit anti-background instructions.
- **Next:** Slice 5 (plugin cleanup + manifest update) — `plugin.json`/`marketplace.json`
  drop the memory clause + version bump, regenerate the inventory; republish is a separate
  human go/no-go.
