---
status: stable
last_verified: 2026-06-19
owner: harness
---
# Workspace lifecycle hooks (R4 — the repo-population bridge)

The deferred **R4** of the Symphony adapter & workspace parity track
([spec](2026-06-18-symphony-adapter-workspace-parity.md), Non-goals). Promoted from
deferred to built because the worker-PR path is now de-risked (see Validation below).
Closes Symphony §9.3–§9.4 (workspace population + lifecycle hooks).

## Problem

Director workers run in a **bare** per-ticket workspace — `_workspace_for` just
`mkdir`s `<root>/<key>` (parity slice R2). Nothing puts a **repository** in it, so a
worker has no real codebase to edit and cannot open a PR against one without manual
setup. Symphony solves this with host-configured **lifecycle hooks** (§9.4): the host
declares an `after_create`/`before_run` script that clones/syncs the repo into the fresh
workspace (§9.3 "workspace population is implementation-defined, typically via hooks"),
plus `after_run`/`before_remove` for teardown. We have **no hook mechanism at all** —
the single most repo-population-defining feature still missing.

**De-risked (2026-06-19 spike).** Before specifying, a manual spike confirmed the load-
bearing unknown: a real codex worker under the production posture (`workspace-write`
sandbox + full network), given `GH_TOKEN` in its allowlisted `worker_env` and git's
`gh auth git-credential` helper, **cloned → edited → committed → pushed → opened a real
PR** in one turn (PR #1 on the throwaway `SSFSKIM/agent-harness-r4-demo`), reporting
`pr_url`/`pr_branch` via `report_outcome` exactly as the merger consumes. So the worker
(sandboxed) authenticates by **`GH_TOKEN` env**; the hook (Director-side) clones by the
**keychain helper**. R4 automates the population step the spike did by hand.

## Requirements

- **R1 — Hook configuration.** `.harness.json` `director.workspace.hooks` declares up to
  four optional shell-command strings — `after_create`, `before_run`, `after_run`,
  `before_remove` — plus `director.workspace.hook_timeout_s` (default 60). Absent block
  or absent hook → that hook is a no-op (current behavior preserved, fail-open). A
  present-but-malformed `workspace` block **fails loud** at load (RELIABILITY R15:
  before any worker spawn), like every other config block. Hook strings support `$VAR`
  indirection like the rest of the config.
- **R2 — Hook execution.** A configured hook runs as `sh -lc <script>` with **cwd = the
  per-ticket workspace path**, under a wall-clock timeout (`hook_timeout_s`). It runs
  **Director-side** with the Director process environment (NOT the worker's deny-by-
  default sandbox env) — hooks are trusted host config (like `codex_command`), and a
  private-repo clone needs the Director's credential reach (keychain/gh). Hook
  start/failure/timeout are logged to **stderr** (the daemon-diagnostic stream). A hook's
  stdout/stderr are captured into the log on failure.
- **R3 — Lifecycle points + failure semantics (Symphony §9.4).**
  - `after_create` — runs **only when the workspace directory was newly created** in this
    call (not on reuse). Failure/timeout is **FATAL to workspace creation**: it raises, so
    dispatch fails and the ticket is never falsely marked started on a workspace that
    isn't populated.
  - `before_run` — runs **before each attempt** (every `drive`). Failure/timeout is
    **FATAL to the attempt** (raises → the dispatch becomes a `failed` disposition).
  - `after_run` — runs **after each attempt**. Failure/timeout is **logged and ignored**.
  - `before_remove` — runs **before a workspace is `rmtree`d** (startup cleanup +
    mid-flight-cancelled cleanup). Failure/timeout is **logged and ignored**.
- **R4 — Repo population is the host's hook, not harness logic.** The harness stays
  VCS-agnostic (§9.3): it only *runs* the configured command. The documented pattern is
  an `after_create` that clones (`git clone <url> .`) and/or a `before_run` that syncs
  (`git fetch && git reset --hard origin/<default>`); the harness asserts nothing about
  git. A worker that will open PRs additionally needs `GH_TOKEN` in `worker_env` (the
  parity track already supports that allowlist).
- **R5 — End-to-end validation (the live demo).** With `after_create` configured to clone
  the throwaway repo and `GH_TOKEN` in `worker_env`, a ticket drives a worker in a
  freshly-cloned workspace that opens a **real PR**, and the serialized merger lands it —
  observed on `SSFSKIM/agent-harness-r4-demo`.

## Design

Additive. No change to pagination, containment, startup recovery (parity slices 1–3), the
decider, or the queue.

### Component 1 — `director/config.py` (R1)
- `DEFAULTS["workspace"] = {"hooks": {"after_create": None, "before_run": None,
  "after_run": None, "before_remove": None}, "hook_timeout_s": 60.0}`.
- A frozen `Workspace(hooks: dict, hook_timeout_s: float)` dataclass + a `workspace:
  Workspace` field on `DirectorConfig`. `_build` validates: `hooks` is an object whose
  known keys are string-or-null (unknown keys rejected), `hook_timeout_s` a positive
  number — fail-loud on malformed (reuses `_str_or_none`/`_pos_num`). `$VAR` resolves via
  the existing `_resolve_env_deep`.

### Component 2 — `director/run.py` (R2, R3 create/run)
- `run_hook(name, script, *, cwd, timeout_s, env=None, fatal) -> None` — if `script` is
  falsy, no-op. Else `subprocess.run(["sh", "-lc", script], cwd=cwd, env=env or os.environ,
  timeout=timeout_s, capture_output=True)`. On non-zero exit or `TimeoutExpired`: log a
  structured stderr line (`{"hook": name, "event": "failed"/"timeout", "cwd", ...}` with
  captured output); if `fatal`, raise `RuntimeError`; else swallow. Always log
  `{"hook": name, "event": "start"}`.
- `_workspace_for` returns `(ws, created_now)` — `created_now = not ws.exists()` captured
  *before* `mkdir`. (Callers that ignore it keep working via tuple unpack.)
- `_prepare` threads a `hooks`/`hook_timeout_s` (defaulting to "no hooks" so existing
  callers are unchanged): after resolving the workspace, run `after_create` **fatal** iff
  `created_now`, then `before_run` **fatal**, both before launching the worker.
- `after_run` runs after the drive completes — wired in `drive` (and `run_ticket`) around
  the turn loop in a `finally`-style best-effort call so it fires on terminal/escalate/
  stuck/failed alike, never raising.
- The hook config flows from `cfg.workspace` through `run.main`, `orchestrator.dispatch`/
  `_RunState`, and `merger` drive-kwargs (the same plumbing `install_skills`/`tools` use).

### Component 3 — `director/orchestrator.py` (R3 before_remove)
- `before_remove` runs (best-effort, logged) immediately before each containment-guarded
  `shutil.rmtree` — in `_startup_recovery`'s terminal cleanup and `reconcile`'s cancelled-
  to-terminal cleanup. Hook config is threaded into `_startup_recovery` and `reconcile`
  the same way `workspace_root` already is.

### Hook env & privilege (security)
Hooks execute with the **Director's** environment and privileges — they are host-authored
config, the same trust class as `codex_command` and the host lint commands (`.harness.json`
executable config). This is intentional: only the Director (un-sandboxed) can reach the
clone credentials. A new SECURITY threat (T15) records this: a `.harness.json` workspace
hook runs host-trusted Director-side; the secret boundary it must respect is that it never
echoes credentials and its failures degrade per R3. Distinct from T11 (worker sandbox) and
T14 (Director workspace delete surface).

### Errors / edges
- Hook configured but workspace reused → `after_create` skipped, `before_run` still runs.
- `after_create` fatal-fails on a brand-new workspace → the half-prepared dir is left for
  the next attempt to reuse-or-repopulate (idempotent; Symphony §9.3 "MAY remove" is not
  required). Dispatch surfaces the failure.
- No `workspace` block → every hook is None → byte-identical to today.
- `before_remove` failure never blocks the cleanup `rmtree` (R3).

## Non-goals
- No built-in VCS/clone logic — population is the host's hook (§9.3). The demo's clone
  command lives in `.harness.json`, not in harness code.
- No per-stage or per-ticket hook variation (one hook set per host).
- No hook output parsing / structured results — hooks are side-effecting shell only.
- No change to the worker secret boundary beyond using the already-supported
  `worker_env` `GH_TOKEN` allowlist (parity track).
- No sandboxing of the hooks themselves (they are Director-trusted host config).

## Acceptance criteria
1. **R1:** a malformed `director.workspace` (e.g. `hooks.after_create` a number, or a
   negative `hook_timeout_s`) raises at `load_director_config`; an absent block yields
   all-None hooks; `$VAR` in a hook string resolves.
2. **R2/R3:** unit tests with a fake script prove: `after_create` runs only on creation
   (not reuse) and its non-zero exit RAISES; `before_run` runs every prepare and its
   failure RAISES; `after_run`/`before_remove` failures are swallowed; a hook exceeding
   `hook_timeout_s` is killed and (for fatal hooks) raises. cwd is the workspace.
3. **R3 (before_remove):** an orchestrator test shows `before_remove` fires before the
   `rmtree` in startup cleanup, and a failing `before_remove` does not block the delete.
4. **R5 (live):** on `SSFSKIM/agent-harness-r4-demo`, a ticket → worker (workspace cloned
   by `after_create`) → real PR → merger squash-merge, captured end-to-end. Recorded as
   the ExecPlan's behavioral acceptance.
5. The full gate (`python3 plugin/scripts/check.py`) is GREEN; no parity-slice behavior
   changes.
