import { describe, it, expect } from "vitest";
import { DaemonSession } from "../../src/daemon/session.js";

function fakeQuery({ prompt }: any) {
  return (async function* () {
    for await (const turn of prompt) {
      const text = turn.message.content;
      yield { type: "assistant", message: { content: [{ type: "text", text: "ack:" + text }] } };
      yield { type: "result", subtype: "success", result: "did:" + text };
    }
  })();
}

function captureQuery(sink: any[]) {
  return ({ prompt, options }: any) => { sink.push(options); return (async function* () { for await (const t of prompt) yield { type: "result", result: "ok:" + t.message.content }; })(); };
}

describe("DaemonSession", () => {
  it("submit streams non-result messages then resolves with the turn result", async () => {
    const chunks: any[] = [];
    const s = new DaemonSession("sess-1", { query: fakeQuery }, {});
    const r = await s.submit("hello", (m) => chunks.push(m));
    expect(r.result).toBe("did:hello");
    expect(chunks.map((c: any) => c.type)).toEqual(["assistant"]); // result is NOT streamed as a chunk
    await s.dispose();
  });
  it("advances lastActiveAt off an injected clock as messages flow", async () => {
    let t = 100;
    const s = new DaemonSession("sess-1", { query: fakeQuery }, {}, () => t);
    expect(s.lastActiveAt).toBe(100);
    t = 250;
    await s.submit("x", () => {});
    expect(s.lastActiveAt).toBe(250);
    await s.dispose();
  });
  it("handles two sequential submits in FIFO order", async () => {
    const s = new DaemonSession("sess-1", { query: fakeQuery }, {});
    expect((await s.submit("a", () => {})).result).toBe("did:a");
    expect((await s.submit("b", () => {})).result).toBe("did:b");
    await s.dispose();
  });
  it("rejects submit once the session has ended (no silent hang)", async () => {
    const s = new DaemonSession("sess-1", { query: fakeQuery }, {});
    await s.submit("a", () => {});
    await s.dispose();                                  // query ends → ended = true
    await expect(s.submit("b", () => {})).rejects.toThrow(/not running/);
  });
  it("rejects an in-flight submit when disposed mid-turn (no fake success)", async () => {
    // a query that consumes the turn but never emits a result for it
    const fq = ({ prompt }: any) => (async function* () { for await (const t of prompt) { void t; } })();
    const s = new DaemonSession("sess-1", { query: fq }, {});
    const p = s.submit("x", () => {});
    await s.dispose();                                  // loop ends with the turn still pending
    await expect(p).rejects.toThrow(/disposed/);
  });
  it("exposes a public done promise that resolves when the query ends", async () => {
    const s = new DaemonSession("sess-1", { query: fakeQuery }, {});
    let ended = false;
    s.done.then(() => { ended = true; });
    await s.dispose();
    await Promise.resolve();          // flush the done.then microtask
    expect(ended).toBe(true);
  });
  it("dispose ends the underlying query", async () => {
    let ended = false;
    const fq = ({ prompt }: any) => (async function* () {
      try { for await (const t of prompt) { void t; yield { type: "result", result: "r" }; } } finally { ended = true; }
    })();
    const s = new DaemonSession("sess-1", { query: fq }, {});
    await s.submit("x", () => {});
    await s.dispose();
    expect(ended).toBe(true);
  });
  it("contextTool (5th ctor arg) merges the cc-context server + allowed tool into options", async () => {
    const sink: any[] = [];
    const s = new DaemonSession("s-ctx", { query: captureQuery(sink) }, {}, Date.now, { contextTool: true });
    expect((sink[0].mcpServers as any)["cc-context"]).toBeTruthy();
    expect(sink[0].allowedTools).toContain("mcp__cc-context__GetContextUsage");
    await s.dispose();
  });
  it("no contextTool → options reach the query untouched (no cc-context)", async () => {
    const sink: any[] = [];
    const s = new DaemonSession("s-plain", { query: captureQuery(sink) }, {});
    expect(sink[0].mcpServers).toBeUndefined();
    await s.dispose();
  });
});
