/** The synthetic message injected on each heartbeat tick (config-overridable). */
export const DEFAULT_TICK_PROMPT =
  "<heartbeat> Autonomous tick — no human is waiting. If there's a concrete next step toward the current " +
  "goal, take it now. If there's nothing useful to do, reply with exactly IDLE and nothing else.";

/** True when a tick produced no work — the model replied with the bare IDLE sentinel. */
export function defaultIdleDetector(result: unknown): boolean {
  return typeof result === "string" && result.trim().toUpperCase() === "IDLE";
}

/** Standing autonomous-work instructions (parity 31.4). Applied as an opt-in systemPrompt append at spawn. */
export const AUTONOMOUS_SECTION = [
  "You may be driven by an autonomous heartbeat that wakes you between human turns.",
  "On a heartbeat tick, advance the current goal with the next concrete step if there is one.",
  "If there is genuinely nothing useful to do, reply with exactly IDLE so the heartbeat can back off.",
  "Do not ask the human questions on a tick; either act or report IDLE.",
].join(" ");

/** Mutate resolved SDK options to append the autonomous section (mirrors applyCoordinatorPersona). */
export function applyProactivePersona(options: Record<string, unknown>): void {
  const sp = options.systemPrompt as { type?: string; preset?: string; append?: string } | string | undefined;
  if (sp && typeof sp === "object") {
    options.systemPrompt = { ...sp, append: (sp.append ? sp.append + "\n\n" : "") + AUTONOMOUS_SECTION };
  } else {
    options.systemPrompt = { type: "preset", preset: "claude_code", append: AUTONOMOUS_SECTION };
  }
}
