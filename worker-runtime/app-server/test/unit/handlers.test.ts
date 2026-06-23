// test/unit/handlers.test.ts
import { describe, it, expect } from "vitest";
import { Peer } from "../../src/peer.js";
import { AppServer, toUsageTotals } from "../../src/handlers.js";
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

describe("sandbox wiring (threadStart)", () => {
  function captureCfg(deps: { autoReview?: boolean; network?: boolean }) {
    let captured: any;
    const peer = new Peer((_o) => {}, (m, p, id) => server.handleRequest(m, p, id), () => {});
    const server = new AppServer(peer, { ...deps, open: (cfg) => { captured = cfg; return fakeSession(); } });
    return { peer, server, cfg: () => captured };
  }

  it("translates a workspace-write posture into cfg.sandbox + credential deny settings", () => {
    const h = captureCfg({ autoReview: true, network: true });
    h.server.handleRequest("thread/start", { cwd: "/tmp/ws", sandbox: "workspace-write" }, 1);
    expect(h.cfg().sandbox).toMatchObject({
      enabled: true, autoAllowBashIfSandboxed: true, excludedCommands: ["gh *", "docker *"],
      network: { allowedDomains: expect.arrayContaining(["github.com"]) },
    });
    expect(h.cfg().settings).toEqual({ permissions: { deny: expect.any(Array) } });
  });

  it("danger-full-access leaves the worker unsandboxed (no cfg.sandbox/settings)", () => {
    const h = captureCfg({ autoReview: true, network: true });
    h.server.handleRequest("thread/start", { cwd: "/tmp/ws", sandbox: "danger-full-access" }, 1);
    expect(h.cfg().sandbox).toBeUndefined();
    expect(h.cfg().settings).toBeUndefined();
  });
});

describe("dynamic tool brokering", () => {
  it("relays a dynamic-tool call to the client via item/tool/call and feeds the reply back to the agent", async () => {
    const out: any[] = [];
    // The session drives one broker call mid-turn and folds the reply into its final text.
    const openDrivesTool: OpenFn = (_cfg, ctx) => ({
      submit: async (_p: string, onMsg: (m: any) => void) => {
        onMsg({ type: "assistant", message: { content: [{ type: "text", text: "calling" }] } });
        const r = await ctx.broker!.call("linear_graphql", { query: "Q" });
        return { result: `got: ${(r.contentItems ?? []).map((c) => c?.text ?? "").join("")}` };
      },
      usage: async () => ({}), dispose: async () => {},
    } as any);
    let server!: AppServer;
    // The sink emulates the client: it answers any item/tool/call request with a fixed result.
    const peer: Peer = new Peer(
      (o: any) => { out.push(o); if (o.method === "item/tool/call") peer.feed(JSON.stringify({ id: o.id, result: { contentItems: [{ type: "inputText", text: "OK-42" }], success: true } }) + "\n"); },
      (m, p, id) => server.handleRequest(m, p, id),
      () => {},
    );
    server = new AppServer(peer, { open: openDrivesTool });
    const spec = { name: "linear_graphql", description: "d", inputSchema: { type: "object", required: ["query"], properties: { query: { type: "string" } } } };
    peer.feed(JSON.stringify({ id: 1, method: "thread/start", params: { cwd: "/w", dynamicTools: [spec] } }) + "\n");
    const threadId = out.find((o) => o.id === 1).result.thread.id;
    peer.feed(JSON.stringify({ id: 2, method: "turn/start", params: { threadId, input: [{ type: "text", text: "go" }], cwd: "/w" } }) + "\n");
    await new Promise((r) => setTimeout(r, 20));
    const call = out.find((o) => o.method === "item/tool/call");
    expect(call.params).toMatchObject({ tool: "linear_graphql", arguments: { query: "Q" }, threadId });
    expect(typeof call.params.callId).toBe("string");
    const fa = out.find((o) => o.method === "item/completed" && o.params?.item?.phase === "final_answer");
    expect(fa.params.item.text).toBe("got: OK-42");
    // documented lifecycle: item/started + item/completed for the dynamicToolCall item
    expect(out.some((o) => o.method === "item/started" && o.params?.item?.type === "dynamicToolCall")).toBe(true);
    expect(out.some((o) => o.method === "item/completed" && o.params?.item?.type === "dynamicToolCall" && o.params?.item?.success === true)).toBe(true);
  });

  it("does NOT register a broker server when no dynamicTools are advertised", async () => {
    const cfgs: any[] = [];
    const captureOpen: OpenFn = (cfg) => { cfgs.push(cfg); return fakeSession(); };
    let server!: AppServer;
    const peer = new Peer(() => {}, (m, p, id) => server.handleRequest(m, p, id), () => {});
    server = new AppServer(peer, { open: captureOpen });
    peer.feed(JSON.stringify({ id: 1, method: "thread/start", params: { cwd: "/w" } }) + "\n");
    expect(cfgs[0]?.mcpServers).toBeUndefined();
  });
});

