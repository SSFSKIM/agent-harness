import { describe, it, expect } from "vitest";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openSession } from "../../src/session/index.js";

// CONFIG-DRIVEN self-compaction: proactive-compaction.test.ts proves the model self-compacts from a
// hand-written soft instruction. THIS proves the productized path — `contextBudget` alone (the flag the
// app-server sets) appends the persona AND wires the checkpoint/high-water push, so the model self-compacts
// with ZERO mention of compaction in any turn prompt. Thresholds are set tiny so a couple of real tool
// turns + a git commit cross them; the worker must (a) DISCOVER cc-compact via ToolSearch (deferred, never
// named) and (b) call RequestCompaction off the standing policy + injected usage signal alone.
const live = (process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_CODE_OAUTH_TOKEN) ? describe : describe.skip;
const MODEL = "claude-haiku-4-5-20251001";

live("config-driven self-compaction (contextBudget flag, real SDK + git checkpoint)", () => {
  it("model self-compacts from the standing budget persona + checkpoint push, no compaction in the prompt", async () => {
    const dir = mkdtempSync(join(tmpdir(), "cc-budget-"));
    const git = (...a: string[]) => execFileSync("git", a, { cwd: dir });
    git("init", "-q");
    git("config", "user.email", "t@example.com");
    git("config", "user.name", "t");
    writeFileSync(join(dir, "README.md"), "# scratch\nSmall math utils.\n");

    // tiny band → after the framing tokens + first turn, usage is already past `net`, and any commit arms the
    // checkpoint push. contextBudget self-enables cc-context (the push needs getContextUsage) + the persona.
    const s = openSession({
      model: MODEL, cwd: dir, permissionMode: "bypassPermissions", compactTool: true, maxTurns: 40,
      contextBudget: { soft: 1000, target: 1000, net: 1000, hard: 1000 },
    });
    const toolUses: string[] = [];
    const onMsg = (m: any) => {
      if (m?.type === "assistant") for (const b of m.message?.content || []) if (b.type === "tool_use") toolUses.push(String(b.name));
    };
    try {
      const before = (await s.getContextUsage()) as { totalTokens?: number };
      // Turn 1: real work + a git commit (arms the checkpoint flag). NOTHING about context/compaction.
      await s.submit([
        "This is a small JS project. Using your tools, do ALL of the following in order:",
        "1. Create math.js exporting a CommonJS function add(a,b).",
        "2. Run `git add -A && git commit -m 'add'` with the shell.",
        "Then reply with exactly: READY",
      ].join("\n"), onMsg);
      // Turn 2: more work past the checkpoint — the push fires here. Still nothing about compaction.
      await s.submit([
        "Now add a CommonJS function mul(a,b) to math.js, then `git add -A && git commit -m 'mul'`.",
        "Then reply with exactly: DONE",
      ].join("\n"), onMsg);
      const after = (await s.getContextUsage()) as { totalTokens?: number };

      const calledCompact = toolUses.some((n) => n.includes("RequestCompaction"));
      const didRealWork = toolUses.some((n) => /Write|Edit|Bash/i.test(n));
      console.log("[budget] tool_use order:", JSON.stringify(toolUses));
      console.log("[budget] calledCompact:", calledCompact, "| didRealWork:", didRealWork);
      console.log("[budget] tokens before:", before.totalTokens, "after:", after.totalTokens);

      expect(didRealWork).toBe(true);     // it actually did the coding + commits
      expect(calledCompact).toBe(true);   // and self-compacted off the standing budget policy + push alone
    } finally {
      await s.dispose();
      rmSync(dir, { recursive: true, force: true });
    }
  }, 300_000);
});
