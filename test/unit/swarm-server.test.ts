import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { SwarmRuntime } from "../../src/swarm/runtime.js";
import { buildSwarmTools, createSwarmMcpServer } from "../../src/swarm/server.js";

const dir = () => mkdtempSync(join(tmpdir(), "swarm-"));
function fakeQuery({ prompt }: any) {
  return (async function* () { for await (const t of prompt) yield { type: "result", result: "did:" + t.message.content }; })();
}
const newRuntime = () => new SwarmRuntime({ query: fakeQuery }, { taskOptions: { dir: dir() } });
function toolMap(rt: SwarmRuntime) {
  const map: Record<string, any> = {};
  for (const t of buildSwarmTools(rt)) map[t.name] = t;
  return map;
}
const text = (r: any) => r.content[0].text;

describe("cc-swarm MCP server", () => {
  it("exposes the seven tools", () => {
    expect(Object.keys(toolMap(newRuntime())).sort())
      .toEqual(["CheckMessages", "RespondPermission", "SendMessage", "ShutdownTeammate", "TeamCreate", "TeamDelete", "spawnTeammate"]);
  });
  it("RespondPermission errors on an unknown request id; ShutdownTeammate on an unknown teammate", async () => {
    const t = toolMap(newRuntime());
    const bad = await t.RespondPermission.handler({ requestId: "nope", decision: "allow" }, {});
    expect(bad.isError).toBe(true);
    const badS = await t.ShutdownTeammate.handler({ name: "ghost" }, {});
    expect(badS.isError).toBe(true);
  });
  it("createSwarmMcpServer returns an sdk server named cc-swarm", () => {
    const srv: any = createSwarmMcpServer(newRuntime());
    expect(srv.type).toBe("sdk");
    expect(srv.name).toBe("cc-swarm");
  });
  it("TeamCreate → spawnTeammate → CheckMessages round-trips through the runtime", async () => {
    const rt = newRuntime();
    const t = toolMap(rt);
    const teamId = JSON.parse(text(await t.TeamCreate.handler({ name: "alpha" }, {}))).teamId;
    expect(teamId).toBe("team-1");
    const spawned = await t.spawnTeammate.handler({ teamId, name: "w1", prompt: "seed" }, {});
    expect(JSON.parse(text(spawned)).name).toBe("w1");
    await rt.disposeAll();
  });
  it("domain errors come back as isError results, not throws", async () => {
    const t = toolMap(newRuntime());
    const bad = await t.SendMessage.handler({ to: "ghost", body: "hi" }, {});
    expect(bad.isError).toBe(true);
    expect(text(bad)).toMatch(/unknown recipient/);
    const badSpawn = await t.spawnTeammate.handler({ teamId: "team-99", name: "w1", prompt: "x" }, {});
    expect(badSpawn.isError).toBe(true);
  });
});
