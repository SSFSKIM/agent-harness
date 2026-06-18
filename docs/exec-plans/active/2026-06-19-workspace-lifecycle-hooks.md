---
status: active
last_verified: 2026-06-19
owner: harness
base_commit: d457aab787fd44b89e7be115c14a32ae721ceedc
review_level: full
---
# Workspace lifecycle hooks (R4) — build + live demo

## Goal
Add Symphony §9.4 workspace lifecycle hooks so a host can populate (and tear down) each
worker workspace declaratively, and prove the repo-population bridge end-to-end. Observable
definition of done:
1. `.harness.json` `director.workspace.hooks` ({after_create/before_run/after_run/
   before_remove} + `hook_timeout_s`) is loaded (fail-loud on malformed, fail-open absent),
   and each hook runs `sh -lc` with cwd=the workspace, Director-side, with Symphony's
   failure semantics (after_create/before_run fatal; after_run/before_remove ignored) —
   proven by unit tests.
2. **Live:** on `SSFSKIM/agent-harness-r4-demo`, an `after_create` clone populates a fresh
   workspace, a worker opens a **real PR**, and the serialized merger squash-merges it —
   captured end-to-end.

Full gate GREEN; parity slices 1–3 and the decider/queue unchanged.

## Context
- **Spec (owns the design):** `docs/product-specs/2026-06-19-workspace-lifecycle-hooks.md`.
- **Parent track:** `docs/product-specs/2026-06-18-symphony-adapter-workspace-parity.md`
  (R4 was its deferred non-goal) + `docs/design-docs/symphony-parity-gap.md`.
- **Symphony ref:** `docs/symphony-original/SPEC.md` §9.3 (population), §9.4 (hooks),
  §17.2 (hook ordering/semantics).
