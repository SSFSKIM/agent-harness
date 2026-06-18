import { describe, it, expect } from "vitest";
import { connectDaemon } from "../../src/daemon/connect.js";

type Handler = (op: any, onLine?: (o: any) => void) => any[];
function fakeRequest(handlers: Record<string, Handler>) {
  const calls: any[] = [];
  const fn = async (_sock: string, op: any, onLine?: (o: any) => void) => {
    calls.push(op);
    const h = handlers[op.op];
    return h ? h(op, onLine) : [{ ok: false, error: `no handler for ${op.op}` }];
  };
  return Object.assign(fn, { calls });
}

describe("connectDaemon (DI transport)", () => {
  it("list() sends {op:list} and returns the sessions array", async () => {
    const req = fakeRequest({ list: () => [{ ok: true, sessions: [{ id: "a" }] }] });
    const c = connectDaemon("sock", req);
    expect(await c.list()).toEqual([{ id: "a" }]);
    expect(req.calls[0]).toEqual({ op: "list" });
  });

  it("submit() forwards chunk messages to onChunk and resolves with the done result", async () => {
    const req = fakeRequest({
      submit: (_op, onLine) => {
        const lines = [{ type: "chunk", message: { n: 1 } }, { type: "chunk", message: { n: 2 } }, { type: "done", result: "R" }];
        for (const l of lines) onLine?.(l);
        return lines;
      },
    });
    const c = connectDaemon("sock", req);
    const seen: unknown[] = [];
    const r = await c.submit("id1", "hi", (m) => seen.push(m));
    expect(seen).toEqual([{ n: 1 }, { n: 2 }]);
    expect(r.result).toBe("R");
    expect(req.calls[0]).toEqual({ op: "submit", id: "id1", prompt: "hi" });
  });

  it("control() returns the raw ControlResponse (does NOT throw on ok:false)", async () => {
    const req = fakeRequest({ control: () => [{ ok: false, error: "boom" }] });
    const c = connectDaemon("sock", req);
    expect(await c.control("id1", { type: "interrupt" })).toEqual({ ok: false, error: "boom" });
  });

  it("contextUsage() unwraps usage and throws on ok:false", async () => {
    const ok = connectDaemon("sock", fakeRequest({ control: () => [{ ok: true, usage: { totalTokens: 5 } }] }));
    expect(await ok.contextUsage("id1")).toEqual({ totalTokens: 5 });
    const bad = connectDaemon("sock", fakeRequest({ control: () => [{ ok: false, error: "no usage" }] }));
    await expect(bad.contextUsage("id1")).rejects.toThrow("no usage");
  });

  it("spawn/compact/fork/stop/startProactive/stopProactive map ops and throw on ok:false", async () => {
    const c = connectDaemon("sock", fakeRequest({
      spawn: (op) => [{ ok: true, id: `s-${op.model ?? "d"}` }],
      compact: () => [{ ok: true, outcome: { compacted: true } }],
      fork: () => [{ ok: true, id: "fk", sessionId: "sid" }],
      stop: () => [{ ok: true }],
      start_proactive: () => [{ ok: true, status: { state: "running", tickCount: 0, idleCount: 0, errorCount: 0 } }],
      stop_proactive: () => [{ ok: true }],
    }));
    expect(await c.spawn({ model: "opus" })).toBe("s-opus");
    expect(await c.compact("id1")).toEqual({ compacted: true });
    expect(await c.fork("id1")).toEqual({ id: "fk", sessionId: "sid" });
    await expect(c.stop("id1")).resolves.toBeUndefined();
    expect((await c.startProactive("id1")).state).toBe("running");
    await expect(c.stopProactive("id1")).resolves.toBeUndefined();
    const fail = connectDaemon("sock", fakeRequest({ spawn: () => [{ ok: false, error: "nope" }] }));
    await expect(fail.spawn()).rejects.toThrow("nope");
  });
});

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DaemonSupervisor } from "../../src/daemon/supervisor.js";
import { DaemonServer } from "../../src/daemon/server.js";
import { daemonRequest } from "../../src/daemon/client.js";

const tmp = () => mkdtempSync(join(tmpdir(), "cc-daemon-"));
// a fake SDK query exposing setModel + getContextUsage so control round-trips return { ok:true } / a payload
function ctlQuery({ prompt }: any) {
  const gen: any = (async function* () {
    for await (const t of prompt) {
      yield { type: "system", subtype: "init", session_id: "sdk-1" };
      yield { type: "assistant", message: { content: [{ type: "text", text: "ack" }] } };
      yield { type: "result", result: "did:" + t.message.content };
    }
  })();
  gen.setModel = async () => {};
  gen.getContextUsage = async () => ({ totalTokens: 1000, maxTokens: 5000 });
  return gen;
}

describe("connectDaemon over a real UDS", () => {
  it("round-trips spawn → submit (streamed) → control(set_model) → contextUsage", async () => {
    const d = tmp(); const sock = join(d, "sock");
    const sup = new DaemonSupervisor({ query: ctlQuery }, { dir: join(d, "sessions") });
    const server = new DaemonServer(sup, sock);
    await server.listen();
    const { connectDaemon } = await import("../../src/daemon/connect.js");
    const c = connectDaemon(sock);

    const id = await c.spawn({ model: "opus-4.8" });
    const chunks: unknown[] = [];
    const r = await c.submit(id, "hi", (m) => chunks.push(m));
    expect(r.result).toBe("did:hi");
    expect(chunks.length).toBeGreaterThan(0);

    const res = await c.control(id, { type: "set_model", model: "x" });
    expect(res.ok).toBe(true);
    expect(await c.contextUsage(id)).toEqual({ totalTokens: 1000, maxTokens: 5000 });

    await daemonRequest(sock, { op: "shutdown" });
    await server.closed;
  });
});
