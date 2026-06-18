import { describe, it, expect } from "vitest";
import { openSession, resumeSession, Session } from "../../src/session/index.js";

function captureQuery(sink: any[]) {
  return ({ prompt, options }: any) => { sink.push(options); return (async function* () { for await (const t of prompt) yield { type: "result", result: "ok:" + t.message.content }; })(); };
}

describe("openSession / resumeSession", () => {
  it("openSession returns a Session and applies resolveOptions", async () => {
    const sink: any[] = [];
    const s = openSession({ model: "m" }, { query: captureQuery(sink) });
    expect(s).toBeInstanceOf(Session);
    await s.submit("x");
    expect(sink[0].model).toBe("m");
    expect(sink[0].settingSources).toBeDefined();   // proves resolveOptions ran (not a bare options object)
    await s.dispose();
  });
  it("contextTool/compactTool wire the servers but do NOT leak into resolveOptions output", async () => {
    const sink: any[] = [];
    const s = openSession({ contextTool: true, compactTool: true }, { query: captureQuery(sink) });
    await s.submit("x");
    expect((sink[0].mcpServers as any)["cc-context"]).toBeTruthy();
    expect((sink[0].mcpServers as any)["cc-compact"]).toBeTruthy();
    expect(sink[0].contextTool).toBeUndefined();
    expect(sink[0].compactTool).toBeUndefined();
    await s.dispose();
  });
  it("resumeSession sets options.resume to the given id", async () => {
    const sink: any[] = [];
    const s = resumeSession("sid-xyz", {}, { query: captureQuery(sink) });
    await s.submit("x");
    expect(sink[0].resume).toBe("sid-xyz");
    await s.dispose();
  });
  it("openSession rejects a malformed config with HarnessConfigError", async () => {
    const { openSession } = await import("../../src/session/index.js");
    const { HarnessConfigError } = await import("../../src/config/validate.js");
    expect(() => openSession({ maxTurns: 0 } as any)).toThrow(HarnessConfigError);
  });
});
