import { describe, it, expect } from "vitest";
import { createHarness, resumeHarness } from "../../src/harness.js";

function fakeQuery({ prompt, options }: any) {
  const q: any = (async function* () {
    yield { type: "system", subtype: "init", session_id: "s1", tools: ["Read"] };
    yield { type: "assistant", message: { content: [{ type: "text", text: "hi " + prompt }] } };
    yield { type: "result", subtype: "success", result: "done: " + prompt };
  })();
  q.__options = options;
  q.rewindFiles = async (id: string) => ({ restored: id });
  q.supportedCommands = async () => [{ name: "clear" }];
  q.getContextUsage = async () => ({ totalTokens: 42 });
  q.accountInfo = async () => ({ apiProvider: "anthropic" });
  q.usage_EXPERIMENTAL_MAY_CHANGE_DO_NOT_RELY_ON_THIS_API_YET = async () => ({ session: { total_cost_usd: 1 } });
  q.initializationResult = async () => ({ models: ["m"], account: { apiProvider: "anthropic" } });
  return q;
}

describe("createHarness", () => {
  it("builds CC-faithful options from config", () => {
    const h = createHarness({ outputStyle: "explanatory" }, { query: fakeQuery });
    expect((h.options as any).settingSources).toEqual(["user", "project", "local"]);
    expect((h.options as any).systemPrompt.append).toBeTruthy();
  });
  it("run() collects the stream into result + messages", async () => {
    const h = createHarness({}, { query: fakeQuery });
    const r = await h.run("ping");
    expect(r.result).toBe("done: ping");
    expect(r.messages.length).toBe(3);
    expect(r.sessionId).toBe("s1");
  });
  it("stream() yields each message", async () => {
    const h = createHarness({}, { query: fakeQuery });
    const types: string[] = [];
    for await (const m of h.stream("ping")) types.push((m as any).type);
    expect(types).toEqual(["system", "assistant", "result"]);
  });
  it("rewind() delegates to the active query", async () => {
    const h = createHarness({}, { query: fakeQuery });
    const it = h.stream("ping"); await it.next(); // start a query
    expect(await h.rewind("u1")).toEqual({ restored: "u1" });
  });
  it("resumeHarness sets options.resume to the given session id", () => {
    const h = resumeHarness("sess-xyz", {}, { query: fakeQuery });
    expect((h.options as any).resume).toBe("sess-xyz");
  });
  it("createHarness without resume leaves options.resume unset", () => {
    const h = createHarness({}, { query: fakeQuery });
    expect((h.options as any).resume).toBeUndefined();
  });
  it("getContextUsage()/accountInfo() delegate to the active query", async () => {
    const h = createHarness({}, { query: fakeQuery });
    const it = h.stream("ping"); await it.next(); // start a query
    expect(await h.getContextUsage()).toEqual({ totalTokens: 42 });
    expect(await h.accountInfo()).toEqual({ apiProvider: "anthropic" });
  });
  it("getContextUsage() throws before a query starts", async () => {
    const h = createHarness({}, { query: fakeQuery });
    await expect(h.getContextUsage()).rejects.toThrow(/start a query first/);
  });
  it("usage()/initializationResult() delegate to the active query", async () => {
    const h = createHarness({}, { query: fakeQuery });
    const it = h.stream("ping"); await it.next(); // start a query
    expect(await h.usage()).toEqual({ session: { total_cost_usd: 1 } });
    expect(await h.initializationResult()).toEqual({ models: ["m"], account: { apiProvider: "anthropic" } });
  });
  it("usage() throws before a query starts", async () => {
    const h = createHarness({}, { query: fakeQuery });
    await expect(h.usage()).rejects.toThrow(/start a query first/);
  });
  it("contextTool mounts the cc-context server and allowlists its tool", () => {
    const h = createHarness({ contextTool: true }, { query: fakeQuery });
    expect((h.options as any).mcpServers["cc-context"]).toBeTruthy();
    expect((h.options as any).allowedTools).toContain("mcp__cc-context__GetContextUsage");
  });
  it("without contextTool there is no cc-context server", () => {
    const h = createHarness({}, { query: fakeQuery });
    expect((h.options as any).mcpServers?.["cc-context"]).toBeUndefined();
  });
  it("createHarness rejects a malformed config with HarnessConfigError", async () => {
    const { createHarness } = await import("../../src/harness.js");
    const { HarnessConfigError } = await import("../../src/config/validate.js");
    expect(() => createHarness({ permissionMode: "bogus" as any })).toThrow(HarnessConfigError);
  });
  it("teardown: a control method before any run() throws cleanly (no hang)", async () => {
    const { createHarness } = await import("../../src/harness.js");
    const h = createHarness({}, { query: (() => (async function* () {})()) as any });
    await expect(h.getContextUsage()).rejects.toThrow(/start a query first/);
  });
  it("teardown: a stream can be abandoned early without hanging", async () => {
    const { createHarness } = await import("../../src/harness.js");
    const q = ({ prompt }: any) => (async function* () { for await (const t of prompt) { yield { type: "chunk", n: 1 }; yield { type: "result", result: "ok" }; } })();
    const h = createHarness({}, { query: q as any });
    for await (const _m of h.stream("hi")) break;          // abandon after the first frame
    expect(true).toBe(true);                                // reached here ⇒ no hang
  });
});
