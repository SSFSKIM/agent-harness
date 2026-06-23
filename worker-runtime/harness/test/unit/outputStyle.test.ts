import { describe, it, expect } from "vitest";
import { resolveSystemPrompt, BUILTIN_OUTPUT_STYLES } from "../../src/config/outputStyle.js";

describe("resolveSystemPrompt", () => {
  it("uses claude_code preset with no append by default", () => {
    const sp = resolveSystemPrompt({});
    expect(sp).toEqual({ type: "preset", preset: "claude_code" });
  });
  it("appends a known output-style persona", () => {
    const sp: any = resolveSystemPrompt({ outputStyle: "explanatory" });
    expect(sp.type).toBe("preset");
    expect(sp.append).toContain(BUILTIN_OUTPUT_STYLES.explanatory);
  });
  it("merges custom appendSystemPrompt and excludeDynamic flag", () => {
    const sp: any = resolveSystemPrompt({ appendSystemPrompt: "EXTRA" }, true);
    expect(sp.append).toContain("EXTRA");
    expect(sp.excludeDynamicSections).toBe(true);
  });
});
