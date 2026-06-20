import { describe, it, expect } from "vitest";
import { query } from "@anthropic-ai/claude-agent-sdk";
import { DaemonSession } from "../../src/daemon/session.js";

const live = (process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_CODE_OAUTH_TOKEN) ? describe : describe.skip;
const MODEL = "claude-haiku-4-5-20251001";

live("live self-compaction (real SDK)", () => {
  it("compact() performs a real manual compaction (postTokens < preTokens)", async () => {
    const s = new DaemonSession("live-compact", { query }, { model: MODEL, permissionMode: "auto" });
    try {
      // Build a transcript large enough to exceed the manual-compact minimum (~3 substantial turns).
      await s.submit("In ~400 words, explain how DNS resolution works end to end.", () => {});
      await s.submit("In ~400 words, explain how the TLS 1.3 handshake works.", () => {});
      await s.submit("In ~400 words, explain how TCP congestion control works.", () => {});
      const outcome = await s.compact();
      expect(outcome.result).toBe("success");
      expect(typeof outcome.preTokens).toBe("number");
      expect(typeof outcome.postTokens).toBe("number");
      expect(outcome.postTokens!).toBeLessThan(outcome.preTokens!);
    } finally {
      await s.dispose();
    }
  }, 120_000);
});
