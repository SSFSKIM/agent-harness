import { describe, it, expect } from "vitest";
import { applyProactivePersona } from "../../src/proactive/prompts.js";
import { applyAssistantPersona, ASSISTANT_SECTION } from "../../src/kairos/persona.js";

describe("assistant persona", () => {
  it("creates a claude_code preset append when systemPrompt is unset", () => {
    const o: Record<string, unknown> = {};
    applyAssistantPersona(o);
    expect(o.systemPrompt).toEqual({ type: "preset", preset: "claude_code", append: ASSISTANT_SECTION });
  });
  it("composes after the proactive persona (both sections present, proactive first)", () => {
    const o: Record<string, unknown> = {};
    applyProactivePersona(o);
    applyAssistantPersona(o);
    const append = (o.systemPrompt as any).append as string;
    expect(append).toContain("autonomous heartbeat");   // proactive section
    expect(append).toContain("SendUserMessage");          // assistant section
    expect(append.indexOf("autonomous heartbeat")).toBeLessThan(append.indexOf("SendUserMessage"));
  });
  it("appends to an existing string systemPrompt", () => {
    const o: Record<string, unknown> = { systemPrompt: "BASE" };
    applyAssistantPersona(o);
    expect(o.systemPrompt).toBe("BASE\n\n" + ASSISTANT_SECTION);
  });
});
