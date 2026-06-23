import { describe, it, expect } from "vitest";
import { TurnTranslator, extractAssistantText } from "../../src/translator.js";

const asst = (text: string) => ({ type: "assistant", message: { content: [{ type: "text", text }] } });

describe("extractAssistantText", () => {
  it("pulls text blocks, ignores tool_use", () => {
    expect(extractAssistantText(asst("hi"))).toBe("hi");
    expect(extractAssistantText({ type: "assistant", message: { content: [{ type: "tool_use", name: "Bash" }] } })).toBe("");
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
});
