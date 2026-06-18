import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { SessionRegistry } from "../../src/daemon/registry.js";
import type { SessionRecord } from "../../src/daemon/types.js";

const dir = () => mkdtempSync(join(tmpdir(), "cc-daemon-"));
const rec = (id: string, pid = process.pid): SessionRecord =>
  ({ id, daemonPid: pid, status: "idle", createdAt: 1, lastActiveAt: 1 });

describe("SessionRegistry", () => {
  it("registers, gets, lists (sorted by createdAt), updates, and removes", () => {
    const r = new SessionRegistry({ dir: dir() });
    r.register({ ...rec("sess-2"), createdAt: 20 });
    r.register({ ...rec("sess-1"), createdAt: 10 });
    expect(r.list().map((x) => x.id)).toEqual(["sess-1", "sess-2"]); // createdAt order
    expect(r.get("sess-1")?.status).toBe("idle");
    r.update("sess-1", { status: "busy" });
    expect(r.get("sess-1")?.status).toBe("busy");
    r.remove("sess-1");
    expect(r.get("sess-1")).toBeUndefined();
    expect(r.list().map((x) => x.id)).toEqual(["sess-2"]);
  });
  it("reapStale drops records whose daemonPid is dead", () => {
    const r = new SessionRegistry({ dir: dir(), isAlive: (pid) => pid === 100 });
    r.register({ ...rec("live", 100) });
    r.register({ ...rec("dead", 999) });
    expect(r.reapStale()).toBe(1);
    expect(r.list().map((x) => x.id)).toEqual(["live"]);
  });
  it("rehydrate claims orphaned resumable records, reaps the rest, leaves live ones untouched", () => {
    const r = new SessionRegistry({ dir: dir(), isAlive: (pid) => pid === 100 });   // only pid 100 is alive
    r.register({ ...rec("live", 100), sessionId: "s-live" });                                // alive daemon → untouched
    r.register({ ...rec("idle-ok", 999), sessionId: "s1" });                                 // orphaned + resumable → claim
    r.register({ ...rec("busy-ok", 999), status: "busy", sessionId: "s2" });                 // orphaned busy → claim + normalize
    r.register({ ...rec("restarting-ok", 999), status: "restarting", sessionId: "s3" });     // orphaned restarting → claim
    r.register({ ...rec("no-sid", 999) });                                                   // orphaned, no sessionId → reap
    r.register({ ...rec("errored", 999), status: "errored", sessionId: "s4" });              // orphaned errored → reap
    const claimed = r.rehydrate(200).map((x) => x.id).sort();
    expect(claimed).toEqual(["busy-ok", "idle-ok", "restarting-ok"]);
    for (const id of claimed) expect(r.get(id)).toMatchObject({ daemonPid: 200, status: "idle", restarts: 0 });
    expect(r.list().map((x) => x.id).sort()).toEqual(["busy-ok", "idle-ok", "live", "restarting-ok"]); // reaped gone
    expect(r.get("live")).toMatchObject({ daemonPid: 100, sessionId: "s-live" });            // live record untouched
  });
});
