import { describe, it, expect } from "vitest";
import { connectDaemon } from "../../src/daemon/connect.js";

describe("connectDaemon permission methods", () => {
  it("pendingPermissions sends the op and returns the pending array", async () => {
    const sent: any[] = [];
    const fake = async (_s: string, op: any) => { sent.push(op); return [{ ok: true, pending: [{ sessionId: "s", toolUseID: "t", toolName: "Edit", input: {}, createdAt: 0 }] }]; };
    const c = connectDaemon("/x", fake);
    expect(await c.pendingPermissions()).toEqual([{ sessionId: "s", toolUseID: "t", toolName: "Edit", input: {}, createdAt: 0 }]);
    expect(sent[0]).toEqual({ op: "pending_permissions" });
  });
  it("respondPermission sends toolUseID + decision and resolves on ok", async () => {
    const sent: any[] = [];
    const fake = async (_s: string, op: any) => { sent.push(op); return [{ ok: true }]; };
    await connectDaemon("/x", fake).respondPermission("tu", { kind: "allow_once" });
    expect(sent[0]).toEqual({ op: "permission_response", toolUseID: "tu", decision: { kind: "allow_once" } });
  });
  it("respondPermission throws when the daemon reports no pending request", async () => {
    const fake = async () => [{ ok: false, error: "no pending request" }];
    await expect(connectDaemon("/x", fake).respondPermission("gone", { kind: "deny" })).rejects.toThrow("no pending request");
  });
});
