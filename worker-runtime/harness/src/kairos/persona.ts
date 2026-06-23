/** Assistant-mode standing instructions (parity 32.1/32.3). Applied as a systemPrompt append at spawn,
 *  alongside applyProactivePersona (which carries the heartbeat/IDLE contract). */
export const ASSISTANT_SECTION = [
  "You are running as an autonomous scheduled assistant (Kairos mode); no human is watching in real time.",
  "Report progress, results, and anything the user should see by calling the SendUserMessage tool (the Brief channel) — plain assistant text is NOT surfaced to the user in this mode.",
  "Use status \"proactive\" for messages worth a push notification; status \"normal\" otherwise.",
  "On a heartbeat tick with nothing useful to do, reply with exactly IDLE so the loop backs off; never ask the human questions on a tick.",
].join(" ");

/** Mutate resolved SDK options to append the assistant section (mirrors applyProactivePersona). */
export function applyAssistantPersona(options: Record<string, unknown>): void {
  const sp = options.systemPrompt as { type?: string; preset?: string; append?: string } | string | undefined;
  if (sp && typeof sp === "object") {
    options.systemPrompt = { ...sp, append: (sp.append ? sp.append + "\n\n" : "") + ASSISTANT_SECTION };
  } else if (typeof sp === "string") {
    options.systemPrompt = sp + "\n\n" + ASSISTANT_SECTION;
  } else {
    options.systemPrompt = { type: "preset", preset: "claude_code", append: ASSISTANT_SECTION };
  }
}
