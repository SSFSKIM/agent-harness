import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHarness } from "../../src/harness.js";

const dir = () => mkdtempSync(join(tmpdir(), "swarm-int-"));
function fakeQuery() { return (async function* () { yield { type: "result", subtype: "success", result: "ok" }; })(); }

describe("swarm harness wiring", () => {
  it("merges cc-swarm and exposes harness.swarm", () => {
    const h = createHarness({ swarm: true, cwd: dir() }, { query: fakeQuery as any });
    expect((h.options as any).mcpServers["cc-swarm"].name).toBe("cc-swarm");
    expect(h.swarm).toBeTruthy();
  });
  it("disables native per-session Task tools so cc-tasks is authoritative (split-brain fix)", () => {
    const h = createHarness({ swarm: true, cwd: dir() }, { query: fakeQuery as any });
    expect((h.options as any).disallowedTools).toEqual(expect.arrayContaining(["TaskCreate", "TaskUpdate", "TodoWrite"]));
  });
  it("coexists with taskTools (both servers present, shared store)", () => {
    const h = createHarness({ swarm: true, taskTools: true, cwd: dir() }, { query: fakeQuery as any });
    const servers = (h.options as any).mcpServers;
    expect(servers["cc-swarm"]).toBeTruthy();
    expect(servers["cc-tasks"]).toBeTruthy();
    expect(h.tasks).toBe(h.swarm!.tasks); // the cc-tasks server shares the runtime's store
  });
  it("applies the coordinator persona + whitelist when requested", () => {
    const h = createHarness({ swarm: { coordinatorPersona: true }, cwd: dir() }, { query: fakeQuery as any });
    expect((h.options as any).systemPrompt.append).toContain("COORDINATOR");
    expect((h.options as any).allowedTools).toContain("mcp__cc-swarm__spawnTeammate");
  });
  it("passes permissions config into the runtime broker", async () => {
    let cut: any;
    const fq = ({ prompt, options }: any) => {
      if (options?.canUseTool) cut = options.canUseTool;
      return (async function* () { for await (const t of prompt) { void t; yield { type: "result", result: "ok" }; } })();
    };
    // custom allowlist proves the config flowed through to the runtime broker (Bash allowed, Read not).
    const h = createHarness({ swarm: { permissions: { allow: ["Bash"] } }, cwd: dir() }, { query: fq as any });
    const team = h.swarm!.createTeam("a");
    h.swarm!.spawnTeammate({ teamId: team.id, name: "w1", prompt: "x" });
    expect(typeof cut).toBe("function");
    expect((await cut("Bash", {})).behavior).toBe("allow");
    expect((await cut("Read", {})).behavior).toBe("deny");
    await h.swarm!.disposeAll();
  });
});
