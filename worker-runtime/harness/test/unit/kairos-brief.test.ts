import { describe, it, expect } from "vitest";
import { buildBriefTools, createBriefMcpServer, stdoutBriefSink } from "../../src/kairos/brief.js";

function tools(sink: any) { const m: Record<string, any> = {}; for (const t of buildBriefTools(sink)) m[t.name] = t; return m; }

describe("brief channel", () => {
  it("exposes the SendUserMessage tool", () => {
    expect(Object.keys(tools({ write() {} }))).toEqual(["SendUserMessage"]);
  });
  it("createBriefMcpServer returns an sdk server named cc-brief", () => {
    const srv: any = createBriefMcpServer({ write() {} });
    expect(srv.type).toBe("sdk");
    expect(srv.name).toBe("cc-brief");
  });
  it("routes message to the sink with default status normal", async () => {
    const msgs: any[] = [];
    const t = tools({ write: (m: any) => { msgs.push(m); } });
    const res = await t.SendUserMessage.handler({ message: "hi" }, {});
    expect(msgs).toEqual([{ text: "hi", status: "normal" }]);
    expect(res.content[0].text).toBe("delivered");
  });
  it("passes through proactive status", async () => {
    const msgs: any[] = [];
    const t = tools({ write: (m: any) => { msgs.push(m); } });
    await t.SendUserMessage.handler({ message: "u", status: "proactive" }, {});
    expect(msgs[0].status).toBe("proactive");
  });
  it("ships a default stdout sink", () => { expect(typeof stdoutBriefSink.write).toBe("function"); });
});
