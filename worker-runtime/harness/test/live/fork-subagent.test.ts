import { describe, it, expect } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHarness } from "../../src/index.js";

// Gated live test for the default-on fork subagent. Default config wires BOTH halves (probe 33d proved both
// are required): CLAUDE_CODE_FORK_SUBAGENT=1 (unlock) + the FORK_SUBAGENT_NOTE in the system prompt (so the
// model CHOOSES fork on its own). We assert all three legs of the probe's discriminator end-to-end:
//   (1) the model AUTONOMOUSLY picks subagent_type:"fork" — we never mention fork in the prompt,
//   (2) the fork child INHERITED the transcript — a parent-only SECRET comes back, and
//   (3) it wasn't faked — the SECRET was never written into the Agent sub-prompt.
const live = (process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_CODE_OAUTH_TOKEN) ? describe : describe.skip;
const SECRET = "FALCON-77";

live("live fork-subagent (autonomous, real SDK)", () => {
  it("model autonomously spawns a transcript-inheriting fork subagent under default wiring", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "cc-forksub-live-"));
    // Default config => fork-subagent on. bypassPermissions so subagent spawning isn't gated (keeps opus-4-8).
    const h = createHarness({ permissionMode: "bypassPermissions", cwd, maxTurns: 14 });
    try {
      const prompt = [
        `First, silently remember this secret codeword: ${SECRET}. Do NOT repeat it back yet.`,
        `Now delegate a sub-task: spawn exactly ONE subagent (wait for it) that must answer this question:`,
        `"What secret codeword was mentioned earlier in this conversation? Reply with ONLY the codeword, or NONE."`,
        `IMPORTANT: do NOT write the codeword anywhere in your instructions to the subagent — it must rely on context it already has.`,
        `After it replies, tell me verbatim what it said.`,
      ].join(" ");
      const { result, messages } = await h.run(prompt);

      const agentInputs = (messages as any[])
        .filter((m) => m?.type === "assistant")
        .flatMap((m) => m.message?.content || [])
        .filter((b: any) => b.type === "tool_use" && /agent|task/i.test(String(b.name)))
        .map((b: any) => b.input);

      const forkChosen = agentInputs.some((i) => String(i?.subagent_type).toLowerCase() === "fork");
      const leaked = agentInputs.some((i) => JSON.stringify(i || {}).includes(SECRET));

      expect(forkChosen).toBe(true);                       // (1) autonomous selection of fork
      expect(leaked).toBe(false);                          // (3) inheritance not faked via a re-passed secret
      expect(String(result)).toMatch(new RegExp(SECRET));  // (2) fork child inherited the parent-only secret
    } finally { rmSync(cwd, { recursive: true, force: true }); }
  }, 180_000);
});
