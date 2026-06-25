// harness/test/unit/daemon-supervisor-permissions.test.ts
import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DaemonSupervisor } from "../../src/daemon/supervisor.js";
import type { QueryFn } from "../../src/swarm/types.js";

const tmp = () => mkdtempSync(join(tmpdir(), "sup-perms-"));

// Fake query: capture each session's options; yield an init frame then hang (draining prompt so dispose() can exit).
function captureQuery(captured: any[]): QueryFn {
  return (({ prompt, options }: any) => { captured.push(options); return (async function* () {
    yield { type: "system", subtype: "init", session_id: "sdk-x" };
    for await (const _ of prompt) { /* drain so input.close() exits */ }
  })(); }) as unknown as QueryFn;
}
// Fake query that drives canUseTool once (fire-and-forget) so a request parks in the registry.
function gatingQuery(hold: { call?: Promise<any> }): QueryFn {
  return (({ prompt, options }: any) => (async function* () {
    yield { type: "system", subtype: "init", session_id: "sdk-x" };
    hold.call = options.canUseTool?.("Bash", { command: "x" }, { toolUseID: "tu", signal: new AbortController().signal });
    for await (const _ of prompt) { /* drain so input.close() exits */ }
  })()) as unknown as QueryFn;
}

describe("supervisor permission wiring", () => {
  it("auto + unsupported model forces sonnet-4-6 and sets permissionMode; broker wired", async () => {
    const cap: any[] = [];
    const sup = new DaemonSupervisor({ query: captureQuery(cap) }, { dir: tmp(), now: () => 0, idleTimeoutMs: 0 });
    const id = sup.spawn({ model: "claude-haiku-4-5-20251001", permissionMode: "auto" });
    expect(cap[0].model).toBe("claude-sonnet-4-6");
    expect(cap[0].permissionMode).toBe("auto");
    expect(typeof cap[0].canUseTool).toBe("function");
    expect(sup.list().find((r) => r.id === id)!.model).toBe("claude-sonnet-4-6");
    await sup.shutdown();
  });

  it("auto + no model → opus-4-8 (default); auto + supported preserved; non-auto leaves model + defaults mode to auto", async () => {
    const cap: any[] = [];
    const sup = new DaemonSupervisor({ query: captureQuery(cap) }, { dir: tmp(), now: () => 0, idleTimeoutMs: 0 });
    sup.spawn({ permissionMode: "auto" });
    sup.spawn({ model: "claude-opus-4-6", permissionMode: "auto" });
    sup.spawn({ model: "claude-haiku-4-5-20251001" });           // non-auto (explicit model)
    expect(cap[0].model).toBe("claude-opus-4-8");                 // auto + no model → opus default (was sonnet)
    expect(cap[1].model).toBe("claude-opus-4-6");
    expect(cap[2].model).toBe("claude-haiku-4-5-20251001");       // explicit model preserved
    expect(cap[2].permissionMode).toBe("auto");                   // non-auto spawn now defaults to auto
    expect(typeof cap[2].canUseTool).toBe("function");            // daemon broker still wired
    await sup.shutdown();
  });

  it("routes spawned sessions through resolveOptions — CC preset + settingSources + defaults", async () => {
    const cap: any[] = [];
    const sup = new DaemonSupervisor({ query: captureQuery(cap) }, { dir: tmp(), now: () => 0, idleTimeoutMs: 0 });
    sup.spawn({});                                                // no model, no mode → harness defaults
    expect(cap[0].systemPrompt.type).toBe("preset");              // fork advertisement appended by default
    expect(cap[0].systemPrompt.append).toContain("fork");
    expect(cap[0].settingSources).toEqual(["user", "project", "local"]);
    expect(cap[0].tools).toEqual({ type: "preset", preset: "claude_code" });
    expect(cap[0].model).toBe("claude-opus-4-8");
    expect(cap[0].permissionMode).toBe("auto");
    expect(typeof cap[0].canUseTool).toBe("function");           // daemon broker survives the factory overlay
    await sup.shutdown();
  });

  it("a parked request surfaces in pendingPermissions(); respondPermission resolves it", async () => {
    const hold: { call?: Promise<any> } = {};
    const sup = new DaemonSupervisor({ query: gatingQuery(hold) }, { dir: tmp(), now: () => 0, idleTimeoutMs: 0 });
    sup.spawn({ model: "claude-sonnet-4-6" });
    await new Promise((r) => setTimeout(r, 10));                 // let the gating query call canUseTool
    const pending = sup.pendingPermissions();
    expect(pending.map((e) => e.toolUseID)).toEqual(["tu"]);
    expect(sup.respondPermission("tu", { kind: "allow_once" })).toBe(true);
    await expect(hold.call).resolves.toEqual({ behavior: "allow", updatedInput: { command: "x" } });
    expect(sup.pendingPermissions()).toEqual([]);
    await sup.shutdown();
  });

  it("stop() denies a parked request for that session", async () => {
    const hold: { call?: Promise<any> } = {};
    const sup = new DaemonSupervisor({ query: gatingQuery(hold) }, { dir: tmp(), now: () => 0, idleTimeoutMs: 0 });
    const id = sup.spawn({ model: "claude-sonnet-4-6" });
    await new Promise((r) => setTimeout(r, 10));
    expect(sup.pendingPermissions().length).toBe(1);
    await sup.stop(id);
    await expect(hold.call).resolves.toEqual({ behavior: "deny", message: "User denied Bash", interrupt: undefined });
    expect(sup.pendingPermissions()).toEqual([]);
  });
});
