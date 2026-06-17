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
// emits a system/init frame (carrying session_id) then a result, per turn — so Session captures sessionId
function initQuery(sid: string) {
  return ({ prompt }: any) => (async function* () {
    for await (const t of prompt) {
      yield { type: "system", subtype: "init", session_id: sid };
      yield { type: "result", result: "did:" + t.message.content };
    }
  })();
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
  it("control on a dead (errored) pooled session throws instead of returning ok", async () => {
    const sup = new DaemonSupervisor({ query: dyingQuery }, { dir: dir() }); // dies immediately → errored
    const id = sup.spawn();
    await flush();                                   // handleSessionEnd → errored (session still pooled)
    expect(sup.list()[0].status).toBe("errored");
    await expect(sup.control(id, { type: "interrupt" })).rejects.toThrow(/is errored/);
    await sup.shutdown();
  });

  // ---- Phase 2 C: proactive heartbeat ----
  // A scheduler the test controls: capture pending tick callbacks, fire them on demand.
  function captureSched() {
    const pend: (() => void)[] = [];
    const scheduleRestart = (fn: () => void) => { pend.push(fn); return () => {}; };
    const fire = async () => { const fn = pend.pop(); if (fn) { fn(); await flush(); } };
    return { scheduleRestart, fire };
  }

  it("startProactive: unknown id throws, double-start throws, returns running status", async () => {
    const s = captureSched();
    const sup = new DaemonSupervisor({ query: healthyQuery }, { dir: dir(), scheduleRestart: s.scheduleRestart });
    expect(() => sup.startProactive("ghost")).toThrow(/unknown session/);
    const id = sup.spawn();
    expect(sup.startProactive(id, { intervalMs: 1000 })).toMatchObject({ state: "running", tickCount: 0 });
    expect(() => sup.startProactive(id)).toThrow(/already proactive/);
    await sup.shutdown();
  });

  it("a fired heartbeat tick submits the tickPrompt into the session", async () => {
    const s = captureSched();
    const seen: string[] = [];
    const recordingQuery = ({ prompt }: any) => (async function* () {
      for await (const t of prompt) { seen.push(t.message.content); yield { type: "result", result: "ok" }; }
    })();
    const sup = new DaemonSupervisor({ query: recordingQuery }, { dir: dir(), scheduleRestart: s.scheduleRestart });
    const id = sup.spawn();
    sup.startProactive(id, { tickPrompt: "HB", intervalMs: 1000 });
    await s.fire();                                  // fire the first scheduled tick
    expect(seen).toContain("HB");
    expect(sup.proactiveStatus(id)!.tickCount).toBe(1);
    await sup.shutdown();
  });

  it("submit auto-pauses the heartbeat and resumes it after the human turn", async () => {
    const s = captureSched();
    const sup = new DaemonSupervisor({ query: healthyQuery }, { dir: dir(), scheduleRestart: s.scheduleRestart });
    const id = sup.spawn();
    sup.startProactive(id, { intervalMs: 1000 });
    expect((await sup.submit(id, "hi", () => {})).result).toBe("ok:hi");
    expect(sup.proactiveStatus(id)!.state).toBe("running"); // resumed, not stuck paused
    await sup.shutdown();
  });

  it("submit does NOT resume a heartbeat that already self-stopped (lingers in the map)", async () => {
    const s = captureSched();
    const idleQuery = ({ prompt }: any) => (async function* () {
      for await (const _t of prompt) yield { type: "result", result: "IDLE" };
    })();
    const sup = new DaemonSupervisor({ query: idleQuery }, { dir: dir(), scheduleRestart: s.scheduleRestart });
    const id = sup.spawn();
    sup.startProactive(id, { intervalMs: 1000, idleBackoff: { stopAfterIdle: 1 } });
    await s.fire();                                  // one idle tick → loop self-stops
    expect(sup.proactiveStatus(id)!.state).toBe("stopped");
    await sup.submit(id, "hi", () => {});            // must not throw / must not resume
    expect(sup.proactiveStatus(id)!.state).toBe("stopped");
    await sup.shutdown();
  });

  it("stop(id) tears the heartbeat down before disposing the session", async () => {
    const s = captureSched();
    const sup = new DaemonSupervisor({ query: healthyQuery }, { dir: dir(), scheduleRestart: s.scheduleRestart });
    const id = sup.spawn();
    sup.startProactive(id, { intervalMs: 1000 });
    await sup.stop(id);
    expect(sup.proactiveStatus(id)).toBeUndefined();
    expect(sup.list()).toEqual([]);
    await sup.shutdown();
  });

  it("stopProactive on a non-proactive session throws", async () => {
    const sup = new DaemonSupervisor({ query: healthyQuery }, { dir: dir() });
    const id = sup.spawn();
    await expect(sup.stopProactive(id)).rejects.toThrow(/not proactive/);
    await sup.shutdown();
  });

  it("reapIdle skips a session with an active heartbeat", async () => {
    let t = 1000;
    const s = captureSched();
    const sup = new DaemonSupervisor({ query: healthyQuery }, { dir: dir(), idleTimeoutMs: 500, now: () => t, scheduleRestart: s.scheduleRestart });
    const id = sup.spawn();
    sup.startProactive(id, { intervalMs: 1000 });
    t = 5000; await sup.reapIdle();                 // way past the timeout, but proactive → kept
    expect(sup.list().map((x) => x.id)).toEqual([id]);
    await sup.shutdown();
  });

  it("reapIdle DOES reap a session whose heartbeat has self-stopped", async () => {
    let t = 1000;
    const s = captureSched();
    const idleQuery = ({ prompt }: any) => (async function* () {
      for await (const _t of prompt) yield { type: "result", result: "IDLE" };
    })();
    const sup = new DaemonSupervisor({ query: idleQuery }, { dir: dir(), idleTimeoutMs: 500, now: () => t, scheduleRestart: s.scheduleRestart });
    const id = sup.spawn();
    sup.startProactive(id, { intervalMs: 1000, idleBackoff: { stopAfterIdle: 1 } });
    await s.fire();                                  // one idle tick → loop self-stops
    expect(sup.proactiveStatus(id)!.state).toBe("stopped");
    t = 5000; await sup.reapIdle();                 // self-stopped heartbeat must NOT exempt → reaped
    expect(sup.list()).toEqual([]);
    await sup.shutdown();
  });

  it("contextTool option wires cc-context into every spawned session", async () => {
    const sink: any[] = [];
    const sup = new DaemonSupervisor({ query: captureQuery(sink) }, { dir: dir(), contextTool: true });
    sup.spawn();
    expect((sink[0].mcpServers as any)["cc-context"]).toBeTruthy();
    expect(sink[0].allowedTools).toContain("mcp__cc-context__GetContextUsage");
    await sup.shutdown();
  });

  it("compact(id) delegates to the session and rejects unknown ids", async () => {
    const seen: string[] = [];
    const cq = ({ prompt }: any) => (async function* () {
      for await (const t of prompt) {
        const text = t.message.content; seen.push(text);
        if (text === "/compact") { yield { type: "system", subtype: "status", status: null, compact_result: "success" }; yield { type: "result", result: "c" }; }
        else yield { type: "result", result: "did:" + text };
      }
    })();
    const sup = new DaemonSupervisor({ query: cq }, { dir: dir() });
    const id = sup.spawn();
    expect(await sup.compact(id)).toEqual({ ok: true, result: "success", error: undefined, preTokens: undefined, postTokens: undefined });
    await expect(sup.compact("ghost")).rejects.toThrow(/unknown session/);
    await sup.shutdown();
  });
  it("compactTool option wires cc-compact into every spawned session", async () => {
    const sink: any[] = [];
    const sup = new DaemonSupervisor({ query: captureQuery(sink) }, { dir: dir(), compactTool: true });
    sup.spawn();
    expect((sink[0].mcpServers as any)["cc-compact"]).toBeTruthy();
    expect(sink[0].allowedTools).toContain("mcp__cc-compact__RequestCompaction");
    await sup.shutdown();
  });

  it("daemonOp accepts start_proactive (with/without config) and stop_proactive", () => {
    expect(daemonOp.safeParse({ op: "start_proactive", id: "s1" }).success).toBe(true);
    expect(daemonOp.safeParse({ op: "start_proactive", id: "s1", config: { intervalMs: 10 } }).success).toBe(true);
    expect(daemonOp.safeParse({ op: "start_proactive", id: "s1", config: { intervalMs: "x" } }).success).toBe(false);
    expect(daemonOp.safeParse({ op: "stop_proactive", id: "s1" }).success).toBe(true);
  });

  it("submit persists the captured SDK session_id onto the record", async () => {
    const sup = new DaemonSupervisor({ query: initQuery("sdk-abc") }, { dir: dir() });
    const id = sup.spawn();
    expect(sup.list()[0].sessionId).toBeUndefined();   // unknown before the first turn
    await sup.submit(id, "hi", () => {});
    expect(sup.list()[0].sessionId).toBe("sdk-abc");   // captured from the turn's init frame + persisted
    await sup.shutdown();
  });

  it("spawn({resume}) threads resume into the new session's options", async () => {
    const sink: any[] = [];
    const sup = new DaemonSupervisor({ query: captureQuery(sink) }, { dir: dir() });
    sup.spawn({ resume: "sess-prior" });
    expect(sink[0].resume).toBe("sess-prior");
    await sup.shutdown();
  });
  it("listPersistedSessions / getPersistedMessages delegate to the injected reader", async () => {
    const calls: any[] = [];
    const sup = new DaemonSupervisor({
      query: fakeQuery,
      listSessions: async (o: any) => { calls.push(["list", o]); return [{ sessionId: "s1" }]; },
      getSessionMessages: async (id: string, o: any) => { calls.push(["msgs", id, o]); return [{ uuid: "u1" }]; },
    }, { dir: dir() });
    expect(await sup.listPersistedSessions({ cwd: "/p", limit: 3 })).toEqual([{ sessionId: "s1" }]);
    expect(await sup.getPersistedMessages("sess-9", { cwd: "/p" })).toEqual([{ uuid: "u1" }]);
    expect(calls).toEqual([["list", { cwd: "/p", limit: 3 }], ["msgs", "sess-9", { cwd: "/p" }]]);
    await sup.shutdown();
  });
  it("auto-restart re-creates the session WITHOUT resume (stays fresh)", async () => {
    const sink: any[] = [];
    const dying = ({ options }: any) => { sink.push(options); return (async function* () {})(); };
    const sup = new DaemonSupervisor({ query: dying }, {
      dir: dir(), restart: "on-failure", maxRestarts: 1,
      scheduleRestart: (fn) => { fn(); return () => {}; },
    });
    sup.spawn({ resume: "sess-prior", restart: "on-failure" });
    await new Promise((r) => setTimeout(r, 20)); // let the death→restart cascade drain
    expect(sink[0].resume).toBe("sess-prior");                        // initial spawn carried resume
    expect(sink.length).toBeGreaterThanOrEqual(2);                   // it restarted at least once
    expect(sink.slice(1).every((o) => o.resume === undefined)).toBe(true); // restarts are fresh
    await sup.shutdown();
  });
});
