import { describe, it, expect } from "vitest";
import { resolveSystemPrompt, BUILTIN_OUTPUT_STYLES, FORK_SUBAGENT_NOTE } from "../../src/config/outputStyle.js";

describe("resolveSystemPrompt", () => {
  it("uses claude_code preset with no append when fork-subagent is off", () => {
    const sp = resolveSystemPrompt({ forkSubagent: false });
    expect(sp).toEqual({ type: "preset", preset: "claude_code" });
  });
  it("advertises the fork subagent type by default (env var alone is inert — 33d)", () => {
    const sp: any = resolveSystemPrompt({});
    expect(sp.append).toContain(FORK_SUBAGENT_NOTE);
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