describe("posture wiring in handlers", () => {
  function captureOpen(capturedCfgs: any[]): OpenFn {
    return (cfg) => {
      capturedCfgs.push(cfg);
      return {
        submit: async (_p: string, onMsg: (m: any) => void) => { onMsg({ type: "assistant", message: { content: [{ type: "text", text: "ok" }] } }); return { result: "ok" }; },
        usage: async () => ({}), dispose: async () => {},
      } as any;
    };
  }

  it("autoReview:true -> open cfg permissionMode:'auto'", async () => {
    const cfgs: any[] = [];
    let server!: AppServer;
    const peer = new Peer(() => {}, (m, p, id) => server.handleRequest(m, p, id), () => {});
    server = new AppServer(peer, { open: captureOpen(cfgs), autoReview: true });
    peer.feed(JSON.stringify({ id: 1, method: "thread/start", params: { cwd: "/w", approvalPolicy: "on-request" } }) + "\n");
    expect(cfgs[0]?.permissionMode).toBe("auto");
  });

  it("on-request + no autoReview -> open cfg permissionMode:'default'", async () => {
    const cfgs: any[] = [];
    let server!: AppServer;
    const peer = new Peer(() => {}, (m, p, id) => server.handleRequest(m, p, id), () => {});
    server = new AppServer(peer, { open: captureOpen(cfgs), autoReview: false });
    peer.feed(JSON.stringify({ id: 1, method: "thread/start", params: { cwd: "/w", approvalPolicy: "on-request" } }) + "\n");
    expect(cfgs[0]?.permissionMode).toBe("default");
  });

  it("on-request + no autoReview -> open cfg has permissionBroker set", async () => {
    const cfgs: any[] = [];
    let server!: AppServer;
    const peer = new Peer(() => {}, (m, p, id) => server.handleRequest(m, p, id), () => {});
    server = new AppServer(peer, { open: captureOpen(cfgs), autoReview: false });
    peer.feed(JSON.stringify({ id: 1, method: "thread/start", params: { cwd: "/w", approvalPolicy: "on-request" } }) + "\n");
    expect(cfgs[0]?.permissionBroker).toBeDefined();
  });

  it("autoReview:true -> open cfg does NOT have permissionBroker", async () => {
    const cfgs: any[] = [];
    let server!: AppServer;
    const peer = new Peer(() => {}, (m, p, id) => server.handleRequest(m, p, id), () => {});
    server = new AppServer(peer, { open: captureOpen(cfgs), autoReview: true });
    peer.feed(JSON.stringify({ id: 1, method: "thread/start", params: { cwd: "/w", approvalPolicy: "on-request" } }) + "\n");
    expect(cfgs[0]?.permissionBroker).toBeUndefined();
  });
});

describe("AppServer happy path", () => {
  it("initialize returns userAgent + platformOs (no Claude-specific capability)", () => {
    const { out, peer } = wire();
    peer.feed(JSON.stringify({ id: 1, method: "initialize", params: { capabilities: {} } }) + "\n");
    expect(out[0]).toMatchObject({ id: 1, result: { userAgent: "cc-codex-appserver" } });
    expect((out[0] as any).result.capabilities).toBeUndefined();
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
