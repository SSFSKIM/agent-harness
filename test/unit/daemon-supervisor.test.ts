import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DaemonSupervisor } from "../../src/daemon/supervisor.js";
import { DaemonError } from "../../src/daemon/types.js";

const dir = () => mkdtempSync(join(tmpdir(), "cc-daemon-"));
function fakeQuery({ prompt }: any) {
  return (async function* () { for await (const t of prompt) yield { type: "result", result: "did:" + t.message.content }; })();
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
  it("shutdown disposes all sessions and clears the registry", async () => {
    const sup = new DaemonSupervisor({ query: fakeQuery }, { dir: dir() });
    sup.spawn(); sup.spawn();
    await sup.shutdown();
    expect(sup.list()).toEqual([]);
  });
});
