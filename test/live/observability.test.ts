import { describe, it, expect } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHarness, listSessions } from "../../src/index.js";

const live = (process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_CODE_OAUTH_TOKEN) ? describe : describe.skip;
const MODEL = "claude-haiku-4-5-20251001";

live("live observability read API (real SDK)", () => {
  it("getContextUsage() reports tokens; listSessions({cwd}) finds the session scoped to its dir", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "cc-observe-live-"));
    try {
      const h = createHarness({ model: MODEL, permissionMode: "auto", cwd });
      let usage: any;
      let sessionId: string | undefined;
      for await (const m of h.stream("Reply OK and nothing else.")) {
        const mm = m as any;
        if (mm.type === "system" && mm.subtype === "init") {
          sessionId = mm.session_id;
          usage = await h.getContextUsage(); // requires the active query (still streaming)
        }
      }
      expect(typeof usage?.totalTokens).toBe("number");
      expect(sessionId).toBeTruthy();
      // listSessions scoped to the project dir (cwd→dir) finds the just-created session.
      const sessions = await listSessions({ cwd });
      expect(sessions.some((s) => s.sessionId === sessionId)).toBe(true);
    } finally {
      rmSync(cwd, { recursive: true, force: true });
    }
  }, 60_000);
});
