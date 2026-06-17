import { describe, it, expect } from "vitest";
import { Session } from "../../src/session/session.js";

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
// emits a system/init carrying session_id before each turn's result
function initQuery(ids: string[]) {
  return ({ prompt }: any) => (async function* () {
    let i = 0;
    for await (const t of prompt) {
      yield { type: "system", subtype: "init", session_id: ids[Math.min(i, ids.length - 1)] }; i++;
      yield { type: "result", subtype: "success", result: "did:" + t.message.content };
    }
  })();
}

describe("Session", () => {
  it("submit streams non-result messages then resolves with the turn result", async () => {
    const chunks: any[] = [];
    const s = new Session({ query: fakeQuery }, {});
    const r = await s.submit("hello", (m) => chunks.push(m));
    expect(r.result).toBe("did:hello");
    expect(chunks.map((c: any) => c.type)).toEqual(["assistant"]);
    await s.dispose();
  });
  it("submit defaults onMessage to a no-op (callable with just a prompt)", async () => {
    const s = new Session({ query: fakeQuery }, {});
    expect((await s.submit("x")).result).toBe("did:x");
    await s.dispose();
  });
  it("advances lastActiveAt off an injected clock", async () => {
    let t = 100;
    const s = new Session({ query: fakeQuery }, {}, { now: () => t });
    expect(s.lastActiveAt).toBe(100);
    t = 250;
    await s.submit("x");
    expect(s.lastActiveAt).toBe(250);
    await s.dispose();
  });
  it("handles two sequential submits in FIFO order", async () => {
    const s = new Session({ query: fakeQuery }, {});
    expect((await s.submit("a")).result).toBe("did:a");
    expect((await s.submit("b")).result).toBe("did:b");
    await s.dispose();
  });
  it("rejects submit once ended, using the label in the message", async () => {
    const s = new Session({ query: fakeQuery }, {}, { label: "lib-sess" });
    await s.submit("a");
    await s.dispose();
    await expect(s.submit("b")).rejects.toThrow(/lib-sess is not running/);
  });
  it("rejects an in-flight submit when disposed mid-turn", async () => {
    const fq = ({ prompt }: any) => (async function* () { for await (const t of prompt) { void t; } })();
    const s = new Session({ query: fq }, {});
    const p = s.submit("x");
    await s.dispose();
    await expect(p).rejects.toThrow(/disposed/);
  });
  it("exposes a done promise that resolves when the query ends", async () => {
    const s = new Session({ query: fakeQuery }, {});
    let ended = false;
    s.done.then(() => { ended = true; });
    await s.dispose();
    await Promise.resolve();
    expect(ended).toBe(true);
  });
  it("captures session_id from the first init frame; undefined before the first turn", async () => {
    const s = new Session({ query: initQuery(["sid-A"]) }, {});
    expect(s.sessionId).toBeUndefined();
    await s.submit("hi");
    expect(s.sessionId).toBe("sid-A");
    await s.dispose();
  });
  it("captures session_id ONCE and keeps the first id across turns", async () => {
    const s = new Session({ query: initQuery(["sid-1", "sid-2"]) }, {});
    await s.submit("a");
    await s.submit("b");
    expect(s.sessionId).toBe("sid-1");
    await s.dispose();
  });
  it("contextTool wires cc-context into the query options", async () => {
    const sink: any[] = [];
    const s = new Session({ query: captureQuery(sink) }, {}, { contextTool: true });
    expect((sink[0].mcpServers as any)["cc-context"]).toBeTruthy();
    expect(sink[0].allowedTools).toContain("mcp__cc-context__GetContextUsage");
    await s.dispose();
  });
  it("no tools → options reach the query untouched", async () => {
    const sink: any[] = [];
    const s = new Session({ query: captureQuery(sink) }, {});
    expect(sink[0].mcpServers).toBeUndefined();
    await s.dispose();
  });
  it("contextTool + compactTool both merge their servers", async () => {
    const sink: any[] = [];
    const s = new Session({ query: captureQuery(sink) }, {}, { contextTool: true, compactTool: true });
    expect((sink[0].mcpServers as any)["cc-context"]).toBeTruthy();
    expect((sink[0].mcpServers as any)["cc-compact"]).toBeTruthy();
    expect(sink[0].allowedTools).toEqual(expect.arrayContaining(["mcp__cc-context__GetContextUsage", "mcp__cc-compact__RequestCompaction"]));
    await s.dispose();
  });
  it("compact() injects /compact and returns the parsed outcome", async () => {
    const seen: string[] = [];
    const s = new Session({ query: compactQuery(seen) }, {});
    expect(await s.compact()).toEqual({ ok: true, result: "success", error: undefined, preTokens: 1000, postTokens: 200 });
    expect(seen).toEqual(["/compact"]);
    await s.dispose();
  });
  it("requestCompaction fires exactly one /compact at the turn boundary; FIFO intact", async () => {
    const seen: string[] = [];
    const s = new Session({ query: compactQuery(seen) }, {});
    s.requestCompaction();
    expect((await s.submit("hello")).result).toBe("did:hello");
    expect((await s.submit("world")).result).toBe("did:world");
    await s.dispose();
    expect(seen).toEqual(["hello", "/compact", "world"]);
  });
});
