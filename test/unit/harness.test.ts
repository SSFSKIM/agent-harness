import { describe, it, expect } from "vitest";
import { createHarness } from "../../src/harness.js";

function fakeQuery({ prompt, options }: any) {
  const q: any = (async function* () {
    yield { type: "system", subtype: "init", session_id: "s1", tools: ["Read"] };
    yield { type: "assistant", message: { content: [{ type: "text", text: "hi " + prompt }] } };
    yield { type: "result", subtype: "success", result: "done: " + prompt };
  })();
  q.__options = options;
  q.rewindFiles = async (id: string) => ({ restored: id });
  q.supportedCommands = async () => [{ name: "clear" }];
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
});
