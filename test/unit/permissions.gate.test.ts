// harness/test/unit/permissions.gate.test.ts
import { describe, it, expect, vi } from "vitest";
import { createPermissionGate } from "../../src/permissions/gate.js";
import type { PermissionBroker, PermissionDecision } from "../../src/permissions/types.js";

const opts = (signal = new AbortController().signal) => ({ signal, toolUseID: "t1" });
const brokerReturning = (...decisions: PermissionDecision[]): PermissionBroker & { calls: number } => {
  let i = 0; const b: any = { calls: 0, async request() { b.calls++; return decisions[Math.min(i++, decisions.length - 1)]; } };
  return b;
};

describe("createPermissionGate", () => {
  it("maps allow_once → allow with updatedInput", async () => {
    const gate = createPermissionGate(brokerReturning({ kind: "allow_once" }));
    expect(await gate("Edit", { a: 1 }, opts())).toEqual({ behavior: "allow", updatedInput: { a: 1 } });
  });
  it("maps deny → deny with a message naming the tool", async () => {
    const r = await createPermissionGate(brokerReturning({ kind: "deny" }))("Bash", {}, opts());
    expect(r.behavior).toBe("deny");
    expect((r as any).message).toContain("Bash");
  });
  it("allow_always short-circuits the next call to the same tool (broker not re-consulted)", async () => {
    const broker = brokerReturning({ kind: "allow_always" });
    const gate = createPermissionGate(broker);
    expect((await gate("Edit", { a: 1 }, opts())).behavior).toBe("allow");
    expect((await gate("Edit", { a: 2 }, opts())).behavior).toBe("allow");
    expect(broker.calls).toBe(1); // second Edit was allowlisted, broker never called again
  });
  it("a pre-aborted signal denies without consulting the broker", async () => {
    const broker = brokerReturning({ kind: "allow_once" });
    const ac = new AbortController(); ac.abort();
    const r = await createPermissionGate(broker)("Edit", {}, opts(ac.signal));
    expect(r.behavior).toBe("deny");
    expect(broker.calls).toBe(0);
  });
  it("aborting WHILE awaiting the broker resolves to deny", async () => {
    const hanging: PermissionBroker = { request: () => new Promise(() => {}) }; // never resolves
    const ac = new AbortController();
    const p = createPermissionGate(hanging)("Edit", {}, opts(ac.signal));
    ac.abort();
    expect((await p).behavior).toBe("deny");
  });
});
