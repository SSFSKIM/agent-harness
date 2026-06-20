// test/unit/tools.test.ts
import { describe, it, expect } from "vitest";
import { buildReportOutcomeTools, buildReportOutcomeServer, withReportOutcome, REPORT_OUTCOME_TOOL_ID } from "../../src/tools.js";

describe("report_outcome tool", () => {
  it("captures structured args into the holder and returns success", async () => {
    const holder: any = {};
    // Test the exported tools array directly (mirrors buildContextTools pattern)
    const tools = buildReportOutcomeTools(holder);
    const tool = tools.find((t: any) => t.name === "report_outcome");
    expect(tool).toBeDefined();
    const res = await (tool as any).handler({ status: "done", reason: "ok", pr_url: "http://x", unresolved_threads: 0 }, {});
    expect(holder.outcome).toMatchObject({ status: "done", reason: "ok", pr_url: "http://x", evidence: { unresolved_threads: 0 } });
    expect(res.content[0].text).toContain("recorded");
  });

  it("omits evidence key when no evidence fields are present", async () => {
    const holder: any = {};
    const tools = buildReportOutcomeTools(holder);
    const tool = tools.find((t: any) => t.name === "report_outcome") as any;
    await tool.handler({ status: "blocked", reason: "stuck" }, {});
    expect(holder.outcome.evidence).toBeUndefined();
    expect(holder.outcome.status).toBe("blocked");
  });

  it("withReportOutcome merges the server and allowlists the tool id", () => {
    const holder: any = {};
    const cfg = withReportOutcome({ allowedTools: ["X"] }, holder);
    expect(cfg.allowedTools).toContain(REPORT_OUTCOME_TOOL_ID);
    expect(cfg.mcpServers["cc-appserver"]).toBeDefined();
  });

  it("withReportOutcome does not mutate the original cfg", () => {
    const holder: any = {};
    const original = { allowedTools: ["X"] };
    withReportOutcome(original, holder);
    expect(original.allowedTools).toEqual(["X"]);
    expect((original as any).mcpServers).toBeUndefined();
  });

  it("buildReportOutcomeServer returns a defined server object", () => {
    const holder: any = {};
    const server = buildReportOutcomeServer(holder);
    expect(server).toBeDefined();
  });
});
