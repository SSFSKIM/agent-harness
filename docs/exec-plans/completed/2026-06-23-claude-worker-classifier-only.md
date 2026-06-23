---
status: completed
last_verified: 2026-06-24
owner: director (SSFSKIM)
type: exec-plan
description: Disable the claude worker's OS-level sandbox (PR3) — dispatch it classifier-only via a per-runtime sandbox posture override.
base_commit: 89f363fbb4861a6686ce6f4ef86cdfd52a1ea85f
review_level: targeted
---
# Claude worker: classifier-only (discard the OS-level sandbox)

## Goal
The `claude` worker runtime runs with **no OS-level Bash sandbox** — relying solely
on the Agent-SDK auto-mode permission classifier (and its hard-block list) as the
action boundary. Observable: a dispatch with `--worker claude` sends
`sandbox=danger-full-access` on `thread/start` (the adapter's `resolveSandbox`
short-circuit → no `sandbox`, no deny rules, no egress allowlist → `permissionMode:
auto` only), while the default `codex` runtime is **unchanged** (still
`workspace-write`). Done = a config-driven per-runtime sandbox posture exists, both
drive paths (`run.py`, `orchestrator.py`) honor it, `.harness.json` sets
`claude → danger-full-access`, gate GREEN, and the decision is recorded as
INFORMED-ACCEPTED in SECURITY.md + the tech-debt tracker.

## Context
- Decision (human, 2026-06-23): discard PR3's OS-level sandboxing for the claude
  worker. Rationale: sandbox denials are real productivity friction (granular
  denials buried in compound commands, hangs, out-of-workspace writes — see the
  LIN-27 dogfood loopback-bind stall), and the auto-mode classifier's hard-block
  list (curl|bash, exfil to external endpoints, prod deploys, mass deletion, IAM
  grants, force-push, destructive git, terraform destroy) is trusted as sufficient
  for this deployment. INFORMED-ACCEPTED: safe only where reachable credentials are
  throwaway (consistent with the pre-existing T11 stance).
- Adapter behavior (`worker-runtime/app-server/src/sandbox.ts:48`):
  `if (!args.mode || args.mode === "danger-full-access") return {}` — so
  `danger-full-access` is the existing "no OS sandbox" signal; this needs **zero
  adapter change** (keeps the vendored copy in sync with the producer).
- Plumbing: `director.worker.sandbox` (`config.py:100`, default `workspace-write`)
  is global; sent via `run.py:574` and `orchestrator.py:1289` (`posture.sandbox`).
  `danger-full-access` is a valid posture value (`config.py:125`).
