import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DaemonSupervisor } from "../../src/daemon/supervisor.js";
import { DaemonError, daemonOp } from "../../src/daemon/types.js";
import { NATIVE_TASK_TOOLS } from "../../src/swarm/coordinator.js";
const CC_TASKS = ["TaskCreate", "TaskUpdate", "TaskGet", "TaskList"].map((t) => `mcp__cc-tasks__${t}`);

const dir = () => mkdtempSync(join(tmpdir(), "cc-daemon-"));
function fakeQuery({ prompt }: any) {
  return (async function* () { for await (const t of prompt) yield { type: "result", result: "did:" + t.message.content }; })();
}
function captureQuery(sink: any[]) {
  return ({ prompt, options }: any) => {
    sink.push(options);
    return (async function* () { for await (const t of prompt) yield { type: "result", result: "did:" + t.message.content }; })();
  };
}
function controllableQuery(calls: any[]) {
  return ({ prompt }: any) => {
    const gen = (async function* () { for await (const _t of prompt) yield { type: "result", result: "ok" }; })();
    return Object.assign(gen, {
      setModel: async (m?: string) => { calls.push(["setModel", m]); },
      interrupt: async () => { calls.push(["interrupt"]); },
      supportedModels: async () => [{ value: "m1" }],
      supportedCommands: async () => [{ name: "help" }],
      mcpServerStatus: async () => [],
    });
  };
}

