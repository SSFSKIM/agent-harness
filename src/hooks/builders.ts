import type {
  HooksMap, HookEvent, HookInput, HookCallback,
  PreToolUseHookInput, UserPromptSubmitHookInput, HookDecision,
} from "./types.js";

/** Inject extra context on each user turn. fn returns the text, or null/undefined/"" for "no injection".
 *  Verified path: UserPromptSubmit.additionalContext (recalled by the model). */
export function injectContext(
  fn: (input: UserPromptSubmitHookInput) => string | null | undefined,
): HooksMap {
  const cb: HookCallback = async (input) => {
    const text = fn(input as UserPromptSubmitHookInput);
    if (text == null || text === "") return {};
    return { hookSpecificOutput: { hookEventName: "UserPromptSubmit", additionalContext: text } };
  };
  return { UserPromptSubmit: [{ hooks: [cb] }] };
}

/** Gate a tool by name. `decide` returns a HookDecision; block → PreToolUse deny.
 *  `matcher` is the SDK tool-name matcher (e.g. "Bash", "Write|Edit"). */
export function guardTool(
  matcher: string,
  decide: (input: PreToolUseHookInput) => HookDecision,
): HooksMap {
  const cb: HookCallback = async (input) => {
    const d = decide(input as PreToolUseHookInput);
    if (d && "block" in d && d.block) {
      const reason = d.reason ?? "blocked by hook";
      return {
        decision: "block",
        reason,
        hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: reason },
      };
    }
    return {};
  };
  return { PreToolUse: [{ matcher, hooks: [cb] }] };
}

/** Sugar over guardTool: block when `test` matches. RegExp tests the JSON-serialized tool_input;
 *  a predicate gets the full PreToolUseHookInput. */
export function blockTool(
  matcher: string,
  test: RegExp | ((input: PreToolUseHookInput) => boolean),
  reason = "blocked by hook",
): HooksMap {
  return guardTool(matcher, (input) => {
    const hit = typeof test === "function"
      ? test(input)
      : test.test(JSON.stringify((input as PreToolUseHookInput).tool_input ?? {}));
    return hit ? { block: true, reason } : undefined;
  });
}

/** Fire-and-forget observer for any event. Errors are swallowed (an observer must never break a turn);
 *  always returns {} so it never alters flow. Works for any HookEvent (PostToolUse, Stop, Subagent*, …). */
export function observe(event: HookEvent, fn: (input: HookInput) => void | Promise<void>): HooksMap {
  const cb: HookCallback = async (input) => {
    try { await fn(input); } catch { /* observers must not affect the turn */ }
    return {};
  };
  // Explicit assignment (not a `{ [event]: … }` literal, which widens to a string
  // index signature and won't assign cleanly to HooksMap under tsc).
  const out: HooksMap = {};
  out[event] = [{ hooks: [cb] }];
  return out;
}
