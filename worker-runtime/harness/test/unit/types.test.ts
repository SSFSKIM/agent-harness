import { describe, it, expect } from "vitest";
import { DEFAULTS } from "../../src/config/types.js";

describe("DEFAULTS", () => {
  it("is CC-faithful: all setting sources, builtin agents, checkpointing on", () => {
    expect(DEFAULTS.settingSources).toEqual(["user", "project", "local"]);
    expect(DEFAULTS.includeBuiltinAgents).toBe(true);
    expect(DEFAULTS.enableFileCheckpointing).toBe(true);
    expect(DEFAULTS.toolPreset).toBe("claude_code");
    expect(DEFAULTS.provider).toBe("anthropic");
  });
});
