/** Context-budget policy — the standing system-prompt guidance that tells a worker WHEN to
 *  self-compact, paired with the checkpoint/high-water push hook (budgetHook.ts builds on this).
 *  Compaction itself stays the MODEL's call: this module only shapes its judgment (the persona)
 *  and the push only grounds it (real numbers). Thresholds are ABSOLUTE tokens — the worker runs a
 *  ~1M-context model; the push also carries percentUsed so the signal stays meaningful on any window.
 *  Mirrors proactive/prompts.ts (applyProactivePersona) so personas compose the same way. */

export interface ContextBudget {
  soft: number;   // below this: too early — just keep working
  target: number; // at a checkpoint past this: compact before continuing
  net: number;    // high-water: nudge even WITHOUT a checkpoint
  hard: number;   // the line: compact at the very next checkpoint, no later
}

/** The human-specified band (2026-06-24): compact in 275k–500k at a checkpoint, drift to 600k–650k
 *  mid-task is acceptable. All well below a ~1M window's native auto-compact, so we beat it at a checkpoint. */
export const DEFAULT_CONTEXT_BUDGET: ContextBudget = { soft: 275_000, target: 500_000, net: 600_000, hard: 650_000 };

export type ContextBudgetInput = Partial<ContextBudget> | true | undefined;

/** Fill defaults over a partial input (mirror proactive/resolveProactiveConfig). `true` = all defaults. */
export function resolveContextBudget(input?: ContextBudgetInput): ContextBudget {
  const o = input && input !== true ? input : {};
  return {
    soft: o.soft ?? DEFAULT_CONTEXT_BUDGET.soft,
    target: o.target ?? DEFAULT_CONTEXT_BUDGET.target,
    net: o.net ?? DEFAULT_CONTEXT_BUDGET.net,
    hard: o.hard ?? DEFAULT_CONTEXT_BUDGET.hard,
  };
}

/** Tokens → "275k" for prose. */
const k = (n: number): string => `${Math.round(n / 1000)}k`;

/** The standing policy text, built FROM the thresholds so the numbers in the prose always match config.
 *  Encodes: the band, checkpoint-first, the anti-anxiety architectural fact (compaction runs after the
 *  turn), and the explicit guard against cutting work short to make room. */
export function contextBudgetSection(cfg: ContextBudget): string {
  return [
    "## Managing your own context window",
    "You can read your current usage with the GetContextUsage tool and free space with the RequestCompaction " +
      "tool. RequestCompaction schedules a compaction that runs AFTER you finish the current turn — it never " +
      "cuts your current work short.",
    "Context-budget policy:",
    `- You have a large context window; do not compact reflexively. Below ~${k(cfg.soft)} tokens, just keep working.`,
    `- When you reach a CLEAN CHECKPOINT — a git commit, or a finished sub-task — and your usage is past ` +
      `~${k(cfg.target)} tokens, call RequestCompaction before continuing.`,
    `- If a long stretch pushes you past ~${k(cfg.net)} tokens without a checkpoint, stop at the nearest safe ` +
      `point soon and compact there; treat ~${k(cfg.hard)} tokens as the line where you compact at the very ` +
      `next checkpoint, no later.`,
    "- NEVER end, shorten, or rush your actual work to make room. Compaction preserves your task state and is " +
      "cheap; the only thing to avoid is running low, and you avoid it by compacting at checkpoints — not by " +
      "doing less work.",
    "The harness will remind you of your current usage at checkpoints; combine that signal with this policy to decide.",
  ].join("\n");
}

/** Append the budget section to resolved SDK options' systemPrompt (mirror applyProactivePersona):
 *  preserve an existing append; synthesize a claude_code preset when systemPrompt is absent. */
export function applyContextBudgetPersona(options: Record<string, unknown>, cfg: ContextBudget): void {
  const section = contextBudgetSection(cfg);
  const sp = options.systemPrompt as { type?: string; preset?: string; append?: string } | string | undefined;
  if (sp && typeof sp === "object") {
    options.systemPrompt = { ...sp, append: (sp.append ? sp.append + "\n\n" : "") + section };
  } else {
    options.systemPrompt = { type: "preset", preset: "claude_code", append: section };
  }
}
