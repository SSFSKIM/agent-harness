---
status: active
last_verified: 2026-06-24
owner: harness
type: exec-plan
description: Give the Claude worker a context-budget policy (systemPrompt persona) plus a checkpoint-aligned usage push (hooks) so it proactively self-compacts via cc-compact at safe checkpoints instead of running blind.
base_commit: 0c36fe348c0ada3e1c663dfd807d18ce0d6b141a
review_level: targeted
---
# Worker context-budget — proactive self-compaction guidance

## Goal
A Claude worker session (opened by the in-repo app-server, `worker-runtime/app-server`)
**proactively schedules its own context compaction at safe checkpoints** instead of
running until the SDK's native auto-compact fires mid-thought. Definition of done,
observable: (1) every app-server worker session is opened with a **context-budget
persona** appended to its system prompt (the policy: thresholds, checkpoint-first,
anxiety-guard) AND a **budget hook** that, on a clean checkpoint (a `git commit`) or a
high-water crossing, injects the worker's current `{tokensUsed, percentUsed}` plus a
nudge; (2) the `RequestCompaction` decision stays 100% with the model — no code path
calls compaction automatically; (3) a gated live test shows a session opened with the
budget enabled, fed real coding work, injects the usage signal and the model calls
`mcp__cc-compact__RequestCompaction` from the *standing policy* (without the turn prompt
naming the tool); (4) `npm run typecheck` + keyless `npm run test:unit` are green in both
`worker-runtime/harness` and `worker-runtime/app-server`, and `python3
plugin/scripts/check.py` is GREEN.

## Context
Settled in conversation (2026-06-24) — no separate product-spec; the *what* is clear and
single-subsystem, so this ExecPlan carries the design inline (PLANS.md entry decision).

Background a novice needs:
- **The two existing tools (component A, already shipped).** `worker-runtime/harness/src/context/server.ts`
  exposes `mcp__cc-context__GetContextUsage` (a PULL tool returning `summarizeUsage()` =
  `{percentUsed, tokensUsed, maxTokens, tokensRemaining, status}`).
  `worker-runtime/harness/src/compaction/server.ts` exposes `mcp__cc-compact__RequestCompaction`
  (PULL tool; `Session.requestCompaction()` sets a flag consumed at the next turn boundary
  in `session.ts` `readLoop` → runs `/compact` AFTER the turn, never mid-turn). The
  app-server already enables both per session (`worker-runtime/README.md`, `handlers.threadStart`
  sets `contextTool`/`compactTool`). They appear on the worker's ToolSearch surface.
- **The gap.** No standing system-prompt guidance tells the worker *when* to check usage
  or compact, and nothing pushes its current usage to it — so the model rarely self-compacts
  at a good moment. (`worker-runtime/harness/test/live/proactive-compaction.test.ts` already
  proves the model WILL self-compact from a *soft* instruction and discover cc-compact via
  ToolSearch — so an explicit standing policy is the right lever.)
- **Requirements (from the human).**
  - **Context-anxiety aversion is a hard constraint**: the worker must NOT cut work short or
    wrap up prematurely because it feels it should compact. (Rare since Opus 4.6, still guard it.)
  - **Recommended compaction band 275k–500k tokens**, but if work is mid-flight, drift to
    **600k–650k is acceptable**. Compacting at a *definite checkpoint* matters more than the
    raw fill level — never disrupt long work to compact.
  - The key engineering question is *how to tell the worker its current window state*; the
    decision (chosen below) is a **checkpoint(commit)-aligned push + a high-water safety net**,
    delivered as `additionalContext` (advisory text the model reads), never a forced compaction.
- **Seam facts (verified in source).** `Session` ctor (`worker-runtime/harness/src/session/session.ts:31-44`)
  late-binds `ctxHolder.query = this.q` after `deps.query()`, so a hook can reach
  `getContextUsage()` through that same `QueryHolder`. Personas append via
  `opts.systemPrompt.append` (pattern: `worker-runtime/harness/src/proactive/prompts.ts`
  `applyProactivePersona`). Hooks flow through `options.hooks`
  (`worker-runtime/harness/src/config/resolveOptions.ts:63`). Hook builders +
  `mergeHooks` live in `worker-runtime/harness/src/hooks/` (`observe`, `injectContext`).
  `UserPromptSubmit` and `PostToolUse` both fire (note in `config/types.ts`: SessionStart/SessionEnd do not).
- **Why model-only compaction is correct.** `additionalContext` is read text, not a command —
  the hook structurally cannot force compaction, only inform; whether the current moment is a
  safe boundary is judgment only the model has; and the SDK's **native auto-compact**
  (`isAutoCompactEnabled`/`autoCompactThreshold`, surfaced in `summarizeUsage`) already exists
  as the involuntary floor near the window limit, so no redundant deterministic compactor is needed.

