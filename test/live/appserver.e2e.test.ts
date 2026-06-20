// test/live/appserver.e2e.test.ts
import { describe, it, expect } from "vitest";
import { DirectorClient } from "../contract/client.js";
import { fileURLToPath } from "node:url"; import { dirname, resolve } from "node:path";
const live = (process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_CODE_OAUTH_TOKEN) ? describe : describe.skip;
const BIN = resolve(dirname(fileURLToPath(import.meta.url)), "../../dist/bin.js");

live("app-server live e2e", () => {
  it("a real turn completes with a final answer", async () => {
    const c = new DirectorClient(["node", BIN, "app-server", "-c", "approvals_reviewer=auto_review"], { ...process.env } as any);
    try {
      await c.initialize();
      const tid = await c.threadStart(process.cwd());
      const r = await c.runTurn(tid, "Reply with exactly: pong", process.cwd());
      expect(r.status).toBe("completed");
      expect((r.final ?? "").toLowerCase()).toContain("pong");
    } finally {
      c.stop();
    }
  }, 90_000);
});
