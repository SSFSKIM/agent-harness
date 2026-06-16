import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHarness } from "../../src/index.js";

const live = process.env.ANTHROPIC_API_KEY ? describe : describe.skip;

live("live swarm substrate (real SDK)", () => {
  it("a spawned teammate runs a real turn and its result reaches the coordinator", async () => {
    const dir = mkdtempSync(join(tmpdir(), "swarm-live-"));
    const h = createHarness({ swarm: true, cwd: dir, permissionMode: "bypassPermissions", maxTurns: 2 });
    const rt = h.swarm!;
    const team = rt.createTeam("alpha");
    const s = rt.spawnTeammate({
      teamId: team.id,
      name: "w1",
      prompt: "Reply with exactly the single word PONG and nothing else. Do not use any tools.",
    });
    await s.settled(); // wait for the real model turn to settle
    const msgs = rt.checkMessages();
    expect(msgs.some((m) => m.kind === "result" && /PONG/i.test(m.body))).toBe(true);
    await rt.disposeAll();
  }, 60_000);
});
