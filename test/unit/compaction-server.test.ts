import { describe, it, expect } from "vitest";
import { parseCompactOutcome, buildCompactTools, createCompactMcpServer, withCompactTool, COMPACT_TOOL } from "../../src/compaction/server.js";

function tools(holder: any) { const m: Record<string, any> = {}; for (const t of buildCompactTools(holder)) m[t.name] = t; return m; }

describe("parseCompactOutcome", () => {
  it("success: status compact_result + boundary tokens", () => {
    expect(parseCompactOutcome([
      { type: "system", subtype: "status", status: "compacting" },
      { type: "system", subtype: "compact_boundary", compact_metadata: { trigger: "manual", pre_tokens: 31590, post_tokens: 5664 } },
      { type: "system", subtype: "status", status: null, compact_result: "success" },
    ])).toEqual({ ok: true, result: "success", error: undefined, preTokens: 31590, postTokens: 5664 });
  });
  it("failed: status compact_result + error, no boundary", () => {
    expect(parseCompactOutcome([
      { type: "system", subtype: "status", status: null, compact_result: "failed", compact_error: "Not enough messages to compact." },
    ])).toEqual({ ok: false, result: "failed", error: "Not enough messages to compact.", preTokens: undefined, postTokens: undefined });
  });
  it("empty frames → ok false, nothing set", () => {
    expect(parseCompactOutcome([])).toEqual({ ok: false, result: undefined, error: undefined, preTokens: undefined, postTokens: undefined });
  });
});

describe("buildCompactTools", () => {
  it("exposes the RequestCompaction tool", () => { expect(Object.keys(tools({}))).toEqual(["RequestCompaction"]); });
  it("calls holder.request and returns the confirmation", async () => {
    let n = 0; const t = tools({ request: () => { n++; } });
    const res = await t.RequestCompaction.handler({}, {});
    expect(n).toBe(1);
    expect(res.content[0].text).toBe("compaction scheduled for the end of this turn");
  });
  it("is safe when holder.request is unset", async () => {
    const t = tools({});
    expect((await t.RequestCompaction.handler({}, {})).content[0].text).toBe("compaction scheduled for the end of this turn");
  });
});

describe("createCompactMcpServer", () => {
  it("returns an sdk server named cc-compact", () => {
    const srv: any = createCompactMcpServer({});
    expect(srv.type).toBe("sdk"); expect(srv.name).toBe("cc-compact");
  });
});

describe("withCompactTool", () => {
  it("merges server + allowed tool into empty options without mutating input", () => {
    const input: Record<string, unknown> = {};
    const out = withCompactTool(input, {});
    expect((out.mcpServers as any)["cc-compact"]).toBeTruthy();
    expect(out.allowedTools).toEqual([COMPACT_TOOL]);
    expect(input).toEqual({});
  });
  it("composes with existing servers/tools and dedupes", () => {
    const input: Record<string, unknown> = { mcpServers: { "cc-context": { type: "sdk" } }, allowedTools: ["x", COMPACT_TOOL] };
    const out = withCompactTool(input, {});
    expect(Object.keys(out.mcpServers as any).sort()).toEqual(["cc-compact", "cc-context"]);
    expect(out.allowedTools).toEqual(["x", COMPACT_TOOL]);
    expect((input.mcpServers as any)["cc-compact"]).toBeUndefined();
  });
  it("exports the exact tool id", () => { expect(COMPACT_TOOL).toBe("mcp__cc-compact__RequestCompaction"); });
});