- SECURITY.md §"Worker-runtime caveat (`--worker claude`)" (currently "OS sandbox
  now applies") must flip to "intentionally disabled — classifier is the boundary".

## Approach (self-generated alternatives)
- A: **Director-side per-runtime sandbox override** — new config
  `director.worker_runtime_sandbox: {name: mode}`; `resolve_worker_sandbox(cfg,
  worker)` returns the override or falls back to `posture.sandbox`; both drive paths
  call it; `.harness.json` sets `{"claude": "danger-full-access"}`. Tradeoff:
  adds a small config surface; keeps the vendored adapter pristine (no fork, no TS
  rebuild); scoped to claude; reversible by one line.
- B: **Fork the vendored adapter** — make `resolveSandbox` a no-op + rebuild dist.
  Tradeoff: most literal "discard PR3", but forks our copy from the producer
  (maintenance drift), needs a TS rebuild, and is all-or-nothing (can't keep codex's
  posture model intact through the same adapter if shared later).
- Chosen: **A** — smallest blast radius, no rebuild, no producer drift, scoped, and
  the decision lives declaratively in config (where a deployment policy belongs).

## Assumptions & open questions (self-interrogation)
- Assumption: `danger-full-access` → adapter returns `{}` → SDK runs `permissionMode:
  auto` with no sandbox/deny/egress. If wrong (adapter applies *something* for
  danger-full-access), the worker would still be sandboxed — falsified by reading
  `sandbox.ts:48` + `handlers.ts:67-68` (only sets `cfg.sandbox`/`cfg.settings` when
  the plan is non-empty).
- Assumption: the override must key off the **effective** runtime (default selector
  when `--worker` omitted), mirroring `resolve_worker_command`'s `name = cfg.
  worker_runtime if worker is None else worker`. Otherwise the default codex run
  wouldn't resolve correctly.
- Open: should the zero-friction **credential-read deny** rules be retained while
  only the OS Bash sandbox is dropped? → Resolved autonomously as **no** (full
  classifier-only) to match the human's literal "no sandbox, just auto mode
  permission classifier" + keep the adapter pristine; retaining them would require an
  adapter fork (B). Noted as a one-line follow-up if desired (not a taste fork worth
  blocking on — the human accepted the residual).

## Milestones
- M1 — **Config: per-runtime sandbox override.** At the end `DirectorConfig` carries
  `worker_runtime_sandbox: dict` (validated: dict of `{str: mode∈_SANDBOX_VALUES}`)
  and `config.resolve_worker_sandbox(cfg, worker)` exists. Run
  `python3 -m unittest discover -s tests -p test_director_config.py`; expect new
  tests green (valid override, invalid mode fails loud, unknown worker → posture
  default).
- M2 — **Wire both drive paths.** At the end `run.py` and `orchestrator.py` send
  `resolve_worker_sandbox(cfg, worker)` instead of `posture.sandbox`. Run the gate;
  expect existing run/orchestrator tests green + a focused test asserting claude→
  danger-full-access, codex→workspace-write.
- M3 — **Activate + document.** At the end `.harness.json` sets
  `director.worker_runtime_sandbox = {"claude": "danger-full-access"}`; SECURITY.md
  claude caveat flipped to INFORMED-ACCEPTED classifier-only; tracker PR3 row
  annotated. Run `python3 plugin/scripts/check.py`; expect GREEN.

## Progress log
- [x] (2026-06-23) plan created; base_commit recorded.
- [x] (2026-06-23) M1 — config: `worker_runtime_sandbox` field + validation +
  `resolve_worker_sandbox`; 9 config tests added (68 pass).
- [x] (2026-06-23) M2 — wired `run.py` + `orchestrator.py` (setup dict `worker_sandbox`)
  to `resolve_worker_sandbox`; WiringTest assertion added.
- [x] (2026-06-23) M3 — `.harness.json` `worker_runtime_sandbox={"claude":
  "danger-full-access"}`; SECURITY.md caveat flipped to INFORMED-ACCEPTED classifier-only;
  tracker PR3 row marked superseded-by-decision. Gate GREEN.
- [x] (2026-06-24) completion reviews: spec-compliance (codex) SATISFIED; security
  (review-security) SATISFIED (0 P1); code-quality (codex) NOT-SATISFIED → 2 P2s
  fix-forwarded (`1b02b35`), gate re-GREEN (70 tests).
- [x] (2026-06-24) code-quality RE-VERIFY (codex): both P2 claims RESOLVED, no remaining
  findings → SATISFIED. All verdicts SATISFIED; plan completed + moved.

## Surprises & discoveries
- The adapter's `danger-full-access → {}` short-circuit (`sandbox.ts:48`) means disabling
  the OS sandbox needs ZERO adapter change — the Director just selects the posture. Keeps
  the vendored copy in sync with the producer.
- `danger-full-access` drops the adapter's egress allowlist + cred-read deny TOO (all-or-
  nothing in `resolveSandbox`), so classifier-only here means no egress allowlist either —
  consistent with the human's "auto mode blocks egress" stance; recorded in the residual.

## Decision log
- 2026-06-23: disable claude OS sandbox via Director-side per-runtime posture
  (`danger-full-access`), not an adapter fork — keeps vendored copy in sync, no
  rebuild, scoped, reversible.
- 2026-06-23: full classifier-only (drop cred-deny + egress allowlist too), per the
  human's literal decision + adapter-pristine; retention is a noted follow-up.

## Feedback (from completion gate)
- **P2 (code-quality + security, corroborated) — fixed:** the mode membership test lacked
  an `isinstance(mode, str)` guard, so a non-string value (`{"claude": []}`) raised a raw
  `TypeError` instead of the named `ValueError` the contract promises. Added the guard.
- **P2 (code-quality) — fixed:** override keys were decoupled from `worker_runtimes`, so a
  typo silently left a runtime on the default posture and the `--codex` raw path could
  activate an override for an ungated runtime. Now keys MUST name a configured runtime
  (fail-loud at load); docstring corrected to match.
- **Proposed rule (security, not blocking) — tracked:** SECURITY.md should name a
  per-runtime security-posture override as a Tier-0 governed surface (git-visible,
  reviewed as a security change, may only weaken the runtime it names — never the default).
  → tech-debt tracker.

## Outcomes & retrospective
**Delivered (`6e90ffb` + `1b02b35`, both on master).** The `claude` worker runtime now
dispatches classifier-only: `director.worker_runtime_sandbox` maps `claude →
danger-full-access`, the adapter's `resolveSandbox` short-circuits to `{}` (no OS sandbox /
deny rules / egress allowlist), leaving `permissionMode: auto` as the sole boundary. Codex
is provably untouched (still `workspace-write`, verified by the security review through both
drive paths). Mechanism is config-only — the vendored adapter stays in sync with the
producer, and the decision reverses by deleting one config line.

**Reviews:** spec-compliance (codex) SATISFIED; security SATISFIED (0 P1 — scoping + no
collateral weakening confirmed against real code); code-quality (codex) NOT-SATISFIED → 2
P2s fixed → re-verify SATISFIED. The two P2s (raw-TypeError-vs-named-ValueError; decoupled
override keys) were both genuine fail-loud-hygiene gaps; the TypeError one was independently
corroborated by the security reviewer (no confabulation).

**Retrospective.** Behavioral QA: **N/A** — no live `--worker claude` daemon run was made
for this change (it is a config/posture flip on a path already exercised end-to-end by the
prior LIN-27 dogfood; the resolution + wiring is unit-tested, and the adapter short-circuit
was read directly). The next real claude dogfood will observe the no-sandbox posture live.
Key lesson reinforced: a security *decision* that silently fails to take effect (a typo'd
override leaving the runtime sandboxed) is itself a bug — fail-loud beats fail-safe-silent;
coupling the override keys to configured runtimes encodes that.

**Follow-up (tracked):** SECURITY.md should name a per-runtime posture override as a Tier-0
governed surface (review-security proposed rule; behavior already satisfied).
