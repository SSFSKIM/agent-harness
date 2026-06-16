import { describe, it, expect } from "vitest";
import { DEFAULT_TICK_PROMPT, defaultIdleDetector, AUTONOMOUS_SECTION, applyProactivePersona } from "../../src/proactive/prompts.js";
import { resolveProactiveConfig, proactiveConfig } from "../../src/proactive/types.js";
import { DEFAULT_PROACTIVE_CONFIG } from "../../src/proactive/types.js";

describe("proactive prompts & config", () => {
  it("defaultIdleDetector matches an exact IDLE result, case/space-insensitive; non-string → false", () => {
    expect(defaultIdleDetector("IDLE")).toBe(true);
    expect(defaultIdleDetector("  idle \n")).toBe(true);
    expect(defaultIdleDetector("I did some work")).toBe(false);
    expect(defaultIdleDetector(undefined)).toBe(false);
    expect(defaultIdleDetector(42)).toBe(false);
  });
  it("DEFAULT_TICK_PROMPT instructs the IDLE sentinel", () => {
    expect(DEFAULT_TICK_PROMPT).toMatch(/IDLE/);
  });
  it("applyProactivePersona sets a preset append on bare options", () => {
    const o: Record<string, unknown> = {};
    applyProactivePersona(o);
    expect(o.systemPrompt).toEqual({ type: "preset", preset: "claude_code", append: AUTONOMOUS_SECTION });
  });
  it("applyProactivePersona concatenates onto an existing append", () => {
    const o: Record<string, unknown> = { systemPrompt: { type: "preset", preset: "claude_code", append: "X" } };
    applyProactivePersona(o);
    expect((o.systemPrompt as any).append).toBe("X\n\n" + AUTONOMOUS_SECTION);
  });
  it("resolveProactiveConfig fills defaults and merges a partial nested backoff", () => {
    const c = resolveProactiveConfig({ intervalMs: 5, idleBackoff: { stopAfterIdle: 1 } });
    expect(c.intervalMs).toBe(5);
    expect(c.tickPrompt).toBe(DEFAULT_TICK_PROMPT);
    expect(c.idleBackoff.stopAfterIdle).toBe(1);    // overridden
    expect(c.idleBackoff.factor).toBe(2);           // default preserved
    expect(c.errorBackoff.stopAfterErrors).toBe(5); // untouched default
    expect(c.maxTicks).toBeUndefined();
  });
  it("resolveProactiveConfig() with no input equals the defaults", () => {
    expect(resolveProactiveConfig()).toEqual(DEFAULT_PROACTIVE_CONFIG);
  });
  it("proactiveConfig zod accepts partial/empty configs and rejects a bad field type", () => {
    expect(proactiveConfig.safeParse({ intervalMs: 10 }).success).toBe(true);
    expect(proactiveConfig.safeParse({}).success).toBe(true);
    expect(proactiveConfig.safeParse({ idleBackoff: { stopAfterIdle: 1 } }).success).toBe(true);
    expect(proactiveConfig.safeParse({ intervalMs: "ten" }).success).toBe(false);
  });
});
