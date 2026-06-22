import { describe, it, expect } from "vitest";
import { query } from "@anthropic-ai/claude-agent-sdk";
import { DaemonSession } from "../../src/daemon/session.js";
import { openSession } from "../../src/session/index.js";

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

  // The seam the manual test above bypasses: the AGENT itself invoking mcp__cc-compact__RequestCompaction.
  // This exercises the full model-driven chain end-to-end — model calls the (deferred) tool → readLoop fires
  // the autonomous /compact at the next turn boundary → real token reduction — which neither the manual live
  // test (calls compact() directly) nor the unit tests (stub the model) ever cover.
  it("agent-invoked RequestCompaction triggers a real compaction (token usage drops)", async () => {
    const s = openSession({ model: MODEL, permissionMode: "bypassPermissions", compactTool: true });
    try {
      await s.submit("In ~400 words, explain how DNS resolution works end to end.");
      await s.submit("In ~400 words, explain how the TLS 1.3 handshake works.");
      await s.submit("In ~400 words, explain how TCP congestion control works.");
      const pre = (await s.getContextUsage()) as { totalTokens?: number };

      let calledTool = false;
      await s.submit(
        "You are running low on context. Use the RequestCompaction tool now to schedule a compaction, then reply with just DONE.",
        (m) => { const mm = m as any; if (mm.type === "assistant") for (const b of mm.message?.content || []) if (b.type === "tool_use" && String(b.name).includes("RequestCompaction")) calledTool = true; },
      );
      // The autonomous /compact is enqueued FIFO after the tool turn; this flush turn resolves only once it has run.
      await s.submit("Reply with just HI.");
      const post = (await s.getContextUsage()) as { totalTokens?: number };

      console.log("[agent-compact] calledTool:", calledTool, "preTokens:", pre.totalTokens, "postTokens:", post.totalTokens);
      expect(calledTool).toBe(true);
      expect(post.totalTokens!).toBeLessThan(pre.totalTokens!);
    } finally {
      await s.dispose();
    }
  }, 180_000);
});
