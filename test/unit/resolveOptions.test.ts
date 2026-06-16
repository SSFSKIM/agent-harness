import { describe, it, expect } from "vitest";
import { resolveOptions } from "../../src/config/resolveOptions.js";

describe("resolveOptions", () => {
  it("produces CC-faithful defaults", () => {
    const o: any = resolveOptions({});
    expect(o.settingSources).toEqual(["user", "project", "local"]);
    expect(o.systemPrompt).toEqual({ type: "preset", preset: "claude_code" });
    expect(o.tools).toEqual({ type: "preset", preset: "claude_code" });
    expect(o.enableFileCheckpointing).toBe(true);
    expect(o.agents["Explore"].disallowedTools).toContain("Write");
  });
  it("wires outputStyle into systemPrompt.append", () => {
    const o: any = resolveOptions({ outputStyle: "explanatory" });
    expect(o.systemPrompt.append).toBeTruthy();
  });
  it("threads provider env, sandbox, model, mcp, plugins, cwd, maxTurns", () => {
    const o: any = resolveOptions({
      provider: "bedrock", sandbox: true, model: "claude-opus-4-8",
      mcpServers: { x: { type: "stdio", command: "echo" } }, cwd: "/tmp", maxTurns: 5,
    });
    expect(o.env.CLAUDE_CODE_USE_BEDROCK).toBe("1");
    expect(o.sandbox).toEqual({ enabled: true });
    expect(o.model).toBe("claude-opus-4-8");
    expect(o.mcpServers).toBeTruthy();
    expect(o.cwd).toBe("/tmp");
    expect(o.maxTurns).toBe(5);
  });
  it("disableProjectContext clears sources and excludes dynamic sections", () => {
    const o: any = resolveOptions({ disableProjectContext: true });
    expect(o.settingSources).toEqual([]);
    expect(o.systemPrompt.excludeDynamicSections).toBe(true);
  });
});
