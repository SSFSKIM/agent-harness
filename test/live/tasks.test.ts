import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHarness } from "../../src/index.js";

const live = (process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_CODE_OAUTH_TOKEN) ? describe : describe.skip;

live("live task tools (real SDK)", () => {
  it("the model creates dependent tasks and lists them via the MCP tools", async () => {
    const dir = mkdtempSync(join(tmpdir(), "tasks-live-"));
    const h = createHarness({
      taskTools: { dir },
      permissionMode: "bypassPermissions",
      maxTurns: 8,
    });
    await h.run(
      "Use the TaskCreate tool to create a task with subject 'first'. " +
      "Then use TaskCreate to create a task 'second' that is blockedBy the first task's id. " +
      "Then call TaskList. Do not ask me anything; just use the tools.",
    );
    const all = await h.tasks!.list();
    expect(all.length).toBe(2);
    const second = all.find((t) => t.subject.toLowerCase().includes("second"));
    expect(second?.blockedBy.length).toBe(1); // depends on 'first'
  });
});
