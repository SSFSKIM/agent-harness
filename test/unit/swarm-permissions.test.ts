import { describe, it, expect } from "vitest";
import { PermissionBroker, DEFAULT_ALLOW } from "../../src/swarm/permissions.js";

describe("PermissionBroker", () => {
  it("allows read-only + cc-tasks tools by default, echoing updatedInput (SDK requires it)", async () => {
    const b = new PermissionBroker({});
    const r = await b.decide("w1", "Read", { file: "x" });
    expect(r.behavior).toBe("allow");
    expect((r as any).updatedInput).toEqual({ file: "x" }); // SDK rejects an allow without updatedInput
    expect((await b.decide("w1", "mcp__cc-tasks__TaskUpdate", {})).behavior).toBe("allow");
    expect(DEFAULT_ALLOW).toContain("Read");
  });
  it("denies non-allowlisted tools when escalation is off (default)", async () => {
    const r = await new PermissionBroker({}).decide("w1", "Bash", { command: "rm" });
    expect(r.behavior).toBe("deny");
  });
  it("escalates when enabled and resolves allow via respond()", async () => {
    const pushed: any[] = [];
    const b = new PermissionBroker({ escalate: true, onEscalate: (teammate, tool, input, id) => pushed.push({ teammate, tool, id }) });
    const p = b.decide("w1", "Bash", { command: "ls" });
    expect(pushed).toHaveLength(1);
    expect(b.respond(pushed[0].id, "allow")).toBe(true);
    expect((await p).behavior).toBe("allow");
  });
  it("escalation resolved as deny carries the message", async () => {
    const ids: string[] = [];
    const b = new PermissionBroker({ escalate: true, onEscalate: (t, tool, i, id) => ids.push(id) });
    const p = b.decide("w1", "Write", {});
    b.respond(ids[0], "deny", "no writes");
    const r = await p;
    expect(r.behavior).toBe("deny");
    expect((r as any).message).toBe("no writes");
  });
  it("respond() on an unknown id returns false", () => {
    expect(new PermissionBroker({}).respond("nope", "allow")).toBe(false);
  });
  it("fires the onRequest observer before deciding", async () => {
    const seen: any[] = [];
    const b = new PermissionBroker({ onRequest: (t, req) => seen.push({ t, tool: req.tool }) });
    await b.decide("w1", "Read", {});
    expect(seen).toEqual([{ t: "w1", tool: "Read" }]);
  });
});
