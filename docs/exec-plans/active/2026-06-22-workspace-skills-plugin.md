---
status: active
last_verified: 2026-06-22
owner: harness
type: exec-plan
description: Package the vendored Codex-worker skills (commit/debug/land/linear/pull/push) as a standalone Apache-2.0 Claude Code plugin, repointing the worker install source to it.
base_commit: 3dce51bd580dada5df9a69353078e8a110523273
review_level: standard
---
# Workspace skills → a standalone Claude Code plugin

## Goal
The vendored Codex-worker skills currently living in `director/workspace_skills/`
(`commit`, `debug`, `land`, `linear`, `pull`, `push`) ship as a **second,
self-contained Claude Code plugin** (`agent-harness-workspace`, Apache-2.0) under
`plugin-workspace/`, registered as a second entry in
`.claude-plugin/marketplace.json`. The plugin is the **single source** for those
skills: `director/run.py:install_workspace_skills` copies them into each worker
workspace's `.codex/skills/` and `.claude/skills/` from the new location, with its
symlink-safety + idempotency + PR-exclude behavior unchanged. Definition of done
(observable): `python3 plugin/scripts/check.py` is GREEN; `git ls-files
plugin-workspace/` lists `.claude-plugin/plugin.json`, the six `skills/<name>/SKILL.md`,
`LICENSE`, `NOTICE`; `director/workspace_skills/` no longer exists; a fresh
`run.install_workspace_skills(<tmp>)` lands all six skills in both `.codex/skills/`
and `.claude/skills/`; and `python3 -m unittest discover -s tests -p
test_workspace_plugin.py -t tests` passes.

## Context
This is **phase 1** of a larger, human-endorsed initiative: make the Codex/Claude
**worker a full harness practitioner** so it runs the methodology (execplan, the
review gate, product-design, …) where the implementation actually happens, while the
Director stays an orchestrator. The worker already gets the agent-harness plugin's
review *agents* + skills delivered to its workspace (both runtimes share the plugin
structure + subagent dispatch), so the methodology gate runs at the worker.

Phase 1's scope is narrow and deliberately bounded by the human: **just package the
workspace skills as a (Claude-first) plugin.** Two questions are EXPLICITLY DEFERRED
to a later phase and must NOT be addressed here:
- Delivering the *methodology* plugin (`agent-harness`) into the worker workspace
  (the worker-runs-execplan delivery) — later phase.
- The **review-overlap question**: if the worker runs execplan's full gate, what do
  the merger gate and the Director turn-end review become (avoid triple-review)? —
  later phase. Recorded so it is not lost.

Grounding:
- `director/run.py:install_workspace_skills` — the per-workspace installer
  (`_SKILLS_SRC`, the `.codex`+`.claude` dual-target `_SKILL_ROOTS`, the symlink
  refusal, the `.git/info/exclude` PR-hygiene). All of that behavior is preserved;
  only the *source path* moves.
- `director/workspace_skills/ATTRIBUTION.md` — the six skills are **verbatim
  Apache-2.0 from `openai/symphony`** `.codex/skills/`. The repo root is MIT (R5.3),
  so the vendored bundle must carry its **own** `LICENSE` (Apache-2.0) + `NOTICE`
  rather than fold under the root MIT — the reason for a second plugin, not a fold
  into `plugin/skills/`.
- `ARCHITECTURE.md` layer law: `plugin/` is the portable machine governed by
  `lint_structure`/`gen_inventory` via a single `hl.plugin_root()`. The new plugin is
  a *vendored bundle*, intentionally kept OUTSIDE that single-plugin governance (see
  Approach) and validated by its own test instead.
- The skills are already in plugin `SKILL.md` format (name/description frontmatter
  valid for either runtime), so this is relocation + wiring, not authoring.

## Approach (self-generated alternatives)
- **A — Second governed plugin.** New `plugin-workspace/` AND extend
  `lint_structure`/`gen_inventory` to iterate multiple plugin roots so the new plugin
  is S-rule/inventory governed. Tradeoff: touches the **commit-gate lints** (live exec
  surface → pulls in review-security + a bigger blast radius) to govern vendored,
  verbatim-upstream content the S-rules were never meant to police.
