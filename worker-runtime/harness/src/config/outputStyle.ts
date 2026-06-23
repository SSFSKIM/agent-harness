import type { HarnessConfig } from "./types.js";

// Personas appended to the claude_code system prompt to mimic CC output styles.
export const BUILTIN_OUTPUT_STYLES: Record<string, string> = {
  default: "",
  explanatory: "Provide educational insights about the codebase as you work. Explain implementation choices.",
  learning: "Be a collaborative coach: occasionally pause and ask the user to implement small pieces, marked with TODO(human).",
};

export function resolveSystemPrompt(config: HarnessConfig, excludeDynamic = false) {
  const parts: string[] = [];
  if (config.outputStyle && BUILTIN_OUTPUT_STYLES[config.outputStyle]) {
    parts.push(BUILTIN_OUTPUT_STYLES[config.outputStyle]);
  } else if (config.outputStyle) {
    parts.push(config.outputStyle); // treat unknown style string as literal persona
  }
  if (config.appendSystemPrompt) parts.push(config.appendSystemPrompt);
  const append = parts.filter(Boolean).join("\n\n");

  const sp: {
    type: "preset"; preset: "claude_code"; append?: string; excludeDynamicSections?: boolean;
  } = { type: "preset", preset: "claude_code" };
  if (append) sp.append = append;
  if (excludeDynamic) sp.excludeDynamicSections = true;
  return sp;
}
