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

// records every turn's content; the "/compact" turn emits status+boundary then a result.
function compactQuery(seen: string[]) {
  return ({ prompt }: any) => (async function* () {
    for await (const t of prompt) {
      const text = t.message.content; seen.push(text);
      if (text === "/compact") {
        yield { type: "system", subtype: "status", status: "compacting" };
        yield { type: "system", subtype: "compact_boundary", compact_metadata: { trigger: "manual", pre_tokens: 1000, post_tokens: 200 } };
        yield { type: "system", subtype: "status", status: null, compact_result: "success" };
        yield { type: "result", subtype: "success", result: "compacted" };
      } else yield { type: "result", subtype: "success", result: "did:" + text };
    }
  })();
}
function captureQuery2(sink: any[]) {
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
  it("compact() injects /compact and returns the parsed outcome", async () => {
    const seen: string[] = [];
    const s = new DaemonSession("s-c", { query: compactQuery(seen) }, {});
    const outcome = await s.compact();
    expect(outcome).toEqual({ ok: true, result: "success", error: undefined, preTokens: 1000, postTokens: 200 });
    expect(seen).toEqual(["/compact"]);
    await s.dispose();
  });
  it("requestCompaction fires exactly one /compact at the turn boundary; FIFO stays intact", async () => {
    const seen: string[] = [];
    const s = new DaemonSession("s-i", { query: compactQuery(seen) }, {});
    s.requestCompaction();                                  // tool sets intent before the turn
    const r1 = await s.submit("hello", () => {});
    expect(r1.result).toBe("did:hello");                   // human turn gets ITS OWN result, not "compacted"
    const r2 = await s.submit("world", () => {});
    expect(r2.result).toBe("did:world");                   // next human turn NOT mis-resolved by the /compact result
    await s.dispose();
    expect(seen).toEqual(["hello", "/compact", "world"]);  // exactly one /compact, ordered between the two human turns
  });
  it("contextTool + compactTool both merge their servers into the query options", async () => {
    const sink: any[] = [];
    const s = new DaemonSession("s-both", { query: captureQuery2(sink) }, {}, Date.now, { contextTool: true, compactTool: true });
    expect((sink[0].mcpServers as any)["cc-context"]).toBeTruthy();
    expect((sink[0].mcpServers as any)["cc-compact"]).toBeTruthy();
    expect(sink[0].allowedTools).toEqual(expect.arrayContaining(["mcp__cc-context__GetContextUsage", "mcp__cc-compact__RequestCompaction"]));
    await s.dispose();
  });
});
