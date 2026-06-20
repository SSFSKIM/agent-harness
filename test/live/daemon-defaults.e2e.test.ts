// harness/test/live/daemon-defaults.e2e.test.ts — gated: a BARE daemon spawn (no model/mode) runs on the
// new harness defaults (opus-4-8 + auto + xhigh + claude_code preset) against the real API, and the
// registry records opus-4-8. Proves the daemon-parity options are live-accepted (no 400). Run keyed:
//   set -a; . ../.env; set +a; npx vitest run test/live/daemon-defaults.e2e.test.ts
import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { query as sdkQuery } from "@anthropic-ai/claude-agent-sdk";
import { DaemonSupervisor } from "../../src/daemon/supervisor.js";

const live = process.env.ANTHROPIC_API_KEY ? describe : describe.skip;

live("daemon defaults (live)", () => {
  it("a bare spawn runs on opus-4-8 with the CC preset and completes a turn", async () => {
    const sup = new DaemonSupervisor({ query: sdkQuery }, { dir: mkdtempSync(join(tmpdir(), "cc-daemon-live-")) });
    try {
      const id = sup.spawn({});                                  // no model, no mode → harness defaults
      const { result } = await sup.submit(id, "Reply with exactly the single word READY.", () => {});
      expect(String(result)).toMatch(/READY/i);
      expect(sup.list().find((r) => r.id === id)?.model).toBe("claude-opus-4-8");
    } finally {
      await sup.shutdown();
    }
  }, 120_000);
});
