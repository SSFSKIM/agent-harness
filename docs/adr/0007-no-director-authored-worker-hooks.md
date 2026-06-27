---
status: accepted
last_verified: 2026-06-28
owner: harness
type: adr
tags: [worker, codex, security, methodology, hooks]
description: The Director authors no tool-use hooks for either worker runtime; `features.hooks=false` is a settled posture, not a deferral. Closes the deferred "Phase 3 = Codex hooks" of the codex-worker-config lineage — no payload justifies re-opening the clone-hooks RCE that the disable closes.
---
# No Director-authored worker hooks — `features.hooks=false` is settled, not deferred

## Decision

The Director authors **no agent-runtime tool-use hooks** for either worker runtime —
neither for the Codex worker (`.codex/hooks.json`, `~/.codex/hooks.json`, or
`CODEX_HOME/hooks.json`, inline `[hooks]` in `config.toml`) nor for the Claude
adapter. `-c features.hooks=false` (`director/worker/autonomy.py` `DISABLE_HOOKS`,
always-on) is a **permanent** posture, not a temporary disable awaiting a "Phase 3."

This **closes the codex-worker-config lineage's deferred hooks thread**. The lineage
is now complete:

1. [native-translate (Phase 1)](../exec-plans/completed/2026-06-27-codex-worker-config-native-translate.md)
   — skills + agents vendored into the formats/paths the real Codex CLI loads; hooks
   deferred.
2. [Phase 2](../exec-plans/completed/2026-06-28-codex-worker-config-phase2.md) — the
   personas made actually spawnable (hyphen→underscore) and the trust surface closed
   via a Director-managed `CODEX_HOME`; hooks deferred again.
3. **This ADR** — hooks: decided, not building.

**Scope — what this does NOT touch** (all are distinct mechanisms that merely share
the word "hook"):

- The **Director's own self-host plugin hooks** (`plugin/hooks/hooks.json` —
  `Stop`→`tidy_stop.py`, the `SessionStart` feeder) that run on the *human's* Director
  session. Unaffected.
- **Workspace lifecycle hooks** (`director.workspace.hooks`:
  `after_create`/`before_run`/`after_run`/`before_remove`) — host-declared shell run at
  workspace lifecycle points (Symphony §9.4), a Director-side surface governed by T15.
  Unaffected.
- The Claude worker's **in-SDK programmatic hooks** (`options.hooks` inside
  `worker-runtime/harness` — e.g. the [context-budget](../exec-plans/completed/2026-06-24-worker-context-budget.md)
  usage-push). Those are code merged into the SDK options at session open, **not** a
  Director-vendored config file, and are outside this decision.

This ADR governs exactly the third native Codex/Claude config surface — the file-based
*tool-use* event hooks (PreToolUse / PostToolUse / SessionStart / Stop / …). Skills and
agents (surfaces one and two) were delivered by Phases 1–2; hooks are deliberately the
one we do **not** deliver.

## Why

1. **There is no symmetry to restore.** `director/run.py:install_worker_methodology`
   vendors *skills + agents only*. **Neither** worker gets methodology tool-use hooks
   today, so "give the Codex worker the hooks the Claude worker has" describes nothing
   real — the premise that motivated the "Phase 3" label is false.

2. **The candidate payloads do not hold up.** Each plausible reason to author a worker
   hook is already served by another mechanism, or proved weak on its own merits:
   - **Context-budget self-compaction.** The Claude-worker version
     ([worker-context-budget](../exec-plans/completed/2026-06-24-worker-context-budget.md))
     shipped as advisory best-effort; its own retrospective found capable models
     **decline to self-compact** from the standing nudge — model-dependent, low value,
     with the SDK's native auto-compact as the real floor. And it is an *in-SDK* hook
     reading a live `QueryHolder`; a Codex *shell* hook cannot read Codex's live context
     usage, so the concept does not even port.
   - **Deterministic gate enforcement.** The self-host already enforces its gate via the
     repo's **git pre-commit hook**; for a non-agent-harness target repo `check.py` is
     not applicable at all. The methodology gate is delivered by the `execplan` skill
     *procedure*, not a runtime hook.
   - **Observability.** The Director already observes worker turns over the app-server
     protocol (the `thread/tokenUsage/updated` heartbeat); a `Stop`/`PostToolUse` hook
     adds nothing it lacks.
   - **Approval policy.** The Codex worker self-governs via its own reviewer
     (`approvals_reviewer=auto_review`, fail-closed on critical risk —
     `director/worker/autonomy.py`); a `PermissionRequest` hook would duplicate, not
     extend, that.

3. **Real cost against a closure Phases 1–2 deliberately made.** `features.hooks=false`
   is **load-bearing**, not defence-in-depth (SECURITY.md **T16**): because Codex
   *auto-trusts the clone cwd* and there is no disable-auto-trust knob (live-proven,
   codex-cli 0.142), that flag is the *only* thing preventing a hostile clone's
   `.codex/hooks.json` from executing as host RCE at session start. Authoring Director
   hooks means flipping `features.hooks=true`, which **re-exposes that vector** — turning
   a one-line deterministic closure into "re-open, then carefully re-close only the
   clone half" (user-scope `CODEX_HOME` hooks vs. project-scope clone hooks under
   auto-trust, resting on an unverified hash-trust premise). High, ongoing friction in
   exchange for the weak payloads above.

4. **The minimum-code / nothing-speculative belief.** A "Phase N" roadmap entry is a
   *hypothesis* that work is worth doing, not a commitment to do it. With no concrete
   payload and a genuine security cost, the correct, honest deliverable is this
   decision — not machinery built to satisfy a label.

## Consequences

- **`features.hooks=false` stays always-on and is now SETTLED.** Its provisional phrasing
  is reworded from "re-enable selectively *if* the Director ever authors hooks" to "the
  Director authors none; see ADR 0007" in both the code comment
  (`director/worker/autonomy.py` `DISABLE_HOOKS`) and the threat model
  (`docs/SECURITY.md` T16). The security posture is unchanged — only its *status*
  (deferred → decided). No code behavior changes; this is a docs/decision slice.
- **The lineage's hooks thread is closed by reference.** A tech-debt-tracker row records
  the decision and points here, so `nav.py followups` groups it and the doc-gardener does
  not re-surface "hooks deferred" as open work.
- **Reversal trigger (when to revisit).** Reopen this only for a *concrete, named* hook
  payload (an event + an action) whose value (a) **cannot** be delivered by the prompted
  methodology (skills + AGENTS.md), the app-server protocol (observability), Codex's own
  reviewer (approval), or OS isolation (security), **and** (b) justifies re-opening and
  re-closing the clone-hooks surface. The most likely such candidate, if any ever lands,
  is **deterministic methodology gate-enforcement spanning both runtimes** — a larger
  design that would *supersede* this ADR, not a config tweak that slips under it.
- Cross-links [[0005-no-stage-prompt-templates]]: the worker's methodology surface is
  `WORKER_PROTOCOL` + the host's `AGENTS.md` + invocable skills. Hooks are deliberately
  **not** a fourth methodology-delivery layer.
