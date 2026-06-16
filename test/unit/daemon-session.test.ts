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
});