- **Spike (de-risk, done 2026-06-19):** a real codex worker (`workspace-write` + network,
  `GH_TOKEN` in `worker_env`, git's `gh auth git-credential` helper) cloned→edited→pushed→
  opened PR #1 on the throwaway repo in one turn. So the worker authenticates by `GH_TOKEN`
  env; the hook (Director-side) clones via keychain. The repo is seeded (`README.md`+`app.py`
  on `main`); `.harness.json` `worker_env` now allowlists `GH_TOKEN`.
- **Integration facts:** hook config rides the same plumbing as `install_skills`/`tools`
  (cfg → `run.main`/`orchestrator.dispatch`/`_RunState`/`merger`); `_workspace_for`
  (`run.py`) is where create happens; the two `rmtree` sites are `orchestrator._startup_recovery`
  + `reconcile` cancelled branch (parity slice 3).

## Approach (self-generated alternatives)
**Hook env:**
- A: hooks inherit the worker's deny-by-default env. — can't clone a private repo (no creds).
- B: hooks run with the Director's full env (keychain/gh reach), as trusted host config.
- **Chosen: B** — hooks are the same trust class as `codex_command`/host lints; only the
  un-sandboxed Director can reach clone credentials. Recorded as SECURITY T15.

**after_run placement:**
- A: in each caller (run.main, merger, orchestrator dispatch).
- B: inside `drive`/`run_ticket` in a best-effort `finally` so it fires once per attempt on
  every disposition.
- **Chosen: B** — one wiring point, fires on terminal/escalate/stuck/failed/cancelled alike.

**Scope of the live demo merge:**
- A: full daemon (`run_forever`) driving the demo board.
- B: a scripted single-ticket path (`run.main` → PR) + `merger.drain` (once) to land it.
- **Chosen: B** — the demo's point is the hook→populate→PR→land pipeline, not the daemon
  loop (already validated); a scripted path is deterministic and capturable.

## Assumptions & open questions
- **Assumption:** `GH_TOKEN` in `worker_env` + gh credential helper is enough for the worker
  to push/PR (spike-confirmed). *Breaks if* a fresh token/scope issue — re-mint via `gh`.
- **Assumption:** the merger's `land` lane (drives a worker through the `land` skill, gh-based)
  can squash-merge the demo PR with the same `GH_TOKEN`/network. *Open* → **M3 validates it;
  if the land worker can't merge under sandbox, fall back to a Director-side `gh pr merge`
  for the demo and record the gap** (the merger-land-under-sandbox question is a known
  follow-up, not this slice's deliverable — R5 is "merger lands it", with this fallback noted).
- **Assumption:** `sh -lc` is the right shell invocation (Symphony §9.4 conforming default).
  Matches the worker command's `bash -c` precedent in `run._command`.
- **Open:** does `after_create` failure leave a partial dir? → Resolved (spec): left for
  reuse/repopulate next attempt; §9.3 "MAY remove" not required. Idempotent.

## Milestones
- **M1 — Config + hook executor + create/run/after_run wiring (R1, R2, R3 create/run/after_run).**
  Scope: `director/config.py` + `director/run.py`. Add `DEFAULTS["workspace"]` + a `Workspace`
  dataclass + `DirectorConfig.workspace` with fail-loud validation. Add `run.run_hook(name,
  script, *, cwd, timeout_s, env, fatal)` (`sh -lc`, timeout, stderr-logged, raises iff fatal).
  `_workspace_for` returns `(ws, created_now)`. `_prepare` runs `after_create` (fatal, iff
  created_now) + `before_run` (fatal) before launch; `drive`/`run_ticket` run `after_run`
  (ignored) per attempt. Thread `hooks`/`hook_timeout_s` from `cfg.workspace` through
  `run.main`. At the end: hooks fire at create/run/after-run with correct fatality. Run:
  `python3 -m pytest tests/test_director_run.py tests/test_director_config.py -q` (add cases).
  Acceptance: spec acceptance 1–2 (malformed raises; absent→no-op; after_create create-only +
  fatal; before_run fatal; after_run swallowed; timeout kills; cwd=workspace).
- **M2 — before_remove + daemon/merger threading (R3 before_remove).**
  Scope: `director/orchestrator.py` (+ thread hook config through `dispatch`/`_RunState`/
  `_startup_recovery`/`reconcile`, and `merger` drive-kwargs). `before_remove` runs
  (best-effort, logged) before each containment-guarded `rmtree`. At the end: the daemon and
  merger paths carry hook config; teardown fires before_remove. Run:
  `python3 -m pytest tests/test_director_orchestrator.py -q` (add cases). Acceptance: spec
  acceptance 3 (before_remove fires before rmtree; a failing before_remove doesn't block it).
- **M3 — Live end-to-end demo (R5).**
  Scope: a demo `.harness.json`-style hook config (after_create = clone the throwaway repo)
  + a scripted run: a ticket → `run.main`/dispatch drives a worker in the hook-cloned
  workspace → real PR → `merger.drain` lands it (or the documented Director-side fallback).
  At the end: a captured transcript of a fresh workspace cloned by the hook, a real PR opened,
  and a squash-merge on `SSFSKIM/agent-harness-r4-demo`. Run: the scripted demo command.
  Acceptance: spec acceptance 4 — PR URL + merged state observed via `gh`.

## Progress log
- [x] (2026-06-19) Spike done (PR #1 real); spec + plan written.
- [x] (2026-06-19) M1 done. `config.py`: `DEFAULTS["workspace"]` + `Workspace` dataclass +
  `DirectorConfig.workspace` + fail-loud validation (unknown hook key rejected, bad
  type/timeout raise). `run.py`: `run_hook` (sh -lc, timeout, stderr-logged, fatal-raises);
  `_expected_ws` helper; `_workspace_for`→`(ws, created_now)`; `_prepare` runs after_create
  (fatal, create-only) + before_run (fatal); `drive`/`run_ticket` run after_run (ignored) in
  a finally; `run.main` threads `cfg.workspace` (off under --mock). Tests +16 (config ×5,
  run_hook + lifecycle ×11). Discovered: config-layer `$VAR` is whole-string only; embedded
  `$VAR` is shell-time — both work, spec clarified. 66 pass; full gate GREEN.
- [x] (2026-06-19) M2 done. `orchestrator.py`: hooks thread through `_dispatch_wave`/
  `run_forever` → `_RunState` dispatch-kwargs → `dispatch` → `run.drive` (daemon/batch
  workers now get populated workspaces); `reap` extracts hooks for `reconcile`'s
  `before_remove`; `before_remove` runs before both `rmtree` sites (reconcile cancelled +
  `_startup_recovery`), logged+ignored; `resolve_settings`/`main` thread `cfg.workspace`
  (off under --mock). `merger.main` threads hooks into the land-lane drive-kwargs. Tests +3
  (before_remove fires/doesn't-block; run_once threads after_create to the worker). 81 pass;
  full gate GREEN. Next: M3 live demo.
## Surprises & discoveries
## Decision log
- 2026-06-19: hooks run Director-side with full env (Approach B) — only the un-sandboxed
  Director reaches clone creds; trusted host config (SECURITY T15).
- 2026-06-19: after_run wired inside `drive`/`run_ticket` (Approach B) — one point, all
  dispositions.
- 2026-06-19: demo via scripted single-ticket + `merger.drain` (Approach B) — deterministic;
  the daemon loop is already validated.
## Feedback (from completion gate)
## Outcomes & retrospective
