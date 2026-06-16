import { describe, it, expect } from "vitest";
import { applyCoordinatorPersona, coordinatorTools, COORDINATOR_PROMPT } from "../../src/swarm/coordinator.js";

describe("coordinator persona", () => {
  it("appends the persona to an existing preset systemPrompt and sets the default whitelist", () => {
    const options: any = { systemPrompt: { type: "preset", preset: "claude_code", append: "BASE" } };
    applyCoordinatorPersona(options);
    expect(options.systemPrompt.type).toBe("preset");
    expect(options.systemPrompt.append).toContain("BASE");
    expect(options.systemPrompt.append).toContain(COORDINATOR_PROMPT);
    expect(options.allowedTools).toEqual(coordinatorTools());
    expect(options.allowedTools).toContain("mcp__cc-swarm__spawnTeammate");
    expect(options.allowedTools).toContain("mcp__cc-tasks__TaskCreate");
  });
  it("creates a preset systemPrompt when none exists and honors a tools override", () => {
    const options: any = {};
    applyCoordinatorPersona(options, ["Read"]);
    expect(options.systemPrompt).toEqual({ type: "preset", preset: "claude_code", append: COORDINATOR_PROMPT });
    expect(options.allowedTools).toEqual(["Read"]);
  });
});
