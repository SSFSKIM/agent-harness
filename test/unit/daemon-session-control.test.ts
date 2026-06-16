import { describe, it, expect } from "vitest";
import { DaemonSession } from "../../src/daemon/session.js";

// A fake query() return that is BOTH an async generator AND carries the SDK control methods.
function controllableQuery(calls: any[]) {
  return ({ prompt }: any) => {
    const gen = (async function* () { for await (const _t of prompt) yield { type: "result", result: "ok" }; })();
    return Object.assign(gen, {
      setModel: async (m?: string) => { calls.push(["setModel", m]); },
      setPermissionMode: async (mode: string) => { calls.push(["setPermissionMode", mode]); },
      setMaxThinkingTokens: async (n: number | null) => { calls.push(["setMaxThinkingTokens", n]); },
      interrupt: async () => { calls.push(["interrupt"]); },
      supportedModels: async () => [{ value: "m1", displayName: "M1" }],
      supportedCommands: async () => [{ name: "help" }],
      mcpServerStatus: async () => [{ name: "cc-tasks" }],
    });
  };
}

describe("DaemonSession control surface", () => {
  it("delegates control methods to its Query and reports capabilities", async () => {
    const calls: any[] = [];
    const s = new DaemonSession("s1", { query: controllableQuery(calls) }, {});
    await s.setModel("x");
    await s.setPermissionMode("plan");
    await s.setMaxThinkingTokens(0);
    await s.interrupt();
    expect(calls).toEqual([["setModel", "x"], ["setPermissionMode", "plan"], ["setMaxThinkingTokens", 0], ["interrupt"]]);
    expect(await s.capabilities()).toEqual({
      models: [{ value: "m1", displayName: "M1" }], commands: [{ name: "help" }], mcpServers: [{ name: "cc-tasks" }],
    });
    await s.dispose();
  });
  it("setters reject once ended; interrupt stays a safe no-op", async () => {
    const calls: any[] = [];
    const s = new DaemonSession("s2", { query: controllableQuery(calls) }, {});
    await s.dispose();                                       // input.close() → readLoop ends → ended
    await expect(s.setModel("x")).rejects.toThrow(/not running/);
    await expect(s.interrupt()).resolves.toBeUndefined();   // no assert-running → no throw
    expect(calls.filter((c) => c[0] === "setModel")).toEqual([]); // setter never delegated
  });
  it("reports unsupported when the underlying Query lacks a control method", async () => {
    const bareQuery = ({ prompt }: any) => (async function* () { for await (const _t of prompt) yield { type: "result", result: "ok" }; })();
    const s = new DaemonSession("s3", { query: bareQuery }, {});
    await expect(s.setModel("x")).rejects.toThrow(/unsupported: setModel/);
    await s.dispose();
  });
});
