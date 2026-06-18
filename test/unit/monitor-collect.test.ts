import { describe, it, expect } from "vitest";
import { collect, type MonitorClient } from "../../src/monitor/snapshot.js";
import type { ListEntry } from "../../src/daemon/types.js";

function clientFrom(entries: ListEntry[], usage: Record<string, unknown | Error>): MonitorClient {
  return {
    list: async () => entries,
    contextUsage: async (id) => { const u = usage[id]; if (u instanceof Error) throw u; return u; },
  };
}
const rec = (over: Partial<ListEntry>): ListEntry =>
  ({ id: "s1", daemonPid: 1, status: "idle", createdAt: 0, lastActiveAt: 0, ...over });

describe("collect", () => {
  it("assembles rows, computes ctx% from totalTokens/maxTokens, aggregates proactive", async () => {
    const entries = [
      rec({ id: "a", status: "busy", model: "opus-4.8", proactive: { state: "running", tickCount: 1, idleCount: 0, errorCount: 0 } }),
      rec({ id: "b", status: "idle", model: "sonnet-4.6", proactive: { state: "paused", tickCount: 0, idleCount: 0, errorCount: 0 } }),
    ];
    const snap = await collect(clientFrom(entries, { a: { totalTokens: 1240, maxTokens: 2000 }, b: { totalTokens: 360, maxTokens: 2000 } }), { now: () => 1000, socketPath: "/s" });
    expect(snap.daemonUp).toBe(true);
    expect(snap.at).toBe(1000);
    expect(snap.sessions.map((r) => [r.id, r.ctxPercent, r.tokens])).toEqual([["a", 62, 1240], ["b", 18, 360]]);
    expect(snap.proactive).toBe("running"); // running outranks paused
  });

  it("skips context_usage for errored sessions and tolerates a usage failure (ctx stays undefined)", async () => {
    const entries = [rec({ id: "e", status: "errored" }), rec({ id: "f", status: "idle" })];
    const snap = await collect(clientFrom(entries, { f: new Error("not started") }), { now: () => 0 });
    expect(snap.sessions.find((r) => r.id === "e")!.ctxPercent).toBeUndefined();
    expect(snap.sessions.find((r) => r.id === "f")!.ctxPercent).toBeUndefined();
    expect(snap.proactive).toBeUndefined(); // no loops present
  });

  it("returns daemonUp=false when list() throws", async () => {
    const client: MonitorClient = { list: async () => { throw new Error("ECONNREFUSED"); }, contextUsage: async () => ({}) };
    const snap = await collect(client, { now: () => 5, socketPath: "/sock" });
    expect(snap).toEqual({ daemonUp: false, sessions: [], proactive: undefined, at: 5, socketPath: "/sock" });
  });

  it("renders ctx undefined when maxTokens is missing or zero", async () => {
    const snap = await collect(clientFrom([rec({ id: "z" })], { z: { totalTokens: 100 } }), { now: () => 0 });
    expect(snap.sessions[0].ctxPercent).toBeUndefined();
    expect(snap.sessions[0].tokens).toBe(100);
  });
});
