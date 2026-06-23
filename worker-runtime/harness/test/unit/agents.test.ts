import { describe, it, expect } from "vitest";
import { resolveAgents, BUILTIN_AGENTS } from "../../src/config/agents.js";

describe("resolveAgents", () => {
  it("includes CC built-ins by default", () => {
    const out = resolveAgents({});
    expect(Object.keys(out)).toEqual(expect.arrayContaining(["general-purpose", "Explore", "Plan"]));
  });
  it("Explore and Plan are read-only (disallow mutation tools)", () => {
    for (const k of ["Explore", "Plan"]) {
      expect(BUILTIN_AGENTS[k].disallowedTools).toEqual(
        expect.arrayContaining(["Edit", "Write", "NotebookEdit"]));
    }
  });
  it("omits built-ins when includeBuiltinAgents is false", () => {
    expect(resolveAgents({ includeBuiltinAgents: false })).toEqual({});
  });
  it("user agents override built-ins by key", () => {
    const out = resolveAgents({ agents: { Explore: { description: "x", prompt: "y" } } });
    expect(out.Explore.description).toBe("x");
  });
});
