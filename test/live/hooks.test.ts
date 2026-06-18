// test/live/hooks.test.ts
import { describe, it, expect } from "vitest";
import { openSession, injectContext, blockTool, mergeHooks } from "../../src/index.js";

const live = process.env.ANTHROPIC_API_KEY ? describe : describe.skip;
const MODEL = "claude-haiku-4-5-20251001";

live("live hooks (real SDK)", () => {
  it("injectContext is recalled by the model", async () => {
    const hooks = mergeHooks(injectContext(() => "The secret codeword is FALCON-8842."));
    const s = openSession({ model: MODEL, permissionMode: "bypassPermissions", hooks });
    try {
      const r = await s.submit("What is the secret codeword you were told? Reply with just the word.");
      expect(String(r.result)).toMatch(/FALCON-8842/);
    } finally { await s.dispose(); }
  }, 60_000);

  it("blockTool's deny hook fires on a matching Bash command", async () => {
    const fired: string[] = [];
    // Predicate form so the test captures, deterministically, that PreToolUse fired
    // for the Bash attempt and our deny matched it — no dependency on hook_* frames
    // (which would require includeHookEvents). Blocking takes effect regardless.
    const hooks = mergeHooks(
      blockTool("Bash", (i: any) => {
        const cmd = String(i?.tool_input?.command ?? "");
        const hit = cmd.includes("FORBIDDEN_CMD");
        if (hit) fired.push(cmd);
        return hit;
      }, "blocked by probe hook"),
    );
    const s = openSession({ model: MODEL, permissionMode: "bypassPermissions", hooks });
    try {
      const r = await s.submit("Run exactly this bash command: echo FORBIDDEN_CMD");
      expect(fired.length).toBeGreaterThan(0);            // PreToolUse fired; our deny matched the attempt
      expect(String(r.result).length).toBeGreaterThan(0); // the turn still completed
    } finally { await s.dispose(); }
  }, 90_000);
});
