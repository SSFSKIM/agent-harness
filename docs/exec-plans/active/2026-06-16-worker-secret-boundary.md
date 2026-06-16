---
status: active
last_verified: 2026-06-16
owner: harness
base_commit: 53a3e49325103aa694a9bc3715513711e804d635
review_level: targeted
---
# Worker secret boundary — host policy surface + deny-by-default env

This is **M1 of a three-plan arc** that closes the credential-exfiltration residual
in `docs/SECURITY.md` T11. It is the only part enforceable *without* container
isolation, and it lays the host-facing contract the other two plans build on:
- **M1 (this plan)** — a secret-agnostic, host-declared policy surface plus
  deny-by-default construction of the worker subprocess environment. Closes the
  **env-inheritance** exfil channel.
- **M2 (next plan, container isolation)** — closes the two channels that need an OS
  boundary: filesystem-wide reads (the host `.env` read directly off disk) and
  egress (a read secret POSTed out). codex-cli 0.139.0 has **no native domain
  allowlist** (probe-confirmed: only `sandbox_workspace_write.network_access` bool;
  `allowed_domains`/`network_proxy`/… all rejected as unknown config), so an
  enforceable egress allowlist is coupled to a container (network namespace + a
  filtering proxy), not to codex config. M1 *declares* the allowlist; M2 *enforces* it.
- **M3 (final plan, capability mediation)** — a vault-proxy on GCP Secret Manager
  (backend fixed by the human, 2026-06-16) so a secretless worker can still perform
  privileged external actions. The worker's own model auth (codex authenticates via
  `~/.codex`, a file, not an env var) is its own ephemeral-credential case handled here.

## Goal
A real codex worker spawned by the harness no longer inherits **secret environment
variables** from the Director's process. Observable definition of done: with a
sentinel secret exported in the parent process env (`SENTINEL_SECRET=leakme`, and the
real `LINEAR_API_KEY`), a spawned worker's `os.environ` provably **does not contain**
`SENTINEL_SECRET` or `LINEAR_API_KEY`, while an operational base var (`PATH`) **is**
present and a real worker still completes one turn. The allowed set is **host-declared**
in `<repo-root>/.harness.json` under a new `worker_policy` key (deny-by-default: an
absent file or key yields empty allowlists), consistent with ARCHITECTURE invariant 7
(a host's rules are the host's, not hardcoded in the machine). Egress enforcement and
filesystem-wide-read closure are explicitly **out of scope** here and are restated as
the remaining residual in `docs/SECURITY.md` T11 (deferred to M2).

## Context
- **Residual being closed:** `docs/SECURITY.md` T11 ("Worker posture"), specifically
  the "Confirmed residual — credential exfiltration that BYPASSES T10" paragraph: a
  prompt-injected worker reads a host credential and exfiltrates it. The residual has
  three channels — env-inheritance (this plan), fs-wide read, and egress (M2).
- **Why secret-agnostic, not a blocklist:** this harness is transplanted into *other*
  host repos (`AGENTS.md` "Porting"; `plugin/scripts/scaffold.py`; the `harness-init`
  skill). The worker spawns with `cwd=<host repo>` inside the host's filesystem, so the
  reachable secrets are the *host's* (`.env`, cloud creds, CI tokens) — unknowable to
  the harness. A boundary that enumerates "known" secret vars cannot protect unknown
  host secrets; only deny-by-default can. ARCHITECTURE invariant 7 already encodes this
  shape (host-owned config via `.harness.json`); `worker_policy` is one more such key.
- **Term definitions.** *deny-by-default env*: the worker subprocess receives a freshly
  *constructed* environment — an operational base (the non-secret vars a process needs
  to run: `PATH`, `HOME`, …) plus the host-declared `worker_env` keys — never a copy of
  the Director's full env. *secret-agnostic*: the boundary never decides which vars are
  "secret"; it denies everything not explicitly allowed. *operational base*: the small,
  hardcoded set of non-secret vars codex needs to start (resolved empirically in M2).
