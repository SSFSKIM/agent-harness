import type {
  HookEvent, HookInput, HookCallback, HookJSONOutput, HookCallbackMatcher,
  PreToolUseHookInput, PostToolUseHookInput, UserPromptSubmitHookInput,
  StopHookInput, SubagentStopHookInput,
} from "@anthropic-ai/claude-agent-sdk";

export type {
  HookEvent, HookInput, HookCallback, HookJSONOutput, HookCallbackMatcher,
  PreToolUseHookInput, PostToolUseHookInput, UserPromptSubmitHookInput,
  StopHookInput, SubagentStopHookInput,
};

/** The exact SDK `options.hooks` shape — what builders produce and `config.hooks` accepts. */
export type HooksMap = Partial<Record<HookEvent, HookCallbackMatcher[]>>;

/** Return value of a `guardTool` decision function. `void` = no opinion (allow). */
export type HookDecision = { allow: true } | { block: true; reason?: string } | void;
