import { describe, it, expect } from "vitest";
import { ControlBridge } from "../../src/bridge/control.js";
import { controlFrame } from "../../src/bridge/types.js";
import type { ControllableSession } from "../../src/bridge/types.js";

function fakeSession(calls: any[], overrides: Partial<ControllableSession> = {}): ControllableSession {
  return {
    setModel: async (m) => { calls.push(["setModel", m]); },
    setPermissionMode: async (mode) => { calls.push(["setPermissionMode", mode]); },
    setMaxThinkingTokens: async (n) => { calls.push(["setMaxThinkingTokens", n]); },
    interrupt: async () => { calls.push(["interrupt"]); },
    capabilities: async () => ({ models: [{ value: "m1" }], commands: [{ name: "help" }], mcpServers: [] }),
    ...overrides,
  };
}

describe("ControlBridge", () => {
  it("routes each frame to the matching method with the right args", async () => {
    const calls: any[] = [];
    const s = fakeSession(calls);
    expect(await ControlBridge.apply(s, { type: "set_model", model: "x" })).toEqual({ ok: true });
    expect(await ControlBridge.apply(s, { type: "set_permission_mode", mode: "plan" })).toEqual({ ok: true });
    expect(await ControlBridge.apply(s, { type: "set_thinking", maxTokens: 0 })).toEqual({ ok: true });
    expect(await ControlBridge.apply(s, { type: "interrupt" })).toEqual({ ok: true });
    expect(calls).toEqual([["setModel", "x"], ["setPermissionMode", "plan"], ["setMaxThinkingTokens", 0], ["interrupt"]]);
  });
  it("initialize returns the capabilities payload", async () => {
    const r = await ControlBridge.apply(fakeSession([]), { type: "initialize" });
    expect(r).toMatchObject({ ok: true, models: [{ value: "m1" }], commands: [{ name: "help" }], mcpServers: [] });
  });
  it("reports unsupported for a missing method (never throws)", async () => {
    const s = fakeSession([], { setModel: undefined });
    expect(await ControlBridge.apply(s, { type: "set_model", model: "x" })).toEqual({ ok: false, error: "unsupported: setModel" });
  });
  it("converts a throwing method into a structured error", async () => {
    const s = fakeSession([], { setModel: async () => { throw new Error("bad model"); } });
    expect(await ControlBridge.apply(s, { type: "set_model", model: "x" })).toEqual({ ok: false, error: "bad model" });
  });
  it("initialize converts a throwing capabilities() into a structured error", async () => {
    const s = fakeSession([], { capabilities: async () => { throw new Error("cap boom"); } });
    expect(await ControlBridge.apply(s, { type: "initialize" })).toEqual({ ok: false, error: "cap boom" });
  });
  it("controlFrame rejects an unknown frame type and accepts valid ones", () => {
    expect(controlFrame.safeParse({ type: "nope" }).success).toBe(false);
    expect(controlFrame.safeParse({ type: "set_model", model: "x" }).success).toBe(true);
    expect(controlFrame.safeParse({ type: "set_permission_mode", mode: "bogus" }).success).toBe(false);
  });
});