- **Spawn seam (where the change lands):** `director/run.py:_prepare` builds
  `AppServerClient(command, cwd=ws, …)` (line ~85); `director/worker/app_server.py`
  `start()` calls `subprocess.Popen(self.command, cwd=self.cwd, …)` (line ~98) **with no
  `env=`**, so the worker inherits the full parent env today (`board/linear.py` reads
  `LINEAR_API_KEY` from `os.environ`, so it is present when the orchestrator runs).
- **Host-config seam:** `<root>/.harness.json`, loaded for the gate by
  `plugin/scripts/harness_lib.py:gate_config`. Our repo has none today (self-host
  defaults apply), so adding one is itself the dogfood. The director reads its own
  `worker_policy` key directly (a runtime concern), independent of `gate_config` (a
  commit-gate concern).
- **PRODUCT_SENSE.md** governs what escalates: this is mechanical security hardening,
  no taste fork — proceed autonomously.

## Approach (self-generated alternatives)
- **A — Blocklist (scrub known secret vars).** Strip `LINEAR_API_KEY`, `AWS_*`,
  `OPENAI_API_KEY`, `GITHUB_TOKEN`, … from the inherited env. Tradeoff: fails for the
  entire point — unknown host secrets in adopting repos are not enumerable; brittle and
  silently incomplete. Rejected.
- **B — Deny-by-default allowlist at the spawn seam.** Construct the worker env from a
  small operational base + host-declared `worker_env`; drop everything else. Tradeoff:
  must determine the operational base codex needs (empirical, but bounded — and codex's
  file-based auth means HOME suffices). Safe for unknown host secrets. **Chosen.**
- **C — Defer env-deny to the container (M2) and do nothing now.** Tradeoff: leaves the
  cheapest, already-enforceable channel open while the container's larger unknowns are
  resolved; env vars are the *easiest* channel to leak (surfaced in `env`, crash dumps,
  child processes), so closing them is correct posture regardless of M2. Rejected — no
  reason to defer the enforceable-now layer.
- **Chosen: B.** Deny-by-default env construction at the `Popen` seam, allowlist
  host-declared in `.harness.json worker_policy`. Mirrors invariant 7.

