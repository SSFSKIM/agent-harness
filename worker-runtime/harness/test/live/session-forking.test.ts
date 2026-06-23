import { describe, it, expect } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openSession, resumeSession, forkSession } from "../../src/index.js";

const live = (process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_CODE_OAUTH_TOKEN) ? describe : describe.skip;
const MODEL = "claude-haiku-4-5-20251001";

live("live session forking (real SDK)", () => {
  it("fork branches a session: the fork recalls history; the original's later turns don't leak in", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "cc-fork-live-"));
    const orig = openSession({ model: MODEL, permissionMode: "bypassPermissions", cwd });
    let srcId: string | undefined;
    let forkId: string | undefined;
    try {
      await orig.submit("Remember this codeword: ZEBRA. Reply OK only.");
      srcId = orig.sessionId;
      expect(srcId).toBeTruthy();
      const res = await forkSession(srcId!, { cwd });          // fork AFTER ZEBRA, BEFORE MANGO
      forkId = res.sessionId;
      expect(forkId).toBeTruthy();
      expect(forkId).not.toBe(srcId);                          // fork mints a NEW id
      await orig.submit("Also remember a second codeword: MANGO. Reply OK only."); // original-only, post-fork
    } finally { await orig.dispose(); }

    const branch = resumeSession(forkId!, { model: MODEL, permissionMode: "bypassPermissions", cwd });
    try {
      const r = await branch.submit("List every codeword I gave you. Reply with just the words.");
      expect(String(r.result)).toMatch(/ZEBRA/);              // the fork carries history up to the fork point
      expect(String(r.result)).not.toMatch(/MANGO/);          // the original's later turn did NOT leak into the branch
    } finally { await branch.dispose(); rmSync(cwd, { recursive: true, force: true }); }
  }, 120_000);
});
