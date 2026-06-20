import { describe, it, expect } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHarness } from "../../src/index.js";

const live = (process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_CODE_OAUTH_TOKEN) ? describe : describe.skip;
const MODEL = "claude-haiku-4-5-20251001";

live("live context introspection tool (real SDK)", () => {
  it("the model calls GetContextUsage and the tool returns a numeric percentUsed", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "cc-context-live-"));
    try {
      const h = createHarness({ model: MODEL, permissionMode: "auto", cwd, contextTool: true });
      let toolText: string | undefined;
      for await (const m of h.stream(
        "Call the GetContextUsage tool to check how full your context window is, then tell me the percentUsed value. Do not do anything else.",
      )) {
        const mm = m as any;
        // The cc-context tool result comes back as a user message carrying a tool_result block.
        if (mm.type === "user" && Array.isArray(mm.message?.content)) {
          for (const block of mm.message.content) {
            if (block?.type === "tool_result") {
              const c = block.content;
              const text = typeof c === "string" ? c : Array.isArray(c) ? c.map((x: any) => x?.text ?? "").join("") : "";
              if (text.includes("percentUsed")) toolText = text;
            }
          }
        }
      }
      expect(toolText).toBeTruthy();
      const parsed = JSON.parse(toolText!);
      expect(typeof parsed.percentUsed).toBe("number");
    } finally {
      rmSync(cwd, { recursive: true, force: true });
    }
  }, 120_000);
});
