import { describe, it, expect } from "vitest";
import { query } from "@anthropic-ai/claude-agent-sdk";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { KairosAssistant } from "../../src/kairos/assistant.js";
import type { BriefMessage } from "../../src/kairos/brief.js";

const live = process.env.ANTHROPIC_API_KEY ? describe : describe.skip;

live("live kairos (real SDK)", () => {
  it("a heartbeat tick reports through the Brief channel under permissionMode auto", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "kairos-live-"));
    const briefs: BriefMessage[] = [];
    const k = new KairosAssistant({ query }, {
      cwd,
      sink: { write: (m) => { briefs.push(m); } },
      proactive: {
        tickPrompt: "Call the SendUserMessage tool with message exactly HEARTBEAT_BRIEF and status normal. Then reply with exactly IDLE.",
        intervalMs: 1500,
        idleBackoff: { stopAfterIdle: 100 },
      },
    });
    await k.start();
    try {
      const sawBrief = await new Promise<boolean>((resolve) => {
        const t0 = Date.now();
        const poll = () => {
          if (briefs.some((b) => /HEARTBEAT_BRIEF/.test(b.text))) return resolve(true);
          if (Date.now() - t0 > 90_000) return resolve(false);
          setTimeout(poll, 2000);
        };
        poll();
      });
      expect(sawBrief).toBe(true); // a real autonomous tick delivered a Brief, no human in the loop
    } finally {
      await k.stop();
    }
  }, 120_000);
});