## Approach (self-generated alternatives)
- **A — Two layers: standing persona (policy) + checkpoint/high-water push (hook).** A
  `context/budget.ts` module adds (1) a systemPrompt append encoding the band/checkpoint/anxiety
  policy and (2) a hook pair: `PostToolUse(Bash)` flags a successful `git commit`; the next
  `UserPromptSubmit` reads `getContextUsage()` and injects usage + a nudge when (commit &&
  ≥soft) or (≥net high-water, throttled). Wired in the `Session` ctor next to `withContextTool`
  (where the late-bound holder lives); the app-server flips it on per session. Tradeoff: a new
  stateful hook (per-session closure) + a config object — but each piece is small, pure, and
  DI-testable, and it mirrors existing patterns (`applyProactivePersona`, `withContextTool`).
- **B — Persona only (no push).** Just append the policy text; rely on the model calling
  `GetContextUsage` itself at checkpoints. Tradeoff: simplest, but the model is blind between
  explicit checks and the policy's absolute-token thresholds become guesswork — weak grounding,
  and the high-water safety net disappears.
- **C — Deterministic auto-compact in the hook.** Have the hook call `requestCompaction()` when
  usage crosses a threshold. Tradeoff: removes the anxiety problem by removing model agency, but
  compacts at non-checkpoints (mid-thought), violates the human's "checkpoint > fill" priority,
  and duplicates the SDK's native floor. Rejected.
- **Chosen: A.** It satisfies the checkpoint-first + anxiety-aversion constraints exactly, keeps
  the model as the sole compaction actor (B's grounding gap fixed, C's overreach avoided), and
  reuses established harness seams. (Mirrored in Decision log.)

## Assumptions & open questions (self-interrogation)
- Assumption: the claude worker runs on a **~1M-token context** model, so absolute-token
  thresholds {soft 275k, target 500k, net 600k, hard 650k} are meaningful (≈28%/50%/60%/65%).
  What breaks if wrong: on a 200k-window model the thresholds exceed the window and never fire.
  Mitigation: the injected message also carries `percentUsed` (always meaningful), and
  `resolveContextBudget` accepts overrides; v1 ships the absolute defaults the human specified.
  Recorded as a known limitation, not a blocker.
- Assumption: a worker turn maps to one `UserPromptSubmit`; commits made within a long single
  turn are caught at that turn's end (the persona ALSO drives in-turn checks at commit points,
  so the hook is the cross-turn grounding + safety net, not the only signal). What breaks if
  wrong: a very long no-commit turn gets no mid-turn push — covered by the persona's in-turn
  guidance + the native auto-compact floor.
- Assumption: detecting `git commit` via the `PostToolUse(Bash)` command string is good enough.
  Best-effort: match the command on `git ... commit`; if a `tool_response` error signal is
  available, a failed commit does not set the checkpoint flag. What breaks if wrong: a false
  positive injects an early "good time to compact" note — harmless (advisory, gated on ≥soft).
