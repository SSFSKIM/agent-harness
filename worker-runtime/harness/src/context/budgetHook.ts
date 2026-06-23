/** The context-budget PUSH hook (Layer 2) — grounds the budget persona (budget.ts, Layer 1) in real
 *  numbers at the right moments. Two triggers, both ADVISORY (injected `additionalContext` the model
 *  reads — never a forced compaction; the model alone calls RequestCompaction):
 *    1. checkpoint: a successful `git commit` (PostToolUse/Bash) arms a flag; the next UserPromptSubmit,
 *       if usage ≥ soft, injects the usage + a "good moment to compact" note.
 *    2. high-water net: usage ≥ net with no checkpoint injects a stronger nudge, once per episode
 *       (re-arms only after usage drops back under net, e.g. a compaction freed space).
 *  Turn-safe: any failure to read usage yields {} so a hook can never break a turn. */
import { summarizeUsage, type QueryHolder } from "./server.js";
import { mergeHooks } from "../hooks/merge.js";
import type { HooksMap, HookCallback, PostToolUseHookInput } from "../hooks/types.js";
import type { ContextBudget } from "./budget.js";

/** "275000" → "275k" for prose. */
const k = (n: number): string => `${Math.round(n / 1000)}k`;

/** Best-effort: did this PostToolUse complete a git commit? Matching the Bash command is enough — a false
 *  positive only injects an advisory note (gated on ≥soft), so we don't parse tool_response for success. */
export function isGitCommit(input: PostToolUseHookInput): boolean {
  if (input.tool_name !== "Bash") return false;
  const cmd = (input.tool_input as { command?: unknown } | null | undefined)?.command;
  if (typeof cmd !== "string" || /--dry-run/.test(cmd)) return false;
  return /\bgit\b[^\n]*\bcommit\b/.test(cmd);
}

function checkpointMsg(tokensUsed: number, percentUsed: number, cfg: ContextBudget): string {
  return `[context] You just hit a checkpoint (git commit). Current usage ~${k(tokensUsed)} tokens ` +
    `(${percentUsed}%), past your ~${k(cfg.target)} target — per your context-budget policy this is a good ` +
    `moment to call RequestCompaction before continuing. Keep working normally if you judge it premature.`;
}
function highWaterMsg(tokensUsed: number, percentUsed: number, cfg: ContextBudget): string {
  return `[context] Heads up: usage is ~${k(tokensUsed)} tokens (${percentUsed}%), past your ~${k(cfg.net)} ` +
    `high-water mark with no recent checkpoint. Finish the current step at the nearest safe point and call ` +
    `RequestCompaction there — do not abandon or rush work, just compact at the next clean boundary.`;
}

/** Build the PostToolUse(commit-flag) + UserPromptSubmit(usage-injector) hook pair, closing over per-session
 *  state. Construct once per session (the Session ctor) so the flag/throttle are scoped to that session. */
export function buildContextBudgetHooks(holder: QueryHolder, cfg: ContextBudget): HooksMap {
  const state = { committed: false, nettedNudged: false };

  const flagCommit: HookCallback = async (input) => {
    if (isGitCommit(input as PostToolUseHookInput)) state.committed = true;
    return {};
  };

  const inject: HookCallback = async () => {
    try {
      const raw = await holder.query?.getContextUsage();
      if (!raw) return {};
      const u = summarizeUsage(raw);
      if (u.tokensUsed < cfg.net) state.nettedNudged = false; // re-arm the net throttle once we drop back down
      if (state.committed) {                                  // (1) checkpoint takes precedence over the net net
        state.committed = false;
        if (u.tokensUsed >= cfg.soft) {
          if (u.tokensUsed >= cfg.net) state.nettedNudged = true; // the checkpoint note already covered high-water
          return { hookSpecificOutput: { hookEventName: "UserPromptSubmit", additionalContext: checkpointMsg(u.tokensUsed, u.percentUsed, cfg) } };
        }
        return {};                                           // committed but too early → consume flag, stay quiet
      }
      if (u.tokensUsed >= cfg.net && !state.nettedNudged) {   // (2) high-water safety net
        state.nettedNudged = true;
        return { hookSpecificOutput: { hookEventName: "UserPromptSubmit", additionalContext: highWaterMsg(u.tokensUsed, u.percentUsed, cfg) } };
      }
      return {};
    } catch { return {}; }                                    // a hook must NEVER break a turn
  };

  return mergeHooks(
    { PostToolUse: [{ matcher: "Bash", hooks: [flagCommit] }] },
    { UserPromptSubmit: [{ hooks: [inject] }] },
  );
}

/** COPY of options with the budget hooks merged into options.hooks (never mutates; mirror withContextTool). */
export function withContextBudgetHooks(options: Record<string, unknown>, holder: QueryHolder, cfg: ContextBudget): Record<string, unknown> {
  const existing = (options.hooks as HooksMap | undefined) ?? {};
  return { ...options, hooks: mergeHooks(existing, buildContextBudgetHooks(holder, cfg)) };
}
