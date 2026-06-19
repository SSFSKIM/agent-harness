---
status: completed
last_verified: 2026-06-19
owner: harness
type: exec-plan
tags: [hooks, parity, worker, daemon, config]
description: Builds Symphony §9.4 workspace lifecycle hooks (R4) — .harness.json director.workspace.hooks (after_create/before_run/after_run/before_remove + timeout) run sh -lc Director-side with Symphony's fatal/ignored failure semantics, proven by a live demo where an after_create clone populates a workspace, a worker opens a real PR, and the merger squash-merges it.
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
  full gate GREEN.
- [x] (2026-06-19) M3 LIVE DEMO done on `SSFSKIM/agent-harness-r4-demo` (full pipeline):
  - **Phase 1** — `run_once`(MockBoard[ticket], real codex, `hooks={after_create: git clone …}`):
    the after_create hook cloned the repo into the fresh workspace (`.git/README.md/app.py/.codex`),
    the worker added `shout`, pushed `feat/r4-shout`, opened **PR #2**; reconcile enqueued the
    merge (`merge_enqueued: true`).
  - **Phase 2** — `merger.drain`: land worker rebased + confirmed mergeable + ran the smoke test,
    then **correctly refused to squash-merge and escalated** (`needs_human`) because the land
    skill's gate `plugin/scripts/check.py` is absent in the throwaway repo → `mergeReview` queued.
    (The serialized merger's safety contract working — it won't blind-merge without a green gate.)
  - **Phase 3** — Director resolves: `director_min.requeue_merge` with guidance ("no harness gate
    in this repo; smoke passes; squash-merge"), then `merger.drain` again → land worker
    **squash-merged PR #2** (`result: merged`, commit `ecd5ea1`; GitHub confirms `state: MERGED`,
    `main` now has `shout`).
  - Proves R4 (hook repo-population) AND the full escalate→Director-resolve→land merger loop.
  - Throwaway demo runners (`/tmp/r4_demo.py`, `/tmp/r4_merge.py`) not committed; commands +
    output recorded here + in Outcomes.
## Surprises & discoveries
## Decision log
- 2026-06-19: hooks run Director-side with full env (Approach B) — only the un-sandboxed
  Director reaches clone creds; trusted host config (SECURITY T15).
- 2026-06-19: after_run wired inside `drive`/`run_ticket` (Approach B) — one point, all
  dispositions.
- 2026-06-19: demo via scripted single-ticket + `merger.drain` (Approach B) — deterministic;
  the daemon loop is already validated.
## Feedback (from completion gate)
Round-1 reviews (full): review-arch SATISFIED, review-security SATISFIED, review-reliability
NOT SATISFIED (1 P1). All findings resolved inline:
- **review-reliability P1 — `run_hook` not total against subprocess-LAUNCH failure.** It
  caught only `TimeoutExpired`+returncode, not `OSError` (missing `sh`, a `cwd` deleted by a
  concurrent session). A non-fatal `before_remove`/`after_run` would then raise instead of
  swallow → crash the reap loop/daemon + skip the `rmtree`, or mask a disposition (R8).
  Fixed: `run_hook` now catches `OSError` → logs `event:error` → raises only when fatal.
  Resolves the P1 + its two derived P2s (startup-cleanup loop abort; after_run finally
  masking). Test added (`test_launch_failure_is_total`).
- **review-arch P2 — merger threaded `before_run` (FATAL) into the land lane.** A host
  `before_run` sync (`git reset --hard origin/<default>`) would reset the PR branch's commits
  away before the merge (land worker reuses the PR checkout). Fixed: `merger.main` drops
  `before_run` from the land-lane hooks (keeps `after_create` for the fresh-box re-clone).
- **review-security P2 — captured hook stderr is logged verbatim.** A host hook echoing a
  secret to its stderr would surface it in the daemon log. Fixed: SECURITY T15 extended with
  the "no secrets in hook output" host discipline (same as T3/T9).
