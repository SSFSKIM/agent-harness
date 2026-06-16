import { describe, it, expect } from "vitest";
import { PlanApprovalBroker } from "../../src/swarm/planApproval.js";

const input = { plan: "# Plan\nDo the thing", planFilePath: "/tmp/p.md" };

describe("PlanApprovalBroker", () => {
  it("always escalates (never resolves immediately) and surfaces the plan text", () => {
    const esc: any[] = [];
    const b = new PlanApprovalBroker({ onEscalate: (name, plan, id) => esc.push({ name, plan, id }) });
    const p = b.requestApproval("w1", input);
    expect(esc).toHaveLength(1);
    expect(esc[0].name).toBe("w1");
    expect(esc[0].plan).toContain("Do the thing");
    expect(typeof esc[0].id).toBe("string");
    let settled = false;
    void p.then(() => { settled = true; });
    expect(settled).toBe(false); // parked until respond()
  });
  it("approve resolves to allow and echoes the FULL ExitPlanMode input", async () => {
    const ids: string[] = [];
    const approved: string[] = [];
    const b = new PlanApprovalBroker({ onEscalate: (n, p, id) => ids.push(id), onApprove: (n) => { approved.push(n); } });
    const p = b.requestApproval("w1", input);
    expect(await b.respond(ids[0], "approve")).toBe(true);
    expect(approved).toEqual(["w1"]);            // onApprove fired for the right teammate
    const r = await p;
    expect(r.behavior).toBe("allow");
    expect((r as any).updatedInput).toEqual(input); // full echo (SDK-required)
  });
  it("reject resolves to deny carrying the feedback", async () => {
    const ids: string[] = [];
    const b = new PlanApprovalBroker({ onEscalate: (n, p, id) => ids.push(id) });
    const p = b.requestApproval("w1", input);
    await b.respond(ids[0], "reject", "tighten scope");
    const r = await p;
    expect(r.behavior).toBe("deny");
    expect((r as any).message).toBe("tighten scope");
  });
  it("awaits onApprove BEFORE resolving (mode transition lands first)", async () => {
    const order: string[] = [];
    const ids: string[] = [];
    const b = new PlanApprovalBroker({
      onEscalate: (n, p, id) => ids.push(id),
      onApprove: async () => { await Promise.resolve(); order.push("setMode"); },
    });
    const p = b.requestApproval("w1", input).then(() => order.push("resolved"));
    await b.respond(ids[0], "approve");
    await p;
    expect(order).toEqual(["setMode", "resolved"]);
  });
  it("respond on an unknown id returns false and fires nothing", async () => {
    const approved: string[] = [];
    const b = new PlanApprovalBroker({ onApprove: (n) => { approved.push(n); } });
    expect(await b.respond("nope", "approve")).toBe(false);
    expect(approved).toEqual([]);
  });
  it("fires onRequest with the plan before escalating", () => {
    const seen: any[] = [];
    const b = new PlanApprovalBroker({ onRequest: (n, req) => seen.push({ n, plan: req.plan }) });
    b.requestApproval("w1", input);
    expect(seen).toEqual([{ n: "w1", plan: input.plan }]);
  });
});