## Assumptions & open questions (self-interrogation)
- **Assumption (VERIFIED):** codex authenticates via `~/.codex` (file), not an env var
  — `~/.codex/.codex-global-state.json` exists and `OPENAI_API_KEY` is absent from the
  env. So deny-by-default env does **not** break codex auth as long as `HOME` is in the
  base. If this were wrong (codex needed a secret env var), that var would join the base
  as an acknowledged residual (codex's own key = M3 broker territory), and M2's
  "worker still completes a turn" acceptance test would catch a too-narrow base.
- **Assumption:** the worker does not need `LINEAR_API_KEY` — the Director owns Linear
  mutations (T10 guardrail); the worker only writes code. So `worker_env: []` is correct
  for our dogfood. A future worker that needs a host service var has the host add it to
  `worker_env` — the mechanism, not a hardcode.
- **Open:** where the loader lives → resolved: `director/worker/policy.py` (the worker
  subsystem owns it), reading `<root>/.harness.json`. Not `harness_lib` (that is the
  gate's config, a different concern).
- **Open:** the exact operational base set → resolved autonomously: seed with
  `{PATH, HOME, USER, LOGNAME, SHELL, LANG, LC_ALL, LC_CTYPE, TERM, TMPDIR, TZ}` and
  lock it in M2 by the live "worker still completes a turn" check; widen only if a real
  worker fails to start, narrow if a var proves unneeded.
- **Open:** does `gate_config` choke on an unknown `worker_policy` key? → resolved:
  the director reads `.harness.json` itself; M3 verifies `check.py` stays GREEN with the
  key present (if `gate_config` is strict about unknown keys, that surfaces in the gate
  and is fixed there).

## Milestones
- **M1 — Policy surface (the host contract).** Create `director/worker/policy.py` with
  `load_worker_policy(root) -> {"worker_env": [...], "network_allowlist": [...],
  "capabilities": [...]}` that reads `<root>/.harness.json`'s `worker_policy` key and
  returns all-empty deny-by-default defaults when the file or key is absent; a malformed
  `worker_policy` (e.g. a non-list `worker_env`) **fails loud** (raises), never silently
  opens. At the end this loader exists with a documented schema and safe defaults. Run
  `python3 -m unittest tests.test_worker_policy -v`; expect green proving three cases —
  absent file → empty allowlists, present-and-valid → parsed values, malformed → raises.
- **M2 — Enforce deny-by-default env at the spawn.** Add `build_worker_env(policy,
  environ=os.environ) -> dict` to `director/worker/policy.py` (operational base copied
  from `environ` + `{k: environ[k] for k in policy["worker_env"] if k in environ}`,
  nothing else). Thread `env=` through the seam: `director/worker/app_server.py`
  `Popen(self.command, cwd=self.cwd, env=self._env, …)`, `AppServerClient(…, env=…)`,
  `director/run.py:_prepare` (load policy from the repo root, build env, pass it),
  and the orchestrator/`main` callers. At the end a worker receives only the constructed
  env. Acceptance (provable, fails-before/passes-after): a new test exports
  `SENTINEL_SECRET=leakme` in the parent env, spawns the bundled mock app-server that
  echoes its `os.environ`, and asserts `SENTINEL_SECRET` and `LINEAR_API_KEY` are
  **absent** while `PATH` is **present** — this assertion fails on `base_commit` (full
  env inherited) and passes after. Plus a live guard: `python3 -m director.run --ticket
  <throwaway stub>` drives one real codex turn to completion, proving the operational
  base is sufficient (guards the codex-auth assumption). Run `python3 -m unittest
  tests.test_worker_policy -v` (green) and the live smoke (turn completes).
- **M3 — Dogfood + honest docs.** Write `<repo-root>/.harness.json` with
  `worker_policy: {worker_env: [], network_allowlist: ["chatgpt.com",
  "api.openai.com", "github.com", "registry.npmjs.org"], capabilities: []}` — the
  `network_allowlist` is **declared, not yet enforced** (refined when M2-container wires
  the filtering proxy); our own run now uses deny-by-default env. Update
  `docs/SECURITY.md` T11 to record the env-inheritance channel **CLOSED** here, with the
  residual restated precisely: fs-wide read + egress remain open until the container
  plan, and `network_allowlist` is declared-not-enforced (codex 0.139.0 has no native
  domain allowlist — probe-confirmed). Add two `docs/exec-plans/tech-debt-tracker.md`
  entries: (a) container isolation = the enforceable closure of fs-read + egress; (b)
  codex model-key reachable in-worker = M3 vault-proxy/broker territory. At the end the
  doc no longer overstates egress as a near-term lever and the dogfood config is live.
  Run `python3 plugin/scripts/check.py`; expect GREEN (lint_structure accepts the new
  module; lint_docs accepts the edits; tests pass with the new `.harness.json` present).

## Progress log
- [ ] (2026-06-16) Plan created; base_commit recorded; creation-time self-review done.
  Remaining: implement M1 → M2 → M3, then completion gate (targeted review).

## Surprises & discoveries

## Decision log
- 2026-06-16: Backend fixed to **GCP Secret Manager** (not a pluggable abstraction) for
  the future M3 — human decision; simplifies the vault layer, accepted single-cloud
  coupling.
- 2026-06-16: **Container isolation deferred to M2** (its own plan) — human decision;
  M1 ships the enforceable-now env layer + the host contract the container plugs into.
- 2026-06-16: Boundary is **secret-agnostic deny-by-default**, not a blocklist —
  the harness cannot enumerate an adopting host's secrets (Approach A rejected).
- 2026-06-16: Egress allowlist is **declared in M1, enforced in M2** — codex-cli
  0.139.0 exposes only a boolean `network_access`, no domain allowlist (probe-confirmed),
  so per-domain enforcement requires the container's network namespace + proxy.

## Feedback (from completion gate)

## Outcomes & retrospective
