// harness/test/unit/daemon-permissions.test.ts
import { describe, it, expect } from "vitest";
import { PendingPermissions } from "../../src/daemon/permissions.js";
import type { PermissionRequest } from "../../src/permissions/types.js";

const req = (toolUseID: string, over: Partial<PermissionRequest> = {}): PermissionRequest =>
  ({ toolName: "Edit", input: { file_path: "f.ts" }, toolUseID, signal: new AbortController().signal, ...over });

describe("PendingPermissions", () => {
  it("park → respond resolves the awaited promise with the decision", async () => {
    const reg = new PendingPermissions({ now: () => 7 });
    const p = reg.brokerFor("sess-1").request(req("t1"));
    expect(reg.list()).toEqual([{ sessionId: "sess-1", toolUseID: "t1", toolName: "Edit", input: { file_path: "f.ts" }, createdAt: 7 }]);
    expect(reg.respond("t1", { kind: "allow_once" })).toBe(true);
    await expect(p).resolves.toEqual({ kind: "allow_once" });
    expect(reg.list()).toEqual([]);
  });

  it("park → timeout settles deny (no client / no answer)", async () => {
    let fire: () => void = () => {};
    const reg = new PendingPermissions({ schedule: (fn) => { fire = fn; return () => {}; } });
    const p = reg.brokerFor("s").request(req("t2"));
    fire();                                   // simulate the 30 s timeout elapsing
    await expect(p).resolves.toEqual({ kind: "deny" });
    expect(reg.list()).toEqual([]);
  });

  it("park → session teardown denies all of that session's pending; denyAll denies the rest", async () => {
    const reg = new PendingPermissions();
    const a = reg.brokerFor("s1").request(req("t3"));
    const b = reg.brokerFor("s2").request(req("t4"));
    reg.denyAllForSession("s1");
    await expect(a).resolves.toEqual({ kind: "deny" });
    expect(reg.list().map((e) => e.toolUseID)).toEqual(["t4"]); // s2 untouched
    reg.denyAll();
    await expect(b).resolves.toEqual({ kind: "deny" });
    expect(reg.list()).toEqual([]);
  });

  it("multi-answer is idempotent — the second respond is a no-op", async () => {
    const reg = new PendingPermissions();
    const p = reg.brokerFor("s").request(req("t5"));
    expect(reg.respond("t5", { kind: "allow_once" })).toBe(true);
    expect(reg.respond("t5", { kind: "deny" })).toBe(false);   // already settled
    await expect(p).resolves.toEqual({ kind: "allow_once" });
  });

  it("aborting the request signal settles deny and drops the entry (turn interrupted)", async () => {
    const reg = new PendingPermissions();
    const ac = new AbortController();
    const p = reg.brokerFor("s").request(req("t6", { signal: ac.signal }));
    ac.abort();
    await expect(p).resolves.toEqual({ kind: "deny" });
    expect(reg.list()).toEqual([]);
  });

  it("PendingEntry is serializable — no AbortSignal, round-trips through JSON", () => {
    const reg = new PendingPermissions({ now: () => 0 });
    reg.brokerFor("s").request(req("t7"));
    const entry = reg.list()[0];
    expect("signal" in entry).toBe(false);
    expect(JSON.parse(JSON.stringify(entry)).toolUseID).toBe("t7");
  });
});
