import { describe, it, expect } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openSession, resumeSession } from "../../src/index.js";

const live = (process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_CODE_OAUTH_TOKEN) ? describe : describe.skip;
const MODEL = "claude-haiku-4-5-20251001";

live("live interactive Session (real SDK)", () => {
  it("multi-turn: captures a stable sessionId and recalls across turns", async () => {
    const s = openSession({ model: MODEL, permissionMode: "bypassPermissions" });
    try {
      await s.submit("Remember this codeword: ZEBRA77. Reply OK only.");
      const id1 = s.sessionId;
      const r2 = await s.submit("What was the codeword? Reply with just the word.");
      expect(id1).toBeTruthy();
      expect(s.sessionId).toBe(id1);                       // stable across turns
      expect(String(r2.result)).toMatch(/ZEBRA77/);
    } finally { await s.dispose(); }
  }, 60_000);

  it("compact() performs a real manual compaction (postTokens < preTokens)", async () => {
    const s = openSession({ model: MODEL, permissionMode: "bypassPermissions" });
    try {
      await s.submit("In ~400 words, explain how DNS resolution works end to end.");
      await s.submit("In ~400 words, explain how the TLS 1.3 handshake works.");
      await s.submit("In ~400 words, explain how TCP congestion control works.");
      const outcome = await s.compact();
      expect(outcome.result).toBe("success");
      expect(outcome.postTokens!).toBeLessThan(outcome.preTokens!);
    } finally { await s.dispose(); }
  }, 120_000);

  it("resume round-trip: a new Session resumes the id and recalls context", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "cc-session-live-"));
    let id: string | undefined;
    const first = openSession({ model: MODEL, permissionMode: "bypassPermissions", cwd });
    try {
      await first.submit("Remember this codeword: MANGO9. Reply OK only.");
      id = first.sessionId;
      expect(id).toBeTruthy();
    } finally { await first.dispose(); }
    const second = resumeSession(id!, { model: MODEL, permissionMode: "bypassPermissions", cwd });
    try {
      const r = await second.submit("What codeword did I give you earlier? Reply with just the word.");
      expect(String(r.result)).toMatch(/MANGO9/);
      expect(second.sessionId).toBe(id);                   // resume preserves the id
    } finally {
      await second.dispose();
      rmSync(cwd, { recursive: true, force: true });
    }
  }, 90_000);
});
