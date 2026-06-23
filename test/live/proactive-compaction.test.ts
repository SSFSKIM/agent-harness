import { describe, it, expect } from "vitest";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openSession } from "../../src/session/index.js";

// PROACTIVE self-compaction: the seam test (compaction.test.ts) names the tool and the moment
// ("Use RequestCompaction now"). This one is realistic: a multi-step coding task in a throwaway repo
// (so context grows via real Read/Write/Bash tool calls), and only a SOFT standing instruction —
// "when the work is done, compact your context" — WITHOUT naming the tool. The model must (a) judge
// when the task is complete, (b) DISCOVER the deferred cc-compact tool via ToolSearch on its own, and
// (c) call it. This is the open question deferral raised (probe 35c): will the model self-compact when
// it isn't spoon-fed the tool?
const live = (process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_CODE_OAUTH_TOKEN) ? describe : describe.skip;
const MODEL = "claude-haiku-4-5-20251001";

live("proactive self-compaction (real SDK, real coding work)", () => {
  it("model self-compacts after finishing a multi-step task, from a soft instruction (no tool name)", async () => {
    const dir = mkdtempSync(join(tmpdir(), "cc-proactive-"));
    writeFileSync(join(dir, "README.md"), "# scratch project\nImplement small math utilities here.\n");
    const s = openSession({ model: MODEL, cwd: dir, permissionMode: "bypassPermissions", compactTool: true, maxTurns: 40 });
    const toolUses: string[] = [];
    let sawTextSummaryInsteadOfTool = false;
    try {
      const before = (await s.getContextUsage()) as { totalTokens?: number };
      await s.submit(
        [
          "This is a small JS project. Using your tools, do ALL of the following in order:",
          "1. Create math.js exporting two CommonJS functions: add(a,b) and mul(a,b).",
          "2. Create run.js that requires ./math.js, computes add(2,3) and mul(4,5), and console.logs each result on its own line.",
          "3. Run `node run.js` with the shell and confirm it prints 5 then 20. If wrong, fix the code and re-run until correct.",
          "4. Once the output is verified correct, compact your context window to free up space before you finish.",
          "Finally, reply with exactly: DONE",
        ].join("\n"),
        (m) => {
          const mm = m as any;
          if (mm.type === "assistant") for (const b of mm.message?.content || []) {
            if (b.type === "tool_use") toolUses.push(String(b.name));
            // detect if it tried to "compact" by writing a prose summary instead of calling a tool
            if (b.type === "text" && /compact|summar/i.test(b.text || "") && !toolUses.some((n) => n.includes("RequestCompaction"))) sawTextSummaryInsteadOfTool = true;
          }
        },
      );
      // flush past the autonomous /compact that fires at the turn boundary
      await s.submit("Reply with just HI.");
      const after = (await s.getContextUsage()) as { totalTokens?: number };

      const calledCompact = toolUses.some((n) => n.includes("RequestCompaction"));
      const usedSearch = toolUses.some((n) => /toolsearch|tool_search/i.test(n));
      const didRealWork = toolUses.some((n) => /Write|Edit|Bash/i.test(n));
      console.log("[proactive] tool_use order:", JSON.stringify(toolUses));
      console.log("[proactive] calledCompact:", calledCompact, "| usedToolSearch:", usedSearch, "| didRealWork:", didRealWork, "| textSummaryInstead:", sawTextSummaryInsteadOfTool);
      console.log("[proactive] tokens before:", before.totalTokens, "after:", after.totalTokens);

      expect(didRealWork).toBe(true);          // it actually performed the coding task
      expect(calledCompact).toBe(true);        // and proactively self-compacted from the soft instruction
    } finally {
      await s.dispose();
      rmSync(dir, { recursive: true, force: true });
    }
  }, 300_000);
});
