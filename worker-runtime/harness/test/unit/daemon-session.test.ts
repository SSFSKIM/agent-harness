import { describe, it, expect } from "vitest";
import { DaemonSession } from "../../src/daemon/session.js";

function fakeQuery({ prompt }: any) {
  return (async function* () { for await (const turn of prompt) yield { type: "result", subtype: "success", result: "did:" + turn.message.content }; })();
}
function captureQuery(sink: any[]) {
  return ({ prompt, options }: any) => { sink.push(options); return (async function* () { for await (const t of prompt) yield { type: "result", result: "ok:" + t.message.content }; })(); };
}

describe("DaemonSession (subclass of Session)", () => {
  it("exposes the daemon handle id", async () => {
    const s = new DaemonSession("sess-7", { query: fakeQuery }, {});
    expect(s.id).toBe("sess-7");
    await s.dispose();
  });
  it("inherits submit + dispose from Session", async () => {
    const s = new DaemonSession("sess-1", { query: fakeQuery }, {});
    expect((await s.submit("hi", () => {})).result).toBe("did:hi");
    await s.dispose();
  });
  it("threads the 5th-arg contextTool/compactTool through to the base", async () => {
    const sink: any[] = [];
    const s = new DaemonSession("s-both", { query: captureQuery(sink) }, {}, Date.now, { contextTool: true, compactTool: true });
    expect((sink[0].mcpServers as any)["cc-context"]).toBeTruthy();
    expect((sink[0].mcpServers as any)["cc-compact"]).toBeTruthy();
    expect(sink[0].allowedTools).toEqual(expect.arrayContaining(["mcp__cc-context__GetContextUsage", "mcp__cc-compact__RequestCompaction"]));
    await s.dispose();
  });
  it("uses the daemon id as the error label once ended", async () => {
    const s = new DaemonSession("sess-9", { query: fakeQuery }, {});
    await s.submit("a", () => {});
    await s.dispose();
    await expect(s.submit("b", () => {})).rejects.toThrow(/sess-9 is not running/);
  });
});
