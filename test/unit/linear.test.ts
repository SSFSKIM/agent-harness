// test/unit/linear.test.ts
import { describe, it, expect } from "vitest";
import { buildLinearTools, LINEAR_TOOL_ID } from "../../src/linear.js";

const tools = (post: any) => buildLinearTools({ apiKey: "k", post })[0] as any;

describe("linear_graphql tool", () => {
  it("runs a read query and returns data", async () => {
    const t = tools(async () => ({ data: { viewer: { id: "u1" } } }));
    const r = await t.handler({ query: "query { viewer { id } }" }, {});
    expect(r.content[0].text).toContain("u1");
  });
  it("refuses a destructive mutation before POST", async () => {
    let called = false;
    const t = tools(async () => { called = true; return {}; });
    const r = await t.handler({ query: "mutation { issueDelete(id: 1) { success } }" }, {});
    expect(called).toBe(false);
    expect(r.content[0].text).toMatch(/guardrail|refus|block/i);
  });
  it("surfaces a GraphQL errors array as a failure", async () => {
    const t = tools(async () => ({ errors: [{ message: "bad" }] }));
    const r = await t.handler({ query: "query { x }" }, {});
    expect(r.content[0].text).toMatch(/error/i);
  });
  it("allows a forward-only mutation (issueCreate) and POSTs it", async () => {
    let called = false;
    const t = tools(async () => { called = true; return { data: { issueCreate: { success: true } } }; });
    const r = await t.handler({ query: "mutation { issueCreate(input: { title: \"x\" }) { success } }" }, {});
    expect(called).toBe(true);
    expect(r.content[0].text).toContain("success");
  });
  it("guardrail closes the leading-comment bypass", async () => {
    let called = false;
    const t = tools(async () => { called = true; return { data: {} }; });
    const r = await t.handler({ query: "# innocuous\nmutation { issueDelete(id: 1) { success } }" }, {});
    expect(called).toBe(false);
    expect(r.content[0].text).toMatch(/guardrail|refus/i);
  });
  it("guardrail closes the multi-operation bypass", async () => {
    let called = false;
    const t = tools(async () => { called = true; return { data: {} }; });
    const r = await t.handler({ query: "query Read { viewer { id } }\nmutation Bad { issueDelete(id: 1) { success } }" }, {});
    expect(called).toBe(false);
    expect(r.content[0].text).toMatch(/guardrail|refus/i);
  });
  it("a read whose string literal mentions 'delete' is NOT a false positive", async () => {
    let called = false;
    const t = tools(async () => { called = true; return { data: { x: 1 } }; });
    await t.handler({ query: "query { search(term: \"please delete this\") { id } }" }, {});
    expect(called).toBe(true);  // a pure read still POSTs
  });
});

describe("withLinear", () => {
  it("includes LINEAR_TOOL_ID in allowedTools", async () => {
    const { withLinear } = await import("../../src/linear.js");
    const cfg = withLinear({ allowedTools: ["other"] }, "test-key");
    expect(cfg.allowedTools).toContain(LINEAR_TOOL_ID);
  });
});

describe("handlers LINEAR_API_KEY wiring", () => {
  it("with LINEAR_API_KEY set, open cfg allowedTools includes LINEAR_TOOL_ID", async () => {
    const prev = process.env.LINEAR_API_KEY;
    process.env.LINEAR_API_KEY = "lin_test_key";
    try {
      const { LINEAR_TOOL_ID: ID } = await import("../../src/linear.js");
      const cfgs: any[] = [];
      const { Peer } = await import("../../src/peer.js");
      const { AppServer } = await import("../../src/handlers.js");
      let server!: InstanceType<typeof AppServer>;
      const peer = new Peer(
        () => {},
        (m, p, id) => server.handleRequest(m, p, id),
        () => {},
      );
      server = new AppServer(peer, {
        open: (cfg) => {
          cfgs.push(cfg);
          return { submit: async () => ({ result: "" }), usage: async () => ({}), dispose: async () => {} } as any;
        },
      });
      peer.feed(JSON.stringify({ id: 1, method: "thread/start", params: { cwd: "/w" } }) + "\n");
      expect(cfgs[0]?.allowedTools).toContain(ID);
    } finally {
      if (prev === undefined) delete process.env.LINEAR_API_KEY;
      else process.env.LINEAR_API_KEY = prev;
    }
  });

  it("without LINEAR_API_KEY, open cfg allowedTools does NOT include LINEAR_TOOL_ID", async () => {
    const prev = process.env.LINEAR_API_KEY;
    delete process.env.LINEAR_API_KEY;
    try {
      const { LINEAR_TOOL_ID: ID } = await import("../../src/linear.js");
      const cfgs: any[] = [];
      const { Peer } = await import("../../src/peer.js");
      const { AppServer } = await import("../../src/handlers.js");
      let server!: InstanceType<typeof AppServer>;
      const peer = new Peer(
        () => {},
        (m, p, id) => server.handleRequest(m, p, id),
        () => {},
      );
      server = new AppServer(peer, {
        open: (cfg) => {
          cfgs.push(cfg);
          return { submit: async () => ({ result: "" }), usage: async () => ({}), dispose: async () => {} } as any;
        },
      });
      peer.feed(JSON.stringify({ id: 1, method: "thread/start", params: { cwd: "/w" } }) + "\n");
      expect(cfgs[0]?.allowedTools ?? []).not.toContain(ID);
    } finally {
      if (prev !== undefined) process.env.LINEAR_API_KEY = prev;
    }
  });
});