- Open: enable budget **always** for the app-server worker vs. config-gated? → resolved
  autonomously: **always on** for the app-server session with built-in defaults (matches the
  human's "always on for the claude worker"); plumbing host-tunable thresholds through Director
  `.harness.json` is deferred to tech-debt (not needed for v1 since defaults == the spec).
- Open: security review needed? → resolved: **no** — these are in-worker SDK programmatic hooks
  (no Director exec surface, no credential handling, worker already sandboxed). `review_level:
  targeted` → reliability (turn-safety) + arch (seam) personas; spec-compliance + code-quality
  are always-on.

## Milestones

- **M1 — Context-budget config + persona text (pure, no wiring).** New module
  `worker-runtime/harness/src/context/budget.ts` exporting: `ContextBudget`
  (`{soft,target,net,hard}` absolute tokens); `resolveContextBudget(input?: Partial<ContextBudget> | true): ContextBudget`
  filling defaults `{275_000, 500_000, 600_000, 650_000}` (mirror `resolveProactiveConfig`);
  `contextBudgetSection(cfg): string` building the policy prose FROM the thresholds (so the
  numbers in the text always match config); `applyContextBudgetPersona(options, cfg)` appending
  that section to `options.systemPrompt.append` (mirror `applyProactivePersona`, handling the
  object / preset / missing cases). The prose MUST state: the band + checkpoint-first rule; that
  `RequestCompaction` runs *after* the current turn and never cuts work short; and the explicit
  anxiety-guard ("never end, shorten, or rush your work to make room"). At the end this module
  exists with no callers yet. Run `cd worker-runtime/harness && npm run typecheck && npx vitest
  run test/unit/context-budget.test.ts`; expect green, with assertions that the section text
  contains "650", "after you finish", and an anxiety-guard phrase, and that the persona append
  composes onto a `{type:preset}` systemPrompt and onto an absent one.

- **M2 — The 2-trigger budget hook (pure, DI-tested).** Extend `budget.ts` with
  `buildContextBudgetHooks(holder: QueryHolder, cfg: ContextBudget): HooksMap` =
  `mergeHooks(observe("PostToolUse", flagGitCommit), { UserPromptSubmit: [{ hooks: [injector] }] })`,
  plus `withContextBudgetHooks(options, holder, cfg)` that non-mutatingly merges those into
  `options.hooks` (mirror `withContextTool`). `flagGitCommit` sets a per-session closure flag
  when a `Bash` `git commit` succeeds. `injector` awaits `holder.query?.getContextUsage()` →
  `summarizeUsage()` → decides: (a) committed-since-last-turn && `tokensUsed ≥ soft` → checkpoint
  message naming tokens+percent, reset flag; (b) else `tokensUsed ≥ net` && band not already
  nudged → high-water message, mark throttle; (c) else `{}` (no injection). On any throw from
  `getContextUsage()` the injector returns `{}` (a hook must never break a turn). At the end the
  hook builder exists, still unwired. Run `npx vitest run test/unit/context-budget-hook.test.ts`
  with a fake holder returning scripted usages; expect green proving: below-soft+commit → no
  injection; target+commit → checkpoint injection mentions the token count; net+no-commit →
  high-water injection; second net call same band → throttled `{}`; holder throws → `{}`.

- **M3 — Session wiring + public surface.** `worker-runtime/harness/src/session/session.ts`: add
  `SessionOpts.contextBudget?: Partial<ContextBudget> | true`; in the ctor, when set, ensure a
  `ctxHolder` exists (call `withContextTool` if `contextTool` was not separately requested — the
  hook needs `getContextUsage`), resolve the budget, `applyContextBudgetPersona(opts, bcfg)`, and
  `opts = withContextBudgetHooks(opts, ctxHolder, bcfg)` — all before `deps.query(opts)` so the
  late-bind at line 41 still wires `ctxHolder.query`. `worker-runtime/harness/src/session/index.ts`:
  add `contextBudget?` to `OpenSessionConfig` and pass it into `new Session(...)`. Export the new
  public symbols from `worker-runtime/harness/src/index.ts` and update the surface pin
  (`test/unit/index.test.ts`). At the end, `openSession({ contextBudget: true, ... })` yields a
  session whose resolved options carry the systemPrompt append + a `UserPromptSubmit` hook + the
  `GetContextUsage` tool allowlisted even if `contextTool` was not passed. Run `npm run typecheck
  && npm run test:unit && npm run build`; expect green (build proves the public `.d.ts` resolve).

- **M4 — App-server enablement + live proof.** `worker-runtime/app-server/src/handlers.ts`
  `threadStart`: set `cfg.contextBudget = true` alongside the existing `contextTool`/`compactTool`
  so every worker session gets the persona + hooks. Keyless unit coverage: a handlers test asserts
  the `cfg` passed to the session opener has `contextBudget` set (mirror the existing
  context/compact assertions). Live proof (gated on `ANTHROPIC_API_KEY`/`CLAUDE_CODE_OAUTH_TOKEN`,
  skips clean without): a new `worker-runtime/harness/test/live/context-budget.test.ts` opens a
  session with `contextBudget` set to a *tiny* `soft`/`net` (so a couple of real tool turns cross
  it), does real coding work + a `git commit` in a throwaway repo, and asserts the injected
  `additionalContext` carrying usage appears AND the model calls `RequestCompaction` without the
  turn prompt naming the tool. Run `cd worker-runtime/app-server && npm run typecheck && npm run
  test:unit` (keyless) and, when keyed, `cd worker-runtime/harness && set -a; . ../.env; set +a;
  npx vitest run test/live/context-budget.test.ts`. Expect: keyless green; keyed live shows the
  injection + a `RequestCompaction` call (capture the `[budget]` log line as proof).

- **M5 — Docs + gate.** Update `worker-runtime/README.md` (the two tools now carry a budget
  persona + checkpoint push; compaction stays model-driven). Add a `docs/RELIABILITY.md` rule:
  a worker-runtime hook MUST return `{}` rather than throw — the budget injector swallows a
  `getContextUsage` failure (cite the M2 safety test). At the end the docs reflect the behavior.
  Run `python3 plugin/scripts/check.py`; expect GREEN. (Completion gate — reviews — runs after M5
  per the execplan procedure.)

## Progress log
- [ ] (2026-06-24) Plan created; base_commit 0c36fe3; review_level targeted. Next: M1.

## Surprises & discoveries

## Decision log
- 2026-06-24: Chose Approach A (persona policy + checkpoint/high-water push) over persona-only
  (B, no grounding/safety-net) and deterministic auto-compact (C, violates checkpoint-first +
  removes model agency). The SDK's native auto-compact is the involuntary floor, so our layer is
  entirely advisory and model-driven.
- 2026-06-24: Budget enabled **always** for the app-server worker with the human's absolute-token
  defaults; host-tunable thresholds via Director config deferred to tech-debt.
- 2026-06-24: `review_level: targeted` (reliability + arch); security persona not applicable —
  in-worker SDK hooks, no Director exec surface or credential handling.

## Feedback (from completion gate)

## Outcomes & retrospective
