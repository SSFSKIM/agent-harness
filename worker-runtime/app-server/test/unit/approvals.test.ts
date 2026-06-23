// test/unit/approvals.test.ts
import { describe, it, expect } from "vitest";
import { Peer } from "../../src/peer.js";
import { AppServerBroker } from "../../src/approvals.js";

function setup() {
  const out: any[] = [];
  const peer = new Peer((o) => out.push(o), () => {}, () => {});
  const broker = new AppServerBroker(peer, { threadId: "thr_1", turnId: () => "turn_1" });
  return { out, peer, broker };
}
const sig = { aborted: false, addEventListener() {} } as any;

describe("AppServerBroker", () => {
  it("Bash -> commandExecution approval; accept -> allow_once", async () => {
    const { out, peer, broker } = setup();
    const p = broker.request({ toolName: "Bash", input: { command: "ls", cwd: "/w" }, toolUseID: "t1", signal: sig });
    const sent = out.find((o) => o.method === "item/commandExecution/requestApproval");
    expect(sent.params).toMatchObject({ command: "ls", cwd: "/w", threadId: "thr_1", turnId: "turn_1", availableDecisions: ["accept", "acceptForSession", "decline"] });
    peer.feed(JSON.stringify({ id: sent.id, result: { decision: "accept" } }) + "\n");
    expect(await p).toEqual({ kind: "allow_once" });
  });
  it("Edit -> fileChange approval; acceptForSession -> allow_always; decline -> deny", async () => {
    const { out, peer, broker } = setup();
    const p1 = broker.request({ toolName: "Edit", input: { file_path: "/w/a.ts" }, toolUseID: "t2", signal: sig });
    const s1 = out.find((o) => o.method === "item/fileChange/requestApproval");
    expect(s1.params.changes).toBeDefined();
    peer.feed(JSON.stringify({ id: s1.id, result: { decision: "acceptForSession" } }) + "\n");
    expect(await p1).toEqual({ kind: "allow_always" });
    const p2 = broker.request({ toolName: "Bash", input: { command: "rm -rf /" }, toolUseID: "t3", signal: sig });
    const s2 = out.filter((o) => o.method === "item/commandExecution/requestApproval").pop();
    peer.feed(JSON.stringify({ id: s2.id, result: { decision: "decline" } }) + "\n");
    expect(await p2).toEqual({ kind: "deny" });
  });
});
