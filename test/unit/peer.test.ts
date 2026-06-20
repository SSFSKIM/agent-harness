// test/unit/peer.test.ts
import { describe, it, expect, vi } from "vitest";
import { Peer } from "../../src/peer.js";

function harness() {
  const out: any[] = [];
  const reqs: any[] = []; const notes: any[] = [];
  const peer = new Peer((o) => out.push(o), (m, p, id) => reqs.push({ m, p, id }), (m, p) => notes.push({ m, p }));
  return { out, reqs, notes, peer };
}

describe("Peer", () => {
  it("frames split chunks and dispatches a request", () => {
    const h = harness();
    h.peer.feed('{"id":1,"method":"thread/st');
    h.peer.feed('art","params":{"cwd":"/w"}}\n');
    expect(h.reqs).toEqual([{ m: "thread/start", p: { cwd: "/w" }, id: 1 }]);
  });
  it("dispatches a notification (no id)", () => {
    const h = harness();
    h.peer.feed('{"method":"initialized","params":{}}\n');
    expect(h.notes).toEqual([{ m: "initialized", p: {} }]);
  });
  it("correlates a response to an outgoing request", async () => {
    const h = harness();
    const p = h.peer.request("item/commandExecution/requestApproval", { command: ["ls"] });
    const sent = h.out.find((o) => o.method);                 // the outgoing request
    expect(sent.id).toBeDefined();
    h.peer.feed(JSON.stringify({ id: sent.id, result: { decision: "accept" } }) + "\n");
    expect(await p).toEqual({ id: sent.id, result: { decision: "accept" } });
  });
  it("reply/notify emit jsonrpc-lite objects (no jsonrpc field)", () => {
    const h = harness();
    h.peer.reply(7, { thread: { id: "thr_1" } });
    h.peer.notify("turn/completed", { turn: { id: "turn_1", status: "completed" } });
    expect(h.out[0]).toEqual({ id: 7, result: { thread: { id: "thr_1" } } });
    expect(h.out[1]).toEqual({ method: "turn/completed", params: { turn: { id: "turn_1", status: "completed" } } });
    expect("jsonrpc" in h.out[0]).toBe(false);
    h.peer.replyError(3, -32601, "not found");
    expect(h.out[2]).toEqual({ id: 3, error: { code: -32601, message: "not found" } });
    expect("jsonrpc" in h.out[2]).toBe(false);
  });

  it("skips a malformed line (logs to console.error) and keeps processing", () => {
    const h = harness();
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    h.peer.feed("{not json}\n");
    h.peer.feed('{"method":"turn/started","params":{}}\n');
    expect(spy).toHaveBeenCalled();
    expect(h.notes).toEqual([{ m: "turn/started", p: {} }]);
    spy.mockRestore();
  });
});
