// test/unit/handlers.test.ts
import { describe, it, expect } from "vitest";
import { Peer } from "../../src/peer.js";
import { AppServer, toUsageTotals } from "../../src/handlers.js";
import type { OutcomeHolder } from "../../src/tools.js";
import type { OpenFn } from "../../src/handlers.js";

// A fake Session whose submit() streams one assistant message then resolves with a result string.
function fakeSession() {
  return {
    submit: async (_p: string, onMessage: (m: any) => void) => {
      onMessage({ type: "assistant", message: { content: [{ type: "text", text: "thinking" }] } });
      return { result: "final text" };
    },
    usage: async () => ({ input_tokens: 60, output_tokens: 40 }),
    dispose: async () => {},
  } as any;
}

function wire() {
  const out: any[] = [];
  const peer = new Peer((o) => out.push(o), (m, p, id) => server.handleRequest(m, p, id), () => {});
  const server = new AppServer(peer, { open: () => fakeSession() });
  return { out, peer };
}

describe("toUsageTotals", () => {
  it("sums the probe-32 nested model_usage, folding cache into input", () => {
    const u = { session: { model_usage: {
      "claude-opus-4-8": { inputTokens: 100, outputTokens: 40, cacheReadInputTokens: 200, cacheCreationInputTokens: 50 },
      "claude-haiku-4-5": { inputTokens: 10, outputTokens: 5, cacheReadInputTokens: 0, cacheCreationInputTokens: 0 },
    } } };
    expect(toUsageTotals(u)).toEqual({ inputTokens: 360, outputTokens: 45, totalTokens: 405 });
  });
  it("returns zeros for an empty/unknown shape (lenient, no throw)", () => {
    expect(toUsageTotals({})).toEqual({ inputTokens: 0, outputTokens: 0, totalTokens: 0 });
    expect(toUsageTotals(undefined)).toEqual({ inputTokens: 0, outputTokens: 0, totalTokens: 0 });
  });
});

describe("outcome propagation", () => {
  it("attaches a captured report_outcome to turn/completed.outcome", async () => {
    const out: any[] = [];
    const fakeOpen = (_cfg: any, holder: OutcomeHolder) => ({
      submit: async (prompt: string, onMessage: (m: any) => void) => {
        onMessage({ type: "assistant", message: { content: [{ type: "text", text: "working" }] } });
        if (prompt.includes("REPORT")) holder.outcome = { status: "done", reason: "ok" };  // the tool would do this
        return { result: "done" };
      },
      usage: async () => ({}), dispose: async () => {},
    } as any);
    let server!: AppServer;
    const peer = new Peer((o) => out.push(o), (m, p, id) => server.handleRequest(m, p, id), () => {});
    server = new AppServer(peer, { open: fakeOpen });
    peer.feed(JSON.stringify({ id: 1, method: "initialize", params: {} }) + "\n");
    peer.feed(JSON.stringify({ id: 2, method: "thread/start", params: { cwd: "/w" } }) + "\n");
    const threadId = out.find((o) => o.id === 2).result.thread.id;
    peer.feed(JSON.stringify({ id: 3, method: "turn/start", params: { threadId, input: [{ type: "text", text: "REPORT" }], cwd: "/w" } }) + "\n");
    await new Promise((r) => setTimeout(r, 10));
    const tc = out.find((o) => o.method === "turn/completed");
    expect(tc.params.outcome).toEqual({ status: "done", reason: "ok" });
  });

  it("turn/completed.outcome is absent when report_outcome was not called", async () => {
    const out: any[] = [];
    const fakeOpen = (_cfg: any, _holder: OutcomeHolder) => ({
      submit: async (_prompt: string, onMessage: (m: any) => void) => {
        onMessage({ type: "assistant", message: { content: [{ type: "text", text: "no outcome" }] } });
        return { result: "done" };
      },
      usage: async () => ({}), dispose: async () => {},
    } as any);
    let server!: AppServer;
    const peer = new Peer((o) => out.push(o), (m, p, id) => server.handleRequest(m, p, id), () => {});
    server = new AppServer(peer, { open: fakeOpen });
    peer.feed(JSON.stringify({ id: 1, method: "initialize", params: {} }) + "\n");
    peer.feed(JSON.stringify({ id: 2, method: "thread/start", params: { cwd: "/w" } }) + "\n");
    const threadId = out.find((o) => o.id === 2).result.thread.id;
    peer.feed(JSON.stringify({ id: 3, method: "turn/start", params: { threadId, input: [{ type: "text", text: "go" }], cwd: "/w" } }) + "\n");
    await new Promise((r) => setTimeout(r, 10));
    const tc = out.find((o) => o.method === "turn/completed");
    expect(tc.params.outcome).toBeUndefined();
  });
});

