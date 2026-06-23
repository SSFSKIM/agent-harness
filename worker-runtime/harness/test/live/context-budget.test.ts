import { describe, it, expect } from "vitest";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openSession } from "../../src/session/index.js";

// END-TO-END SMOKE + OBSERVATION for the productized `contextBudget` path. `contextBudget` alone (the flag
// the app-server sets) appends the persona AND wires the checkpoint/high-water push; this test runs a real
// worker session through it (real Write/Bash/Edit + git commits, ZERO mention of compaction in any prompt)
// and asserts the feature does not break the session. Self-compaction itself is ADVISORY + model-dependent:
// a capable model often judges it still has room and declines a checkpoint nudge (observed on haiku AND
// sonnet, 2026-06-24) — so `calledCompact` is OBSERVED/logged for the controller, NOT gated. The SDK's
// native auto-compact remains the involuntary floor. (proactive-compaction.test.ts shows the model DOES
// compact when the turn prompt explicitly instructs it — the soft standing persona is the weaker signal.)
const live = (process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_CODE_OAUTH_TOKEN) ? describe : describe.skip;
// Default haiku for a cheap controller run; override to the worker's real tier (sonnet/opus) via CC_BUDGET_LIVE_MODEL.
const MODEL = process.env.CC_BUDGET_LIVE_MODEL || "claude-haiku-4-5-20251001";

live("contextBudget end-to-end on a real worker session (self-compaction advisory/observed)", () => {
  it("runs a real coding+commit session with contextBudget enabled without breaking; logs whether the model self-compacts", async () => {
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
      console.log("[budget] calledCompact:", calledCompact, "| didRealWork:", didRealWork, "(advisory — not gated)");
      console.log("[budget] tokens before:", before.totalTokens, "after:", after.totalTokens);

      // GATE: the contextBudget wiring (persona + push + self-enabled cc-context) must not break a real worker
      // session — the worker still does its coding work and commits end-to-end.
      expect(didRealWork).toBe(true);
      // NOT gated: self-compaction is advisory + model-dependent (logged above for the controller).
    } finally {
      await s.dispose();
      rmSync(dir, { recursive: true, force: true });
    }
  }, 300_000);
});