- Proposed rules noted (after_run/before_run pairing semantics; hook-output discipline) —
  folded into T15; the pairing semantics are tested, left as a tracker doc-debt candidate.

Always-on QA (Codex was unavailable — rate-limited / no result; ran as Claude rubric agents
per CLAUDE.md fallback, [[mid-session-agents-not-dispatchable]]):
- **spec-compliance — SATISFIED**, no findings: every R1–R5 verified against the code +
  the live MERGED PR #2; non-goals respected; T15 written; tests cover acceptance 1–3.
- **review-code-quality — SATISFIED**, 2 P2s: (1) `run_hook`'s `env` param was speculative
  (only the test used it) → **dropped** (run_hook always uses the Director env); (2) the
  `60.0` hook-timeout default duplicated as a literal across config/signatures/reap →
  recorded in the tech-debt-tracker as accepted (mirrors the per-function-default convention).

All five reviews SATISFIED (arch, security, reliability, spec-compliance, code-quality).
## Outcomes & retrospective
**Shipped:** Symphony §9.4 workspace lifecycle hooks — the repo-population bridge (R4 of the
parity track). A host declares `director.workspace.hooks` ({after_create/before_run/after_run/
before_remove} + `hook_timeout_s`) in `.harness.json`; `run.run_hook` runs each `sh -lc`
Director-side with cwd=the workspace, Symphony's fatal/ignored semantics, total against
timeout + non-zero + launch failure. Wired through every dispatch path (run.main, the daemon/
batch orchestrator via `_RunState` dispatch-kwargs, the merger land lane minus `before_run`)
+ both cleanup `rmtree` sites (before_remove). Repo population is the host's `after_create`
clone — the harness stays VCS-agnostic.

**Live-validated** on `SSFSKIM/agent-harness-r4-demo` (real GitHub): a ticket drove a worker
in a workspace the `after_create` hook had just cloned; the worker opened **real PR #2**;
the serialized merger escalated (no integration gate in the throwaway repo) and, after the
Director resolved it via `requeue_merge` with guidance, **squash-merged PR #2** into `main`
(commit `ecd5ea1`, GitHub `state: MERGED`). This exercised R4 AND the full lights-out merger
escalate→Director-resolve→land loop.

**De-risk-first paid off:** a manual spike (before any code) proved the one unknown inspection
couldn't — a `workspace-write`-sandbox codex worker, with `GH_TOKEN` in `worker_env` + git's gh
credential helper, can clone→edit→push→open a PR. That settled the architecture (worker auths by
token; hook clones Director-side via keychain) and let the spec/build reflect reality, not guesses.

**What review caught:** (reliability P1) `run_hook` was only total against timeout+exit-code, not
the `OSError` launch-failure family — and this repo's concurrent-session reality (workspaces
deleted out from under a daemon) makes a vanished `cwd` real, so a non-fatal hook would have
crashed the daemon → fixed (catch `OSError`, swallow iff non-fatal). (arch P2) the merger would
have threaded a host's `before_run` sync into the land lane and reset the PR branch away → fixed
(drop `before_run` from landing). (security P2) captured hook stderr is logged → T15 host
discipline. (code-quality P2) dropped a speculative `env` param.

**Rules written:** SECURITY **T15** (workspace hooks run host-trusted, Director-side; hook output
is a host-trusted log channel). **Tracker:** the `60.0` default-literal duplication (accepted) +
the after_run/before_run pairing-semantics doc-rule (candidate).

**Deferred (future hardening):** sandbox the hooks themselves (container/vault track); the
merger-land-under-sandbox question (the land worker needs a host gate — the demo repo had none,
which is why it escalated; a real host supplies its gate).

**Parity track status:** R1–R3 (pagination/workspace-safety/daemon-recovery) + R4 (hooks) all
shipped. The Symphony adapter & workspace parity track is now CLOSED.
