import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { SwarmRuntime } from "../../src/swarm/runtime.js";
import { TaskStore } from "../../src/tasks/store.js";

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
    await rt.deleteTeam(t.id);
    expect(() => rt.sendMessage("w1", "hi")).toThrow(/unknown recipient/);
  });
  it("disposeAll unregisters teammates from the bus", async () => {
    const rt = newRuntime();
    const t = rt.createTeam("a");
    rt.spawnTeammate({ teamId: t.id, name: "w1", prompt: "x" });
    await rt.disposeAll();
    expect(() => rt.sendMessage("w1", "hi")).toThrow(/unknown recipient/);
  });
  it("gives a teammate a cc-tasks server + shares the task list under its own agentName (30.1/15.10)", async () => {
    let seen: any;
    const fq = ({ prompt, options }: any) => {
      seen = options;
      return (async function* () { for await (const t of prompt) { void t; yield { type: "result", result: "r" }; } })();
    };
    const d = dir();
    const rt = new SwarmRuntime({ query: fq }, { taskOptions: { dir: d } });
    const team = rt.createTeam("a");
    rt.spawnTeammate({ teamId: team.id, name: "w1", prompt: "x" });
    expect(seen.mcpServers["cc-tasks"]).toBeTruthy();   // teammate can claim via the task tools
    expect(seen.disallowedTools).toEqual(expect.arrayContaining(["TaskCreate", "TaskUpdate", "TodoWrite"])); // native per-session tasks disabled
    await rt.tasks.create({ subject: "job" });
    const claimed = await new TaskStore({ dir: d, agentName: "w1" }).update(1, { status: "in_progress" });
    expect(claimed.owner).toBe("w1");                   // claims as itself over the shared file
    expect((await rt.tasks.get(1))?.owner).toBe("w1");  // visible to the runtime store
    return rt.disposeAll();
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
    expect(seen.model).toBe("claude-haiku-4-5-20251001");
    return rt.disposeAll();
  });
  it("wires canUseTool into teammate options; the broker allows/denies by policy", async () => {
    let seen: any;
    const fq = ({ prompt, options }: any) => { seen = options; return (async function* () { for await (const t of prompt) { void t; yield { type: "result", result: "r" }; } })(); };
    const rt = new SwarmRuntime({ query: fq }, { taskOptions: { dir: dir() } });
    const team = rt.createTeam("a");
    rt.spawnTeammate({ teamId: team.id, name: "w1", prompt: "x" });
    expect(typeof seen.canUseTool).toBe("function");
    expect((await seen.canUseTool("Read", {})).behavior).toBe("allow");
    expect((await seen.canUseTool("Bash", {})).behavior).toBe("deny");
    return rt.disposeAll();
  });
  it("escalates a teammate permission to the coordinator inbox, resolved by respondPermission", async () => {
    let cut: any;
    const fq = ({ prompt, options }: any) => { cut = options.canUseTool; return (async function* () { for await (const t of prompt) { void t; yield { type: "result", result: "r" }; } })(); };
    const rt = new SwarmRuntime({ query: fq }, { taskOptions: { dir: dir() }, permissions: { escalateToCoordinator: true } });
    const team = rt.createTeam("a");
    rt.spawnTeammate({ teamId: team.id, name: "w1", prompt: "x" });
    const decision = cut("Bash", { command: "ls" }); // teammate asks
    const perm = rt.checkMessages().find((m) => m.kind === "permission");
    expect(perm).toBeTruthy();
    const requestId = (perm!.data as any).requestId;
    expect(rt.respondPermission(requestId, "allow")).toBe(true);
    expect((await decision).behavior).toBe("allow");
    return rt.disposeAll();
  });
  it("spawns a plan-mode teammate, escalates its ExitPlanMode plan, and approves it (mode transition + allow)", async () => {
    const modes: string[] = [];
    let cut: any;
    const fq = ({ prompt, options }: any) => {
      cut = options.canUseTool;
      const gen: any = (async function* () { for await (const t of prompt) { void t; yield { type: "result", result: "r" }; } })();
      gen.setPermissionMode = async (m: string) => { modes.push(m); };
      return gen;
    };
    const rt = new SwarmRuntime({ query: fq }, { taskOptions: { dir: dir() }, permissions: { onPlanApproval: "acceptEdits" } });
    const team = rt.createTeam("a");
    rt.spawnTeammate({ teamId: team.id, name: "w1", prompt: "x", plan: true });

    const decision = cut("ExitPlanMode", { plan: "# Plan\nship it", planFilePath: "/tmp/p.md" }); // teammate presents plan
    const env = rt.checkMessages().find((m) => m.kind === "plan");
    expect(env).toBeTruthy();
    expect((env!.data as any).plan).toContain("ship it");
    const requestId = (env!.data as any).requestId;

    expect(await rt.respondPlan(requestId, "approve")).toBe(true);
    expect(modes).toEqual(["acceptEdits"]);                 // transitioned to the configured post-approval mode
    const r = await decision;
    expect(r.behavior).toBe("allow");
    expect((r as any).updatedInput).toEqual({ plan: "# Plan\nship it", planFilePath: "/tmp/p.md" });
    await rt.disposeAll();
  });
  it("sets permissionMode:'plan' only for plan-mode teammates; respondPlan on an unknown id is false", async () => {
    const seen: any[] = [];
    const fq = ({ prompt, options }: any) => { seen.push(options); return (async function* () { for await (const t of prompt) { void t; yield { type: "result", result: "r" }; } })(); };
    const rt = new SwarmRuntime({ query: fq }, { taskOptions: { dir: dir() } });
    const t = rt.createTeam("a");
    rt.spawnTeammate({ teamId: t.id, name: "p1", prompt: "x", plan: true });
    rt.spawnTeammate({ teamId: t.id, name: "n1", prompt: "x" });
    expect(seen[0].permissionMode).toBe("plan");
    expect(seen[1].permissionMode).toBeUndefined();
    expect(await rt.respondPlan("req-nope", "approve")).toBe(false);
    await rt.disposeAll();
  });
  it("a reject resolves the teammate's ExitPlanMode to deny with feedback", async () => {
    let cut: any;
    const fq = ({ prompt, options }: any) => { cut = options.canUseTool; return (async function* () { for await (const t of prompt) { void t; yield { type: "result", result: "r" }; } })(); };
    const rt = new SwarmRuntime({ query: fq }, { taskOptions: { dir: dir() } });
    const t = rt.createTeam("a");
    rt.spawnTeammate({ teamId: t.id, name: "w1", prompt: "x", plan: true });
    const decision = cut("ExitPlanMode", { plan: "bad plan" });
    const id = (rt.checkMessages().find((m) => m.kind === "plan")!.data as any).requestId;
    await rt.respondPlan(id, "reject", "needs tests");
    const r = await decision;
    expect(r.behavior).toBe("deny");
    expect((r as any).message).toBe("needs tests");
    await rt.disposeAll();
  });
  it("disposing a teammate with a parked plan resolves it (deny) instead of leaking it", async () => {
    let cut: any;
    const fq = ({ prompt, options }: any) => { cut = options.canUseTool; return (async function* () { for await (const t of prompt) { void t; yield { type: "result", result: "r" }; } })(); };
    const rt = new SwarmRuntime({ query: fq }, { taskOptions: { dir: dir() } });
    const t = rt.createTeam("a");
    rt.spawnTeammate({ teamId: t.id, name: "w1", prompt: "x", plan: true });
    const decision = cut("ExitPlanMode", { plan: "p" }); // park awaiting approval
    rt.checkMessages();                                    // drain the plan envelope
    await rt.disposeAll();                                 // teardown must cancel the parked plan
    const r = await decision;
    expect(r.behavior).toBe("deny");
  });
  it("teardown: a second disposeAll() is a safe no-op (idempotent)", async () => {
    const rt = newRuntime();
    const team = rt.createTeam("alpha");
    rt.spawnTeammate({ teamId: team.id, name: "w1", prompt: "seed" });
    await rt.disposeAll();
    await expect(rt.disposeAll()).resolves.toBeUndefined();  // second teardown must not throw
  });

  it("requestShutdown emits a shutdown ack and unregisters the teammate", async () => {
    const fq = ({ prompt }: any) => (async function* () { for await (const t of prompt) { void t; yield { type: "result", result: "r" }; } })();
    const rt = new SwarmRuntime({ query: fq }, { taskOptions: { dir: dir() } });
    const team = rt.createTeam("a");
    rt.spawnTeammate({ teamId: team.id, name: "w1", prompt: "x" });
    await rt.requestShutdown("w1");
    expect(rt.checkMessages().some((m) => m.kind === "shutdown")).toBe(true);
    expect(() => rt.sendMessage("w1", "hi")).toThrow(/unknown recipient/);
    await expect(rt.requestShutdown("ghost")).rejects.toThrow(/unknown teammate/);
  });
});
