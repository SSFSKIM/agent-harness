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
});
