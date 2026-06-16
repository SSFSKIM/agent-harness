import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { SwarmRuntime } from "../../src/swarm/runtime.js";

const dir = () => mkdtempSync(join(tmpdir(), "swarm-"));
function fakeQuery({ prompt }: any) {
  return (async function* () {
    for await (const turn of prompt) {
      yield { type: "result", subtype: "success", result: "did:" + turn.message.content };
    }
  })();
}
const newRuntime = () => new SwarmRuntime({ query: fakeQuery }, { taskOptions: { dir: dir() } });

describe("SwarmRuntime", () => {
  it("spawns a teammate and a bus message reaches its query → result to the coordinator", async () => {
    const rt = newRuntime();
    const team = rt.createTeam("alpha");
    const s = rt.spawnTeammate({ teamId: team.id, name: "w1", prompt: "seed" });
    await s.settled();
    rt.checkMessages(); // clear seed result/idle
    const next = s.settled();
    rt.sendMessage("w1", "go");
    await next;
    expect(rt.checkMessages().map((m) => m.body)).toContain("did:go");
    await rt.disposeAll();
  });
  it("rejects duplicate teammate names and unknown teams", () => {
    const rt = newRuntime();
    const t = rt.createTeam("a");
    rt.spawnTeammate({ teamId: t.id, name: "w1", prompt: "x" });
    expect(() => rt.spawnTeammate({ teamId: t.id, name: "w1", prompt: "y" })).toThrow(/duplicate/);
    expect(() => rt.spawnTeammate({ teamId: "team-99", name: "w2", prompt: "z" })).toThrow(/unknown team/);
    return rt.disposeAll();
  });
  it("sendMessage to an unknown recipient throws", () => {
    const rt = newRuntime();
    expect(() => rt.sendMessage("ghost", "hi")).toThrow(/unknown recipient/);
  });
  it("deleteTeam disposes members and unregisters them from the bus", async () => {
    const rt = newRuntime();
    const t = rt.createTeam("a");
    rt.spawnTeammate({ teamId: t.id, name: "w1", prompt: "x" });
    rt.deleteTeam(t.id);
    expect(() => rt.sendMessage("w1", "hi")).toThrow(/unknown recipient/);
  });
  it("a TaskStore owner change notifies the coordinator over the bus (closes A1 15.10)", async () => {
    const rt = newRuntime();
    await rt.tasks.create({ subject: "x" });
    await rt.tasks.update(1, { status: "in_progress" }); // claim → owner change
    expect(rt.checkMessages().some((m) => m.kind === "task" && /owner/.test(m.body))).toBe(true);
  });
  it("forwards spec.agent to the teammate query as options.model (30.9)", () => {
    let seen: any;
    const fq = ({ prompt, options }: any) => {
      seen = options;
      return (async function* () { for await (const t of prompt) { void t; yield { type: "result", result: "r" }; } })();
    };
    const rt = new SwarmRuntime({ query: fq }, { taskOptions: { dir: dir() } });
    const t = rt.createTeam("a");
    rt.spawnTeammate({ teamId: t.id, name: "w1", prompt: "x", agent: "claude-haiku-4-5-20251001" });
    expect(seen).toEqual({ model: "claude-haiku-4-5-20251001" });
    return rt.disposeAll();
  });
});
