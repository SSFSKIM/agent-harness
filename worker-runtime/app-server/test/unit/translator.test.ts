import { describe, it, expect } from "vitest";
import { TurnTranslator, extractAssistantText, extractToolUses } from "../../src/translator.js";

const asst = (text: string) => ({ type: "assistant", message: { content: [{ type: "text", text }] } });
const toolUse = (name: string, input: unknown, id = "t1") =>
  ({ type: "assistant", message: { content: [{ type: "tool_use", id, name, input }] } });

describe("extractAssistantText", () => {
  it("pulls text blocks, ignores tool_use", () => {
    expect(extractAssistantText(asst("hi"))).toBe("hi");
    expect(extractAssistantText({ type: "assistant", message: { content: [{ type: "tool_use", name: "Bash" }] } })).toBe("");
  });
});

describe("extractToolUses", () => {
  it("pulls tool_use blocks {id,name,input}, ignores text", () => {
    expect(extractToolUses(toolUse("Bash", { command: "ls" }))).toEqual([{ id: "t1", name: "Bash", input: { command: "ls" } }]);
    expect(extractToolUses(asst("hi"))).toEqual([]);
    expect(extractToolUses({ type: "user", message: { content: [] } })).toEqual([]);
  });
});

describe("TurnTranslator", () => {
  it("streams commentary, then a MANDATORY final_answer + tokenUsage + turn/completed", () => {
    const t = new TurnTranslator("thr_1", "turn_1");
    const a = t.onMessage(asst("working on it"));     // held, not emitted yet
    expect(a).toEqual([]);
    const fin = t.finalize({ text: "all done", isError: false, usage: { totalTokens: 100, inputTokens: 60, outputTokens: 40 } });
    // held commentary (!= final) flushes, then final_answer, then usage, then turn/completed
    expect(fin[0]).toMatchObject({ method: "item/completed", params: { item: { type: "agentMessage", text: "working on it", phase: "commentary" } } });
    expect(fin[1]).toMatchObject({ method: "item/completed", params: { item: { type: "agentMessage", text: "all done", phase: "final_answer" } } });
    expect(fin[2]).toMatchObject({ method: "thread/tokenUsage/updated", params: { tokenUsage: { total: { totalTokens: 100, inputTokens: 60, outputTokens: 40 } } } });
    expect(fin[3]).toMatchObject({ method: "turn/completed", params: { turn: { id: "turn_1", status: "completed" } } });
  });
  it("suppresses a duplicate when the last commentary equals the final text", () => {
    const t = new TurnTranslator("thr_1", "turn_1");
    t.onMessage(asst("the answer"));
    const fin = t.finalize({ text: "the answer", isError: false });
    const phases = fin.filter((o: any) => o.method === "item/completed").map((o: any) => o.params.item.phase);
    expect(phases).toEqual(["final_answer"]);                  // no duplicate commentary
  });
  it("turn/completed carries no outcome field (report_outcome rides item/tool/call now)", () => {
    const t = new TurnTranslator("thr_1", "turn_1");
    const fin = t.finalize({ text: "done", isError: false });
    const tc: any = fin.find((o: any) => o.method === "turn/completed");
    expect(tc.params.outcome).toBeUndefined();
    expect(tc.params).toEqual({ turn: { id: "turn_1", status: "completed" } });
  });
  it("maps an errored result to turn/failed", () => {
    const t = new TurnTranslator("thr_1", "turn_1");
    const fin = t.finalize({ text: "", isError: true });
    expect(fin).toEqual([{ method: "turn/failed", params: { turn: { id: "turn_1", status: "failed" } } }]);
  });
  it("emits a tool call (item/completed type=toolCall) for a built-in SDK tool_use", () => {
    const t = new TurnTranslator("thr_1", "turn_1");
    const out = t.onMessage(toolUse("Bash", { command: "echo hi" })) as any[];
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ method: "item/completed",
      params: { item: { type: "toolCall", tool: "Bash", arguments: { command: "echo hi" } } } });
  });
  it("a text+tool_use message flushes prior held text, this text as commentary, then the tool", () => {
    const t = new TurnTranslator("thr_1", "turn_1");
    t.onMessage(asst("earlier"));                                   // held
    const msg = { type: "assistant", message: { content: [
      { type: "text", text: "I'll run it" }, { type: "tool_use", id: "t9", name: "Bash", input: { command: "ls" } }] } };
    const out = t.onMessage(msg) as any[];
    expect(out.map((o: any) => o.params.item.type)).toEqual(["agentMessage", "agentMessage", "toolCall"]);
    expect(out.map((o: any) => o.params.item.text ?? o.params.item.tool)).toEqual(["earlier", "I'll run it", "Bash"]);
    expect(out[1].params.item.phase).toBe("commentary");           // tool-bearing message text is never final
  });
  it("tokenUsage() emits the thread/tokenUsage/updated shape (the one contract reused by heartbeat + finalize)", () => {
    const t = new TurnTranslator("thr_1", "turn_1");
    expect(t.tokenUsage({ totalTokens: 9, inputTokens: 6, outputTokens: 3 })).toEqual({
      method: "thread/tokenUsage/updated",
      params: { threadId: "thr_1", turnId: "turn_1", tokenUsage: { total: { totalTokens: 9, inputTokens: 6, outputTokens: 3 } } },
    });
  });
});