- **B — Second plugin, test-governed (chosen).** New `plugin-workspace/` with its own
  `plugin.json`/`LICENSE`/`NOTICE`; the core gate lints stay single-plugin; a
  dedicated `tests/test_workspace_plugin.py` asserts the bundle's validity (plugin.json
  parses + has name/version; every `skills/<name>/SKILL.md` has `name`+`description`
  frontmatter; `LICENSE`/`NOTICE` present). Tradeoff: the new plugin is not under the
  S/D lints — acceptable because it is a vendored bundle (drift = "diverged from
  upstream", caught by the test's structural checks), and it keeps the change off the
  security-sensitive gate-lint surface.
- **C — Fold into `plugin/skills/`.** Rejected: mixes Apache-2.0 verbatim content into
  the MIT `agent-harness` plugin (license misrepresentation) and conflates the portable
  machine with a vendored worker bundle. The human endorsed two plugins.
- **Chosen: B** — smallest correct change; honors the license boundary; governs the
  bundle without touching the live-exec-surface lints. (Decision log below.)

## Assumptions & open questions (self-interrogation)
- Assumption: the six skills are byte-stable verbatim Apache-2.0 — relocating them via
  `git mv` (history-preserving) changes only their path, not content. If a skill body
  were edited it would no longer be "verbatim"; this plan does NOT edit skill bodies.
- Assumption: `director/run.py` resolves `_SKILLS_SRC` relative to `__file__`
  (`.../director/` → `.parent.parent` = repo root → `plugin-workspace/skills`). director/
  sits at repo root in this repo (mirrors the existing `_SKILLS_SRC` pattern); kept the
  same `__file__`-relative idiom rather than introducing a new resolver.
- Assumption: `install_workspace_skills` iterating `<plugin-workspace>/skills/` yields
  only the six skill dirs (LICENSE/NOTICE/plugin.json live at the plugin root, OUTSIDE
  `skills/`), so the current `if item.name == "ATTRIBUTION.md": continue` skip becomes
  unnecessary and is removed — a small simplification, not a behavior change.
- Open: directory name `plugin-workspace/` vs `workspace-plugin/` → resolved
  autonomously as `plugin-workspace/` (reads as "the workspace-skills plugin", parallel
  to `plugin/`); marketplace plugin `name: agent-harness-workspace`. Not a taste fork.
- Open: should `tests/test_director_merger.py` / `.claude/DIRECTOR.md` / ADR-0003 path
  references be updated? → yes, the live ones (the harness's own "retire = grep the
  surviving bodies" rule); archived `completed/*` plans keep their historical mentions
  (D5 ignores prose).

## Milestones
- **M1 — Scaffold the plugin + relocate the six skills.** Create
  `plugin-workspace/.claude-plugin/plugin.json` (`name: agent-harness-workspace`,
  `version: 0.1.0`, one-line description), `plugin-workspace/LICENSE` (Apache-2.0 full
  text) and `plugin-workspace/NOTICE` (the `openai/symphony` attribution, carried over
  from `ATTRIBUTION.md`). `git mv director/workspace_skills/{commit,debug,land,linear,
  pull,push}` → `plugin-workspace/skills/` (history-preserving), and `git rm`
  `director/workspace_skills/ATTRIBUTION.md` (its content now lives in NOTICE). At the
  end `plugin-workspace/skills/` holds the six skill dirs (incl. `land/land_watch.py`)
  and `director/workspace_skills/` no longer exists. Run `git ls-files plugin-workspace
  director/workspace_skills`; expect the six `skills/<name>/SKILL.md` + plugin.json +
  LICENSE + NOTICE listed and zero `director/workspace_skills/` paths.
- **M2 — Repoint the install source.** In `director/run.py`: `_SKILLS_SRC =
  Path(__file__).resolve().parent.parent / "plugin-workspace" / "skills"`, and drop the
  now-dead `ATTRIBUTION.md` skip in the iterdir loop. Preserve EVERYTHING else (the
  `_SKILL_ROOTS` dual-target, the symlink refusal, the per-target unlink-before-copy,
  the `.git/info/exclude` exclude). At the end a worker install sources from the plugin.
  Run `python3 -m unittest discover -s tests -p test_director_run.py -t tests`; expect
  OK (the install + idempotency + symlink-safety tests still pass, now reading the new
  location).
- **M3 — Register in the marketplace + add the validation test.** Add a second entry to
  `.claude-plugin/marketplace.json` `plugins` (`name: agent-harness-workspace`,
  `source: ./plugin-workspace`, description naming the six worker skills + Apache-2.0
  provenance). Add `tests/test_workspace_plugin.py`: plugin.json parses with
  `name`/`version`; each `plugin-workspace/skills/*/SKILL.md` has non-empty `name` +
  `description` frontmatter; `LICENSE` + `NOTICE` exist and NOTICE names openai/symphony.
  At the end both plugins are advertised and the bundle is structurally validated by CI.
  Run `python3 -m unittest discover -s tests -p test_workspace_plugin.py -t tests`;
  expect OK.
- **M4 — Repoint live cross-references + full gate.** Update the live pointers to the
  old path: `tests/test_director_merger.py` (the land-skill path it computes from
  `merger.__file__`), `.claude/DIRECTOR.md` (the "Installed-skill set →
  `director/workspace_skills/`" prose), and `docs/adr/0003-lights-out-director.md` (the
  `workspace_skills/linear` pointer). Leave `docs/exec-plans/completed/*` historical
  mentions untouched (D5 ignores prose; not a history rewrite). At the end no LIVE
  reference points at `director/workspace_skills/`. Run `python3 plugin/scripts/check.py`;
  expect GREEN, and `grep -rn "director/workspace_skills" --include=*.py --include=*.md .
  | grep -v completed/` returns nothing.

## Progress log
- [ ] (2026-06-22) plan created on branch `workspace-skills-plugin`

## Surprises & discoveries

## Decision log
- 2026-06-22: chose Approach B (test-governed second plugin) over A
  (multi-plugin-aware gate lints) — keeps the change off the live-exec-surface gate
  lints and matches the vendored-bundle nature of the skills; over C (fold into
  `plugin/`) — preserves the MIT/Apache-2.0 license boundary the human endorsed.
- 2026-06-22: feature-branch + PR rather than commit-to-master (overriding CLAUDE.md's
  commit-to-master rule) — human decision, to isolate from concurrent dogfood `director/`
  work on `master` touching the same `install_workspace_skills` area.

## Feedback (from completion gate)

## Outcomes & retrospective
