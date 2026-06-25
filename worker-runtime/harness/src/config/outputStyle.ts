import { DEFAULTS, type HarnessConfig } from "./types.js";

// Personas appended to the claude_code system prompt to mimic CC output styles.
export const BUILTIN_OUTPUT_STYLES: Record<string, string> = {
  default: "",
  explanatory: "Provide educational insights about the codebase as you work. Explain implementation choices.",
  learning: "Be a collaborative coach: occasionally pause and ask the user to implement small pieces, marked with TODO(human).",
};

// Advertises the native fork subagent so the model will CHOOSE it on its own. Probe 33d: with the env var
// set but this note absent, the model never picks subagent_type:"fork" (it treats "subagent" as blank-slate);
// once advertised, it forks when the sub-task depends on prior context. Paired with CLAUDE_CODE_FORK_SUBAGENT=1.
export const FORK_SUBAGENT_NOTE =
  'A subagent_type "fork" is available when you spawn a subagent (Agent/Task tool). A "fork" subagent ' +
  "INHERITS this conversation's full context — everything discussed so far — whereas a normal subagent " +
  'starts blank. Prefer subagent_type:"fork" whenever the delegated sub-task depends on what has already ' +
  "been discussed in this session.";

export function resolveSystemPrompt(config: HarnessConfig, excludeDynamic = false) {
  const parts: string[] = [];
  if (config.outputStyle && BUILTIN_OUTPUT_STYLES[config.outputStyle]) {
    parts.push(BUILTIN_OUTPUT_STYLES[config.outputStyle]);
  } else if (config.outputStyle) {
    parts.push(config.outputStyle); // treat unknown style string as literal persona
  }
  if (config.appendSystemPrompt) parts.push(config.appendSystemPrompt);
  if (config.forkSubagent ?? DEFAULTS.forkSubagent) parts.push(FORK_SUBAGENT_NOTE);
  const append = parts.filter(Boolean).join("\n\n");

  const sp: {
    type: "preset"; preset: "claude_code"; append?: string; excludeDynamicSections?: boolean;
  } = { type: "preset", preset: "claude_code" };
  if (append) sp.append = append;
  if (excludeDynamic) sp.excludeDynamicSections = true;
  return sp;
}