describe("posture wiring in handlers", () => {
  function captureOpen(capturedCfgs: any[]): OpenFn {
    return (cfg, _holder) => {
      capturedCfgs.push(cfg);
      return {
        submit: async (_p: string, onMsg: (m: any) => void) => { onMsg({ type: "assistant", message: { content: [{ type: "text", text: "ok" }] } }); return { result: "ok" }; },
        usage: async () => ({}), dispose: async () => {},
      } as any;
    };
  }

  it("autoReview:true -> open cfg permissionMode:'auto'", async () => {
    const cfgs: any[] = [];
    const out: any[] = [];
    let server!: AppServer;
    const peer = new Peer((o) => out.push(o), (m, p, id) => server.handleRequest(m, p, id), () => {});
    server = new AppServer(peer, { open: captureOpen(cfgs), autoReview: true });
    peer.feed(JSON.stringify({ id: 1, method: "thread/start", params: { cwd: "/w", approvalPolicy: "on-request" } }) + "\n");
    expect(cfgs[0]?.permissionMode).toBe("auto");
  });

  it("on-request + no autoReview -> open cfg permissionMode:'default'", async () => {
    const cfgs: any[] = [];
    const out: any[] = [];
    let server!: AppServer;
    const peer = new Peer((o) => out.push(o), (m, p, id) => server.handleRequest(m, p, id), () => {});
    server = new AppServer(peer, { open: captureOpen(cfgs), autoReview: false });
    peer.feed(JSON.stringify({ id: 1, method: "thread/start", params: { cwd: "/w", approvalPolicy: "on-request" } }) + "\n");
    expect(cfgs[0]?.permissionMode).toBe("default");
  });

  it("on-request + no autoReview -> open cfg has permissionBroker set", async () => {
    const cfgs: any[] = [];
    const out: any[] = [];
    let server!: AppServer;
    const peer = new Peer((o) => out.push(o), (m, p, id) => server.handleRequest(m, p, id), () => {});
    server = new AppServer(peer, { open: captureOpen(cfgs), autoReview: false });
    peer.feed(JSON.stringify({ id: 1, method: "thread/start", params: { cwd: "/w", approvalPolicy: "on-request" } }) + "\n");
    expect(cfgs[0]?.permissionBroker).toBeDefined();
  });

  it("autoReview:true -> open cfg does NOT have permissionBroker", async () => {
    const cfgs: any[] = [];
    const out: any[] = [];
    let server!: AppServer;
    const peer = new Peer((o) => out.push(o), (m, p, id) => server.handleRequest(m, p, id), () => {});
    server = new AppServer(peer, { open: captureOpen(cfgs), autoReview: true });
    peer.feed(JSON.stringify({ id: 1, method: "thread/start", params: { cwd: "/w", approvalPolicy: "on-request" } }) + "\n");
    expect(cfgs[0]?.permissionBroker).toBeUndefined();
  });
});

describe("AppServer happy path", () => {
  it("initialize advertises the outcome capability", () => {
    const { out, peer } = wire();
    peer.feed(JSON.stringify({ id: 1, method: "initialize", params: { capabilities: {} } }) + "\n");
    expect(out[0]).toMatchObject({ id: 1, result: { capabilities: { outcomeOnTurnCompleted: true } } });
  });
  it("thread/start returns {thread:{id}} and turn/start streams to a MANDATORY final_answer + turn/completed", async () => {
    const { out, peer } = wire();
    peer.feed(JSON.stringify({ id: 1, method: "initialize", params: {} }) + "\n");
    peer.feed(JSON.stringify({ method: "initialized", params: {} }) + "\n");
    peer.feed(JSON.stringify({ id: 2, method: "thread/start", params: { cwd: "/w" } }) + "\n");
    const tsResp = out.find((o) => o.id === 2);
    const threadId = tsResp.result.thread.id;
    expect(typeof threadId).toBe("string");
    peer.feed(JSON.stringify({ id: 3, method: "turn/start", params: { threadId, input: [{ type: "text", text: "go" }], cwd: "/w" } }) + "\n");
    await new Promise((r) => setTimeout(r, 10));               // let the async turn drain
    const turnResp = out.find((o) => o.id === 3);
    expect(turnResp.result.turn.id).toBeDefined();
    const methods = out.filter((o) => o.method).map((o) => o.method);
    expect(methods).toContain("turn/started");
    const finalAnswer = out.find((o) => o.method === "item/completed" && o.params?.item?.phase === "final_answer");
    expect(finalAnswer.params.item.text).toBe("final text");
    expect(methods).toContain("turn/completed");
  });
});
