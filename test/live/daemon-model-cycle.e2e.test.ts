// harness/test/live/daemon-model-cycle.e2e.test.ts — gated: a live set_model control op writes the new
// model back into the registry (the dashboard m-cycle fix, end-to-end). Run keyed (OAuth bills subscription):
//   set -a; . ../.env; set +a; unset ANTHROPIC_API_KEY; npx vitest run test/live/daemon-model-cycle.e2e.test.ts
import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { query as sdkQuery } from "@anthropic-ai/claude-agent-sdk";
import { DaemonSupervisor } from "../../src/daemon/supervisor.js";

const live = (process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_CODE_OAUTH_TOKEN) ? describe : describe.skip;

live("daemon model cycle (live)", () => {
  it("a successful set_model control op reflects the new model in list()", async () => {
    const sup = new DaemonSupervisor({ query: sdkQuery }, { dir: mkdtempSync(join(tmpdir(), "cc-daemon-cycle-")) });
    try {
      const id = sup.spawn({ model: "claude-opus-4-8" });
      expect(sup.list().find((r) => r.id === id)?.model).toBe("claude-opus-4-8");
      const res = await sup.control(id, { type: "set_model", model: "haiku" });
      expect(res.ok).toBe(true);
      expect(sup.list().find((r) => r.id === id)?.model).toBe("haiku");   // live model written back
    } finally {
      await sup.shutdown();
    }
  }, 120_000);
});
