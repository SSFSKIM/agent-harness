import { describe, it, expect } from "vitest";
import {
  summarizeUsage, buildContextTools, createContextMcpServer, withContextTool, CONTEXT_TOOL,
} from "../../src/context/server.js";

function tools(holder: any) { const m: Record<string, any> = {}; for (const t of buildContextTools(holder)) m[t.name] = t; return m; }

describe("summarizeUsage", () => {
  it("ok case: well under every threshold", () => {
    expect(summarizeUsage({ totalTokens: 40000, maxTokens: 200000 })).toEqual({
      percentUsed: 20, tokensUsed: 40000, maxTokens: 200000, tokensRemaining: 160000, status: "ok",
    });
  });
  it("approaching-limit via percentUsed >= 80", () => {
    expect(summarizeUsage({ totalTokens: 160000, maxTokens: 200000 }).status).toBe("approaching-limit");
  });
  it("approaching-limit via the autocompact trigger even when percentUsed < 80", () => {
    const s = summarizeUsage({ totalTokens: 167000, maxTokens: 1_000_000, autoCompactThreshold: 167000, isAutoCompactEnabled: true });
    expect(s.percentUsed).toBe(17);          // 16.7% rounded — well under 80
    expect(s.status).toBe("approaching-limit");
  });
  it("ok when autocompact is enabled but tokens are below the threshold", () => {
    expect(summarizeUsage({ totalTokens: 100000, maxTokens: 1_000_000, autoCompactThreshold: 167000, isAutoCompactEnabled: true }).status).toBe("ok");
  });
  it("maxTokens 0 → percentUsed 0, status ok (no divide-by-zero)", () => {
    expect(summarizeUsage({ totalTokens: 0, maxTokens: 0 })).toEqual({
      percentUsed: 0, tokensUsed: 0, maxTokens: 0, tokensRemaining: 0, status: "ok",
    });
  });
});

describe("buildContextTools", () => {
  it("exposes the GetContextUsage tool", () => {
    expect(Object.keys(tools({}))).toEqual(["GetContextUsage"]);
  });
  it("returns the summarized usage JSON from the holder's live query", async () => {
    const t = tools({ query: { getContextUsage: async () => ({ totalTokens: 26000, maxTokens: 200000 }) } });
    const res = await t.GetContextUsage.handler({}, {});
    expect(JSON.parse(res.content[0].text)).toEqual({
      percentUsed: 13, tokensUsed: 26000, maxTokens: 200000, tokensRemaining: 174000, status: "ok",
    });
  });
  it("returns 'context usage unavailable' when the holder has no query", async () => {
    const t = tools({});
    expect((await t.GetContextUsage.handler({}, {})).content[0].text).toBe("context usage unavailable");
  });
  it("returns 'context usage unavailable' when getContextUsage() throws", async () => {
    const t = tools({ query: { getContextUsage: async () => { throw new Error("boom"); } } });
    expect((await t.GetContextUsage.handler({}, {})).content[0].text).toBe("context usage unavailable");
  });
});

describe("createContextMcpServer", () => {
  it("returns an sdk server named cc-context", () => {
    const srv: any = createContextMcpServer({});
    expect(srv.type).toBe("sdk");
    expect(srv.name).toBe("cc-context");
  });
});

describe("withContextTool", () => {
  it("merges the server + allowed tool into empty options without mutating the input", () => {
    const input: Record<string, unknown> = {};
    const out = withContextTool(input, {});
    expect((out.mcpServers as any)["cc-context"]).toBeTruthy();
    expect(out.allowedTools).toEqual([CONTEXT_TOOL]);
    expect(input).toEqual({});                                  // input untouched
  });
  it("composes with existing mcpServers + allowedTools and dedupes", () => {
    const input: Record<string, unknown> = {
      mcpServers: { "cc-tasks": { type: "sdk" } },
      allowedTools: ["mcp__cc-tasks__TaskList", CONTEXT_TOOL],   // already present → must not duplicate
    };
    const out = withContextTool(input, {});
    expect(Object.keys(out.mcpServers as any).sort()).toEqual(["cc-context", "cc-tasks"]);
    expect(out.allowedTools).toEqual(["mcp__cc-tasks__TaskList", CONTEXT_TOOL]);
    expect((input.mcpServers as any)["cc-context"]).toBeUndefined(); // input untouched
  });
  it("exports the exact tool id", () => {
    expect(CONTEXT_TOOL).toBe("mcp__cc-context__GetContextUsage");
  });
});