describe("DaemonSupervisor", () => {
  it("spawn registers an idle record; submit flips busy→idle and returns the result", async () => {
    const sup = new DaemonSupervisor({ query: fakeQuery }, { dir: dir() });
    const id = sup.spawn({ model: "m1" });
    expect(sup.list()).toEqual([expect.objectContaining({ id, status: "idle", model: "m1" })]);
    const r = await sup.submit(id, "hi", () => {});
    expect(r.result).toBe("did:hi");
    expect(sup.list()[0].status).toBe("idle");
    await sup.shutdown();
  });
  it("enforces maxSessions and throws on unknown ids", async () => {
    const sup = new DaemonSupervisor({ query: fakeQuery }, { dir: dir(), maxSessions: 1 });
    sup.spawn();
    expect(() => sup.spawn()).toThrow(DaemonError);
    await expect(sup.submit("ghost", "x", () => {})).rejects.toThrow(/unknown session/);
    await expect(sup.stop("ghost")).rejects.toThrow(/unknown session/);
    await sup.shutdown();
  });
  it("stop disposes the session and removes its record", async () => {
    const sup = new DaemonSupervisor({ query: fakeQuery }, { dir: dir() });
    const id = sup.spawn();
    await sup.stop(id);
    expect(sup.list()).toEqual([]);
    await sup.shutdown();
  });
  it("reapIdle stops sessions idle past the timeout (injected clock)", async () => {
    let t = 1000;
    const sup = new DaemonSupervisor({ query: fakeQuery }, { dir: dir(), idleTimeoutMs: 500, now: () => t });
    const id = sup.spawn();
    t = 1400; await sup.reapIdle();           // 400ms idle < 500 → kept
    expect(sup.list().map((s) => s.id)).toEqual([id]);
    t = 1600; await sup.reapIdle();           // 600ms idle > 500 → reaped
    expect(sup.list()).toEqual([]);
    await sup.shutdown();
  });
  it("submit to a session whose query has died rejects instead of hanging", async () => {
    // query ends after the first turn → session no longer running
    const fq = ({ prompt }: any) => (async function* () { for await (const t of prompt) { yield { type: "result", result: "ok:" + t.message.content }; return; } })();
    const sup = new DaemonSupervisor({ query: fq }, { dir: dir() });
    const id = sup.spawn();
    expect((await sup.submit(id, "first", () => {})).result).toBe("ok:first");
    await expect(sup.submit(id, "second", () => {})).rejects.toBeTruthy(); // would hang without the ended-guard
    await sup.shutdown();
  }, 10_000);
  it("shutdown disposes all sessions and clears the registry", async () => {
    const sup = new DaemonSupervisor({ query: fakeQuery }, { dir: dir() });
    sup.spawn(); sup.spawn();
    await sup.shutdown();
    expect(sup.list()).toEqual([]);
  });

  // ---- D2 restart machinery ----
  // flush pending microtasks/macrotasks so a dead session's done.then(handleSessionEnd) runs
  const flush = () => new Promise((r) => setTimeout(r, 0));
  // a query that dies immediately (yields nothing, returns) — simulates a crash
  const dyingQuery = () => (async function* () { /* ends at once */ })();
  // a query that works (one result per turn), ends only on dispose
  const healthyQuery = ({ prompt }: any) => (async function* () { for await (const t of prompt) yield { type: "result", result: "ok:" + t.message.content }; })();

  it("on-failure restarts a dead session into a working one (restarting → idle, count tracked)", async () => {
    let calls = 0;
    const fq = (a: any) => { calls++; return calls === 1 ? dyingQuery() : healthyQuery(a); };
    let pending: (() => void) | undefined;
    const scheduleRestart = (fn: () => void) => { pending = fn; return () => { pending = undefined; }; };
    const sup = new DaemonSupervisor({ query: fq }, { dir: dir(), restart: "on-failure", scheduleRestart });
    const id = sup.spawn();
    await flush();                                   // session 1 dies → handleSessionEnd schedules a restart
    expect(sup.list()[0]).toMatchObject({ status: "restarting", restarts: 1 });
    pending!();                                      // fire the restart
    expect(sup.list()[0].status).toBe("idle");
    expect(calls).toBe(2);
    expect((await sup.submit(id, "hi", () => {})).result).toBe("ok:hi"); // restarted session works
    await sup.shutdown();
  });
  it("gives up (errored) once maxRestarts is exceeded", async () => {
    let pending: (() => void) | undefined;
    const scheduleRestart = (fn: () => void) => { pending = fn; return () => {}; };
    const sup = new DaemonSupervisor({ query: dyingQuery }, { dir: dir(), restart: "on-failure", maxRestarts: 1, scheduleRestart });
    sup.spawn();
    await flush();                                   // death 1 → restarts 1, restarting
    expect(sup.list()[0]).toMatchObject({ status: "restarting", restarts: 1 });
    pending!(); await flush();                       // restart → dies again → restarts 2 > 1 → errored
    expect(sup.list()[0]).toMatchObject({ status: "errored", restarts: 2 });
    await sup.shutdown();
  });
  it("default policy 'no' leaves a dead session errored and never schedules a restart", async () => {
    let sched = 0;
    const sup = new DaemonSupervisor({ query: dyingQuery }, { dir: dir(), scheduleRestart: () => { sched++; return () => {}; } });
    sup.spawn();
    await flush();
    expect(sup.list()[0].status).toBe("errored");
    expect(sched).toBe(0);
    await sup.shutdown();
  });
  it("INVARIANT: an intentional stop never triggers a restart", async () => {
    let sched = 0;
    const sup = new DaemonSupervisor({ query: healthyQuery }, { dir: dir(), restart: "on-failure", scheduleRestart: () => { sched++; return () => {}; } });
    const id = sup.spawn();
    await sup.stop(id);                              // dispose → end hook fires but id is in `stopping`
    await flush();
    expect(sched).toBe(0);
    expect(sup.list()).toEqual([]);
    await sup.shutdown();
  });
  it("INVARIANT: shutdown never triggers a restart", async () => {
    let sched = 0;
    const sup = new DaemonSupervisor({ query: healthyQuery }, { dir: dir(), restart: "on-failure", scheduleRestart: () => { sched++; return () => {}; } });
    sup.spawn(); sup.spawn();
    await sup.shutdown();
    await flush();
    expect(sched).toBe(0);
  });
  it("a stop during the restarting window cancels the pending restart", async () => {
    let pending: (() => void) | undefined;
    let cancelled = false;
    const scheduleRestart = (fn: () => void) => { pending = fn; return () => { cancelled = true; }; };
    const sup = new DaemonSupervisor({ query: dyingQuery }, { dir: dir(), restart: "on-failure", scheduleRestart });
    const id = sup.spawn();
    await flush();                                   // restarting, pending set
    expect(sup.list()[0].status).toBe("restarting");
    await sup.stop(id);                              // removes the record + config
    expect(cancelled).toBe(true);                    // cancelRestart actually invoked the canceller
    if (pending) pending();                          // firing it now is a no-op anyway (config gone)
    expect(sup.list()).toEqual([]);
    await sup.shutdown();
  });
  it("submit during the restarting window reports the status", async () => {
    const scheduleRestart = () => () => {};          // never actually restarts
    const sup = new DaemonSupervisor({ query: dyingQuery }, { dir: dir(), restart: "on-failure", scheduleRestart });
    const id = sup.spawn();
    await flush();
    await expect(sup.submit(id, "x", () => {})).rejects.toThrow(/is restarting/);
    await sup.shutdown();
  });

  // ---- D3 sharedTasks built-in ----
  it("sharedTasks wires a cc-tasks server + native-off + allowlist into every session", async () => {
    const cap: any[] = [];
    const sup = new DaemonSupervisor({ query: captureQuery(cap) }, { dir: dir(), sharedTasks: { dir: dir() } });
    expect(sup.tasks).toBeDefined();
    sup.spawn(); sup.spawn();
    for (const opts of cap) {
      expect(opts.mcpServers).toHaveProperty("cc-tasks");
      expect(opts.disallowedTools).toEqual(expect.arrayContaining([...NATIVE_TASK_TOOLS]));
      expect(opts.allowedTools).toEqual(CC_TASKS);
    }
    expect(cap[0].mcpServers["cc-tasks"]).not.toBe(cap[1].mcpServers["cc-tasks"]); // fresh instance per session
    await sup.shutdown();
  });
  it("all sessions share ONE task store (writes to supervisor.tasks are visible through it)", async () => {
    const sup = new DaemonSupervisor({ query: captureQuery([]) }, { dir: dir(), sharedTasks: { dir: dir() } });
    sup.spawn(); sup.spawn();
    await sup.tasks!.create({ subject: "SHARED_OK" });
    const items = await sup.tasks!.list();
    expect(items.map((t) => t.subject)).toEqual(["SHARED_OK"]);
    await sup.shutdown();
  });
  it("an explicit sessionOptions overrides the sharedTasks default factory (tasks still created)", async () => {
    const cap: any[] = [];
    const sup = new DaemonSupervisor({ query: captureQuery(cap) }, {
      dir: dir(), sharedTasks: { dir: dir() },
      sessionOptions: () => ({ mcpServers: { custom: {} } }),
    });
    sup.spawn();
    expect(cap[0].mcpServers).toHaveProperty("custom");
    expect(cap[0].mcpServers).not.toHaveProperty("cc-tasks");
    expect(cap[0].allowedTools).toBeUndefined();
    expect(sup.tasks).toBeDefined();           // still created for inspection
    await sup.shutdown();
  });
  it("sharedTasks: true normalizes to TaskStore defaults", async () => {
    const cap: any[] = [];
    const cwd = process.cwd();
    process.chdir(dir());                       // keep TaskStore's default write inside a tmp dir
    try {
      const sup = new DaemonSupervisor({ query: captureQuery(cap) }, { dir: dir(), sharedTasks: true });
      expect(sup.tasks).toBeDefined();
      sup.spawn();
      expect(cap[0].allowedTools).toEqual(CC_TASKS);
      await sup.shutdown();
    } finally { process.chdir(cwd); }
  });

  // ---- D3 generic sessionOptions seam ----
  it("merges a sessionOptions factory into each session's options (model preserved)", async () => {
    const cap: any[] = [];
    const sup = new DaemonSupervisor({ query: captureQuery(cap) }, {
      dir: dir(),
      sessionOptions: (id) => ({ mcpServers: { probe: {} }, marker: id }),
    });
    const id = sup.spawn({ model: "m1" });
    expect(cap).toHaveLength(1);
    expect(cap[0]).toMatchObject({ model: "m1", marker: id });
    expect(cap[0].mcpServers).toHaveProperty("probe");
    await sup.shutdown();
  });
  it("a restarted session receives fresh factory options too (compose with D2)", async () => {
    const cap: any[] = [];
    let calls = 0;
    const fq = ({ prompt, options }: any) => {
      cap.push(options); calls++;
      if (calls === 1) return (async function* () { /* dies at once */ })();
      return (async function* () { for await (const t of prompt) yield { type: "result", result: "ok:" + t.message.content }; })();
    };
    let pending: (() => void) | undefined;
    const scheduleRestart = (fn: () => void) => { pending = fn; return () => {}; };
    const sup = new DaemonSupervisor({ query: fq }, {
      dir: dir(), restart: "on-failure", scheduleRestart,
      sessionOptions: () => ({ mcpServers: { "cc-tasks": {} } }),
    });
    sup.spawn();
    await flush();                 // session 1 dies → restart scheduled
    pending!();                    // fire restart → session 2 constructed
    expect(cap).toHaveLength(2);
    expect(cap[0].mcpServers).toHaveProperty("cc-tasks");
    expect(cap[1].mcpServers).toHaveProperty("cc-tasks");
    expect(cap[1].mcpServers).not.toBe(cap[0].mcpServers); // fresh object per session
    await sup.shutdown();
  });

  // ---- Phase 2 B: control op ----
  it("control routes a frame to the pooled session via ControlBridge; unknown id throws", async () => {
    const calls: any[] = [];
    const sup = new DaemonSupervisor({ query: controllableQuery(calls) }, { dir: dir() });
    const id = sup.spawn();
    expect(await sup.control(id, { type: "set_model", model: "x" })).toEqual({ ok: true });
    expect(calls).toContainEqual(["setModel", "x"]);
    expect((await sup.control(id, { type: "initialize" })).ok).toBe(true);
    await expect(sup.control("ghost", { type: "interrupt" })).rejects.toThrow(/unknown session/);
    await sup.shutdown();
  });
  it("daemonOp accepts a control op", () => {
    expect(daemonOp.safeParse({ op: "control", id: "s1", frame: { type: "interrupt" } }).success).toBe(true);
    expect(daemonOp.safeParse({ op: "control", id: "s1", frame: { type: "bogus" } }).success).toBe(false);
  });
});
