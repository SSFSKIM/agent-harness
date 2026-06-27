---
status: completed
last_verified: 2026-06-28
owner: harness
type: exec-plan
description: Phase 2 of the Codex-worker config work — make the vendored review personas ACTUALLY spawnable on the real Codex CLI (sanitize hyphenated agent names), and close the T16 trust surface at its source by loading our agents user-scope via a Director-managed CODEX_HOME instead of trusting the cloned target repo. Plus the four tracked Phase-1 follow-ups (live E2E, garden/scout dispatch, stale-layout sweep, cosmetic).
base_commit: 209964d7334a8ddaf5a0abd2af8743970fb205f9
review_level: full
---
# Codex-worker config — Phase 2 (spawnable personas + trust-surface close)

## Goal
A Codex worker dispatched by the Director can **actually spawn the vendored review/gardener personas by name** at the execplan completion gate, and it does so **without trusting the cloned target repo's project `.codex/` layer** (so a hostile clone's `mcp_servers`/hooks/rules never load, and the Director stops polluting the user's global `~/.codex/config.toml`).

Definition of done (observable):
- A live `codex` session in a vendored workspace spawns a Director-vendored persona **by name** and the child returns its output (the Goal DoD clause Phase 1 left unverified — now the lead acceptance, because the live probe proved it was *broken*).
- Every translated `.codex/agents/*.toml` has a `name` matching `^[a-z0-9_]+$` (Codex's spawn-tool constraint), and the methodology's dispatch instructions name the persona using that exact spawnable name on the Codex side.
- The codex worker launch sets `CODEX_HOME` to a Director-managed dir that carries auth + the vendored personas user-scope; `_with_codex_trust` is gone; the worker run adds **zero** `[projects."…"]` entries to the user's real `~/.codex/config.toml`.
- A reused pre-Phase-1 workspace is swept of inert Director-injected leftovers (`.codex/skills/`, `.codex/agents/*.md`) and the now-stale clone `.codex/agents/*.toml`.
- `garden` + `scout` SKILL.md carry runtime-neutral persona dispatch using the spawnable names.
- `python3 plugin/scripts/check.py` GREEN; full-level completion-gate reviews SATISFIED.

## Context
- **Why this exists** — Phase 1 (`docs/exec-plans/completed/2026-06-27-codex-worker-config-native-translate.md`) vendored review personas to `.codex/agents/*.toml` keeping `name` identical to the source `.md`, and trusted the per-ticket workspace (`-c projects."<ws>".trust_level="trusted"`) so Codex would load that project layer. It explicitly **deferred** the live "does a real Codex worker spawn a vendored persona by name" verification (fix-forward #1). The Phase-2 live probe (this session, codex-cli 0.142.0) ran that verification and found two faults plus confirmed one residual:
  - **F1 (root-cause bug):** Codex's spawn tool rejects an agent whose name contains a hyphen — `error=agent_name must use only lowercase letters, digits, and underscores` (codex_core::tools::router, live). All eight personas are hyphenated (`review-spec-compliance`, `review-code-quality`, `review-arch`, `review-reliability`, `review-security`, `doc-gardener`, `vision-judge`, `workstream-scout`), so today's vendored `.codex/agents/*.toml` are **unspawnable**. The Phase-1 completion claim "personas dispatchable by Codex" was never true at runtime.
  - **F2 (enabler):** A user-scope agent (`~/.codex/agents/<name>.toml`, or `$CODEX_HOME/agents/<name>.toml`) with a valid underscore name passes spawn validation and runs a real child turn — and user/system config loads **regardless of project trust** (developers.openai.com/codex/config-basic: "User and system config still load"). So we do not need to trust the clone to make our personas available.
  - **F3 (side-effect bug):** `-c projects."<path>".trust_level="trusted"` not only works but **auto-persists** the entry into the user's real `~/.codex/config.toml`. The Director's `_with_codex_trust` therefore appends one `[projects."<ws>"]` block per ticket workspace to the user's global config (69 entries observed live, many from prior harness dogfoods — `mt-poc/*`, `lin-livetest-ws`, `secboundary_ws`).
  - **F4 (residual confirmed real):** A trusted clone's project `.codex/config.toml` `mcp_servers.<x>.command` is **executed at session start** (a `/bin/sh -c 'touch MARKER'` mcp entry created the marker, live). The T16 "mcp_servers config-exec" residual is not theoretical.
- **Codex facts (doc-grounded, developers.openai.com; verbatim where load-bearing):**
  - Custom agents: standalone TOML under `~/.codex/agents/` (user) or `.codex/agents/` (project); required keys `name`/`description`/`developer_instructions`; "Codex identifies the custom agent by its `name` field … the `name` field is the source of truth." `features.multi_agent` is stable/on-by-default (no enabling flag needed). Codex only spawns a subagent "when you explicitly ask," so the dispatch instruction must name the persona.
  - `CODEX_HOME`: "Sets the root for Codex state, including config, auth, logs, sessions, skills … If you set it, the directory must already exist." → user-scope agents read from `$CODEX_HOME/agents/` (inference confirmed by F2-style probe), auth from `$CODEX_HOME/auth.json`.
  - Trust: "Codex loads project-scoped config files only when you trust the project … Untrusted projects skip project-scoped `.codex/` layers, including project-local config, hooks, and rules." Project config **cannot** override provider/auth keys (`model_provider`, `model_providers`, `openai_base_url`, … are ignored in a project `.codex/config.toml`), but `mcp_servers` is NOT in that ignore-list → a trusted clone's `mcp_servers` loads (basis of F4).
  - `--ephemeral` breaks subagent spawning (`collab spawn failed: no thread with id`) — a probe-harness caveat, not a worker concern (the worker uses `codex app-server`, non-ephemeral). Recorded so the M5 live test does NOT use `--ephemeral`.
- **Code touched** — `director/run.py` (`_translate_agent_md_to_toml` name sanitize; `_install_agents`/`install_worker_methodology` agent destination → CODEX_HOME; remove `_with_codex_trust`; stale sweep; `_INJECTED_DIRS`/exclude), `director/worker/policy.py` or `director/run.py` (`CODEX_HOME` into the worker env), `director/worker/autonomy.py` (trust-disable comment context; `DISABLE_HOOKS` stays as defence-in-depth), `plugin/skills/{execplan,garden,scout}/SKILL.md` (spawnable codex names), `tests/test_director_run.py`, `docs/SECURITY.md` (T16 rewrite: F3 pollution closed; F4 mcp residual reframed as T11-class; trust removed). Authority: `ARCHITECTURE.md` (Director centralized/non-ported), `docs/SECURITY.md`.

## Approach (self-generated alternatives)
- **Agent names (M1):**
  - **A1 — sanitize at translation (chosen):** the `.codex/agents/*.toml` `name` is `re.sub(r'[^a-z0-9_]', '_', md_name.lower())`; the `.claude/agents/*.md` keep their hyphenated names (Claude is fine with hyphens). The methodology dispatch names the persona per-runtime (Claude: hyphen; Codex: underscore). Tradeoff: two names for one persona — but each is the *native* name on its runtime, and the mapping is a pure deterministic function, so no drift. Minimal blast radius.
  - **A2 — rename the source personas to underscores everywhere:** one name on both runtimes. Rejected: churns plugin agent filenames, `subagent_type:"agent-harness:review-spec-compliance"` call sites across the methodology, every doc reference, and the Director's own agent registry — a huge cross-cutting rename for a cosmetic unification, and Claude's convention is hyphenated. The two-name mapping (A1) is cheaper and keeps each runtime idiomatic.
- **Trust surface (M2):**
  - **B1 — per-Director CODEX_HOME, user-scope agents, no clone trust (chosen):** launch the codex worker with `CODEX_HOME=<director-state>/codex-home` containing `auth.json` (symlink to the real one so token refreshes propagate), a `config.toml` (the user's, copied — so any codex write stays out of `~/.codex`; preserves provider/model), and `agents/<name>.toml` (the vendored personas, underscore-named). Drop `_with_codex_trust` entirely; stop writing `.codex/agents/` into the clone. Closes F4 (clone project layer never trusted → never loaded) AND F3 (no writes to the user's `~/.codex/config.toml`). Tradeoff: a new launch-env knob + first-run CODEX_HOME materialization; the worker no longer sees servers the user added via `codex mcp add` (state-stored, not in config.toml) — acceptable/desirable for a worker (less surface; the methodology needs none of them).
  - **B2 — keep trusting the clone but strip its `.codex/config.toml`:** rejected in Phase 1 already (stripping a clone-tracked file pollutes the worker PR; the overlay+`.git/info/exclude` design exists precisely to never touch the clone's tracked tree).
  - **B3 — keep trust, accept the residual:** the Phase-1 status quo. Rejected: F4 proved the vector real and F3 proved the pollution real; both are cheaply closed by B1.
- **Chosen: A1 + B1** — A1 makes the personas spawnable with the smallest change; B1 closes both the security vector and the config-pollution at the source and folds the stale-`.codex/agents` cleanup into "we no longer write there."

## Assumptions & open questions (self-interrogation)
- Assumption: `$CODEX_HOME/agents/<name>.toml` is the user-scope discovery path when `CODEX_HOME` is set (doc says CODEX_HOME is the state root incl. agents-adjacent state; F2 probe will confirm in M2's PoC). If wrong (agents stay at literal `~/.codex/agents/` regardless of CODEX_HOME), fall back to declaring the agents via a `config.toml` `[agents.<name>]` layer inside CODEX_HOME — caught by M2's PoC before wiring.
- Assumption: `codex app-server` honors `CODEX_HOME` from the process env identically to `codex exec`. The worker is launched as `bash -c "codex app-server …"` with a constructed env; adding `CODEX_HOME` to that env reaches it. PoC in M2.
- Assumption: a **copied** (not symlinked) `config.toml` in CODEX_HOME preserves enough for the worker to reach the model (provider/model/base_url/auth-mode). Auth itself is `auth.json` (symlinked). If the user's config references a relative path or `mcp add`-state server the worker needs, the copy could miss it — but the methodology needs no user MCP, and provider keys are absolute. Verify the PoC worker completes a turn.
- Assumption: the two names per persona (`review-spec-compliance` Claude / `review_spec_compliance` Codex) do not confuse the methodology — the SKILL.md already branches by runtime; M1/M4 just supply the right token per branch.
- Open (Taste — non-blocking, defaulting): CODEX_HOME location — per-Director shared (`.claude/harness/codex-home/`, gitignored) vs per-workspace. Default **per-Director shared**: agents written once, auth symlinked once, trust/session state contained in one Director-owned dir, and it lives OUTSIDE the clone (so no PR-hygiene concern). Concurrent workers sharing one CODEX_HOME is the same as a human running parallel codex sessions (supported).
- Open: keep `DISABLE_HOOKS` (`-c features.hooks=false`)? **Yes** — defence-in-depth. With B1 we never trust the clone so a clone `.codex/hooks.json` can't load anyway, but user-scope hooks in CODEX_HOME could; we author none, and the always-on disable is a cheap belt-and-suspenders. Keep it; update its comment to reflect that trust is gone.

## Milestones
- **M1 — Spawnable agent names (fixes F1).** In `director/run.py` `_translate_agent_md_to_toml`, derive the emitted `name` as a sanitized form of the source name: lowercase, every char outside `[a-z0-9_]` → `_` (so `review-spec-compliance` → `review_spec_compliance`). Add a pure helper `_codex_agent_name(md_name)` reused by the translator AND exported so the dispatch-doc author/tests share one mapping. The `.claude/agents/*.md` are unchanged (hyphens fine on Claude). Update `plugin/skills/execplan/SKILL.md`'s Codex dispatch sentence to name personas by their **sanitized** names (e.g. "ask Codex to spawn `review_spec_compliance`"). Acceptance: a new unit test asserts every translated persona `name` matches `^[a-z0-9_]+$` AND equals `_codex_agent_name(source)`; `tomllib` still parses; `python3 -m unittest discover -s tests -p test_director_run.py` passes; `check.py` GREEN. (Full live spawn is M5.)
- **M2 — Per-Director CODEX_HOME; user-scope agents; remove clone trust (fixes F4 + F3).** PoC FIRST (the unknowns): materialize a CODEX_HOME (auth symlink + config copy + `agents/<underscore>.toml`) and confirm via a live `codex` run (non-ephemeral) that (a) `CODEX_HOME` is honored, (b) the user-scope persona spawns by name, (c) a hostile clone `.codex/config.toml` mcp marker does NOT fire (no trust). Then wire it: a `director/run.py` helper materializes/refreshes the CODEX_HOME (idempotent, symlink-refusing like the other installers), `_install_agents` writes the personas into `$CODEX_HOME/agents/` instead of `<ws>/.codex/agents/`, `CODEX_HOME` is injected into the worker subprocess env (extend `policy._BASE_NAMES` or set it explicitly in the launch-env construction — decide so the deny-by-default boundary still holds), and `_with_codex_trust` + its `_prepare` call site are deleted. `_INJECTED_DIRS`/`_exclude_injected_methodology` drop `.codex/agents/` (no longer in the clone). Acceptance: unit tests — CODEX_HOME materialization (auth symlink present, agents written, idempotent re-run); worker env contains `CODEX_HOME`; `_with_codex_trust` gone (call-site + test removed); the launch command no longer carries a `projects.*.trust_level` override. PoC transcript captured in Surprises. `check.py` GREEN.
- **M3 — Stale-layout sweep (item 4).** Add an idempotent sweep in `install_worker_methodology` that removes Director-injected leftovers from a reused workspace that are no longer written: `<ws>/.codex/skills/`, `<ws>/.codex/agents/*.md`, and (post-M2) `<ws>/.codex/agents/*.toml` — only when they are our injected files (the `.codex/agents/` dir is Director-owned; never touch clone-tracked content elsewhere). Refuse symlinks (same safety contract). Acceptance: a unit test that plants a pre-Phase-1 `.codex/skills/`+`.codex/agents/foo.md` in a workspace, runs install, and asserts they are gone while a clone-tracked sibling file under `.codex/` (e.g. a clone's own `.codex/config.toml`) is untouched. `check.py` GREEN.
- **M4 — Runtime-neutral dispatch for garden + scout (item 2).** Update `plugin/skills/garden/SKILL.md` (doc-gardener) and `plugin/skills/scout/SKILL.md` (workstream-scout, vision-judge) so persona dispatch reads on both runtimes: Claude `subagent_type` (hyphen name) + Codex "spawn the `<underscore_name>` agent" using the M1 sanitized names. Portable layer (lint S7) — host-agnostic. Acceptance: re-read each edited section as each runtime; `check.py` GREEN (doc lints/references).
- **M5 — Live E2E + SECURITY.md + cosmetic + gate (items 1 + 5).** Run the live acceptance: a real `codex` session (non-ephemeral) in a vendored workspace spawns a vendored persona BY its sanitized name and the child returns output — capture the transcript (this is the Goal's lead DoD, the clause Phase 1 left unmet). Rewrite `docs/SECURITY.md` T16 for the **auto-trust reality** the live probe found (codex auto-trusts the worker cwd, so the clone's project `.codex/` loads regardless): **hooks** stay CLOSED via `features.hooks=false` (now load-bearing); the **mcp_servers** exec vector (F4) is NOT in-process closable and is recorded as a T11-class residual retired by OS isolation; the CODEX_HOME closes only the **F3 config-pollution** (auto-trust persistence lands in the Director-managed copy, not the user's real `~/.codex`) and loads personas user-scope (no clone trust). Fix the M5-relevant cosmetic from Phase-1 Feedback #5: `_exclude_injected_methodology` appends a duplicate comment block on a reused ws (make the note write idempotent). Ensure `check.py` GREEN (renumber T-rules if needed — memory merge-numbered-list-collision-renumber), then dispatch the full completion gate (spec-compliance → code-quality, then arch/reliability/security). Acceptance: live transcript captured; all reviews SATISFIED; gate GREEN.

## Progress log
- [x] (2026-06-28) Phase-2 live investigation (the deferred Phase-1 fix-forward #1). Probed codex-cli 0.142.0 with deterministic signals (router error log, mcp marker file, persisted trust entries). Established F1–F4 (see Context). Cleaned up the 2 probe-created trust entries from the user's `~/.codex/config.toml`. ExecPlan created at base_commit 209964d.
- [x] (2026-06-28) M1 — sanitize Codex agent names. Added `_codex_agent_name` (hyphens→underscores, `^[a-z0-9_]+$`); translator emits the sanitized `name` AND filename; execplan SKILL.md Codex dispatch names the underscore form. Tests: charset-invariant guard across all 8 personas + round-trip. `343434d`… → commit `7849fdb`. Gate GREEN.
- [x] (2026-06-28) M2+M3 — per-Director CODEX_HOME + drop clone trust + stale sweep (one commit `3a76375`, since the sweep exists because M2 stops writing `.codex/agents`). Added `_ensure_codex_home` (auth symlink + config COPY + user-scope `agents/`), `_write_codex_agents`, `_install_claude_agents`, `_sweep_stale_codex_layout` (untracked-only). Removed `_with_codex_trust`; wired `CODEX_HOME` into the worker env in `_prepare`; dropped `.codex/agents` from `_INJECTED_DIRS`. Updated autonomy/config/help comments. PoC-verified live first (see Surprises). Gate GREEN.
- [x] (2026-06-28) M4 — runtime-neutral persona dispatch for `garden` + `scout` SKILL.md (Claude `subagent_type`/bare + Codex spawn-by-`underscore_name`). `36606bb`. Gate GREEN.
- [x] (2026-06-28) M5 — live E2E + SECURITY.md + cosmetic. Live E2E through the SHIPPED path: `run._ensure_codex_home()` materialized all 8 personas + symlinked auth, and a real `codex` session under that CODEX_HOME spawned `review_spec_compliance` → child returned `GATE_PERSONA_OK` (the Goal's lead DoD, MET). Rewrote SECURITY.md T16 for the auto-trust reality; fixed the `_exclude_injected_methodology` duplicate-header cosmetic (+ test). `85b2c0b`. Gate GREEN; 47 `test_director_run` tests pass.

## Surprises & discoveries
- (2026-06-28) F1: agent names must be `^[a-z0-9_]+$` — the Phase-1 personas (all hyphenated) are unspawnable; the "tomllib round-trips" Phase-1 acceptance proved well-formedness, not runtime acceptance.
- (2026-06-28) `--ephemeral` breaks subagent spawning (`collab spawn failed: no thread with id`); `-c …trust_level="trusted"` auto-persists to `~/.codex/config.toml`. Both are undocumented; both nearly masked F1.
- (2026-06-28) **The pivotal discovery: Codex AUTO-TRUSTS the directory it operates in** — live-proven on BOTH `codex exec` AND `codex app-server` (the worker runtime). A fresh clone's project `.codex/config.toml` `mcp_servers` command executed at session start with NO trust step, and Codex persisted `trust_level="trusted"`. Consequences that reshaped M2/item-3: (a) Phase-1's explicit `_with_codex_trust` was redundant; (b) the "per-workspace CODEX_HOME closes the mcp residual" premise behind item 3 is FALSE — CODEX_HOME contains the config-pollution (F3) but cannot stop the exec (F4); (c) F4 is not in-process closable (`-c untrusted` overwritten; `-c mcp_servers={}` table-merges; no mcp-disable flag; only trust key is `projects.<path>.trust_level`). Verified the app-server path by driving the Director's own `AppServerClient` (initialize+thread/start, no model turn). Human decision (AskUserQuestion): accept F4 as a T11-class residual retired by OS isolation + ship the CODEX_HOME wins, rather than build a fragile `git update-index --skip-worktree` neutralizer.
- (2026-06-28) PoC (hand-built CODEX_HOME) returned `REVIEW_SECURITY_SPAWNED`; the shipped-path E2E (`_ensure_codex_home()`) returned `GATE_PERSONA_OK` — user-scope personas spawn without trusting the clone, and the real `~/.codex/config.toml` stayed clean (0 new entries) under a custom CODEX_HOME.

## Decision log
- 2026-06-28: Chose **A1** (sanitize codex names, keep Claude hyphen names) over a global rename — each runtime keeps its idiomatic name via a pure deterministic mapping.
- 2026-06-28: Chose **B1** (CODEX_HOME + user-scope agents, drop clone trust) — closes the F4 mcp-exec vector AND the F3 user-config pollution at the source, and folds the stale-`.codex/agents` cleanup into "we no longer write there." B2 (strip clone config) and B3 (accept residual) rejected.
- 2026-06-28: CODEX_HOME is **per-Director shared** (`.claude/harness/codex-home/`, gitignored, outside the clone); auth **symlinked** (token refresh propagates), config **copied** (codex writes stay out of `~/.codex`).
- 2026-06-28: Keep `DISABLE_HOOKS` as defence-in-depth even though dropping clone trust already prevents a clone hooks.json from loading.

## Feedback (from completion gate)
Five full-level reviews (diff range `209964d..HEAD`, clean — only this plan's commits).
Round 1 verdicts: spec-compliance / code-quality / arch / security **SATISFIED**; reliability
**NOT-SATISFIED** (1 P1). All P1 + the convergent P2 bugs fixed inline (`3879a88`); reliability
re-reviewed round 2 → **SATISFIED**. Final: all five SATISFIED.

**P1 fixed inline (reliability, convergent with arch):**
- `_ensure_codex_home` raced under the worker pool — non-atomic check→clear→create on the one
  shared CODEX_HOME (default concurrency 3) → `FileExistsError` / a thread could unlink a live
  worker's auth symlink. Fixed with `_CODEX_HOME_LOCK` (in-process single-flight) + atomic
  temp+`os.replace` writes for the auth symlink, config copy, and agent tomls (cross-process
  safety). Stress-verified: 8 threads × 5 iterations, 0 errors.

**P2 fixed inline (convergent across code-quality / security / reliability):**
- `_refuse_symlink` ran AFTER `.resolve()` (which dereferences the link) → the home-dir symlink
  refusal was a no-op; moved it before `.resolve()`. (+ test)
- `config.toml` symlink-refusal was dead under the common path (a symlink whose target exists
  passed `cfg.exists()`) → could re-open F3; now `if cfg.is_symlink(): cfg.unlink()` runs
  unconditionally before the copy gate. (+ test)
- `_sweep_stale_codex_layout._tracked_under` was fail-OPEN on a non-zero git exit (empty stdout
  → `rmtree`) → data-loss path for a clone shipping its own `.codex/`; now fail-SAFE on non-zero
  returncode + `TimeoutExpired`, and both git probes carry `timeout=30`. (+ mixed-tracked test)
- Spec-compliance: the `_prepare`→worker-env `CODEX_HOME` injection had no unit test (only the
  helper + the direct E2E exercised it); added `test_prepare_injects_codex_home_into_worker_env`
  + the None case.
- Code-quality / arch taste: `_write_codex_agents` now asserts sanitized-name disjointness
  (mirrors `_assert_skill_sources_disjoint`); the execplan dispatch states the hyphen→underscore
  transform as a rule (one example) instead of a 5-way enumeration (map-not-encyclopedia).

**P2 / proposed rules tracked → tech-debt-tracker (not blocking):**
- doc-gardener: 3 grounding-rule proposals carried over from Phase 1 (no hardcoded
  workspace-relative asset path in skill bodies; a vendoring-dest move needs a retired-path
  test/lint; capability/trust override only when its enabling artifact is present) + new
  candidates from this gate (a "symlink-refusing" docstring should have a planted-symlink test;
  a destructive op gated on a subprocess probe must fail-safe on any non-zero/timeout, not only
  on an exception; Director-managed copies of user config need a documented refresh contract).
- `_atomic_write_bytes` can leak a hidden `.<name>.tmp-*` on a mid-write crash (never loaded —
  not codex's `*.toml` glob — and gitignored; cosmetic).
- CODEX_HOME `config.toml` is copy-if-missing (no auto-refresh on a user provider change; delete
  the codex-home to refresh — documented in the helper docstring).

## Outcomes & retrospective
**Shipped (Phase 2).** The Codex worker now ACTUALLY spawns the vendored review/gardener personas
by name — the capability Phase 1 claimed but, the live E2E revealed, never had. Two root faults +
one residual were found and resolved:
- **F1 (root-cause bug):** Codex rejects hyphenated agent names; all 8 personas were unspawnable.
  Fixed by `_codex_agent_name` (hyphen→underscore on both the `name` field and the filename), with
  per-runtime dispatch wording updated in execplan/garden/scout SKILL.md.
- **F3 (config-pollution) + the trust mechanism:** live testing proved Codex **auto-trusts the
  worker cwd** (on `codex exec` AND `codex app-server`), so Phase-1's `_with_codex_trust` was
  redundant and had been persisting `[projects."<ws>"]` entries into the user's real
  `~/.codex/config.toml`. Removed it; the worker now runs under a Director-managed `CODEX_HOME`
  (auth symlinked, config COPIED, personas user-scope) so auto-trust persistence is contained and
  no clone trust is needed. Stale pre-Phase-2 `.codex/{skills,agents}` leftovers are swept
  (untracked-only).
- **F4 (mcp_servers exec):** NOT in-process closable (auto-trust is unkillable; `-c untrusted`
  overwritten, `-c mcp_servers={}` table-merges, no mcp-disable flag) — recorded honestly in
  SECURITY.md T16 as a T11-class residual retired by OS isolation. Hooks stay closed via the
  now-load-bearing `features.hooks=false`.

Commits: `0ce1af0`(plan) `7849fdb`(M1) `3a76375`(M2+M3) `36606bb`(M4) `85b2c0b`+`65939b3`(M5)
`3879a88`(gate P1+P2), base `209964d`.

**Behavioral check (live, codex-cli 0.142).** PROVEN end-to-end through the SHIPPED path: the
investigation matrix (router-error / mcp-marker / persisted-trust signals) on `codex exec` and a
direct `AppServerClient` drive established F1–F4; then `run._ensure_codex_home()` materialized all
8 personas + symlinked auth, and a real `codex` session under that CODEX_HOME spawned
`review_spec_compliance` → child returned `GATE_PERSONA_OK`. Plus 52 `test_director_run` unit tests
and an 8-thread concurrency stress (0 errors). The Goal's lead DoD — a live Codex worker spawning a
vendored persona by name — is MET.

**Review outcome.** 5 personas (full); 1 P1 (reliability concurrency) + convergent P2 bugs, all
fixed inline and re-verified SATISFIED. The reviews materially improved the diff: the P1 race and
the `_tracked_under` fail-open were both real defects a green test suite hadn't caught (the same
class as Phase 1's "tomllib round-trips ≠ runtime accepts").

**Retrospective.** The decisive lesson repeats Phase 1's: **a passing unit suite proves
well-formedness, not runtime acceptance.** Phase 1 shipped a non-functional mechanism because
"tomllib parses the toml" was mistaken for "codex spawns the agent"; the Phase-2 live E2E
(item 1, done FIRST as the user asked) caught it. Carry-forward: for any worker-runtime
integration, the completion gate's behavioral check must drive the REAL runtime (here, a live
`codex` spawn), not just assert artifact shape. The CODEX_HOME redesign also shows the value of
verifying the actual launch path (`codex app-server`, not `codex exec`) — the auto-trust behavior
that reshaped item 3 was only confirmable by driving the worker's real runtime.
