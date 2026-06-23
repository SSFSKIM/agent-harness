import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHarness } from "../../src/index.js";

const live = (process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_CODE_OAUTH_TOKEN) ? describe : describe.skip;

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

  it("a teammate's cc-tasks tool passes the permission bridge and reaches the shared store", async () => {
    const dir = mkdtempSync(join(tmpdir(), "swarm-perm-live-"));
    const h = createHarness({ swarm: true, cwd: dir, permissionMode: "bypassPermissions", maxTurns: 6 });
    const rt = h.swarm!;
    const team = rt.createTeam("alpha");
    const s = rt.spawnTeammate({
      teamId: team.id,
      name: "w1",
      prompt: "Create a task with subject exactly 'BRIDGE_OK' using the TaskCreate tool from the cc-tasks server. Then stop. Do not ask me anything.",
    });
    await s.settled();
    const tasks = await rt.tasks.list();
    expect(tasks.some((t) => /BRIDGE_OK/i.test(t.subject))).toBe(true);
    await rt.disposeAll();
  }, 60_000);

  it("a plan-mode teammate's plan is approved by the coordinator, then it executes (full handshake)", async () => {
    const dir = mkdtempSync(join(tmpdir(), "swarm-plan-live-"));
    const h = createHarness({ swarm: true, cwd: dir, maxTurns: 8 }); // post-approval default "default"; cc-tasks is allowlisted
    const rt = h.swarm!;
    const team = rt.createTeam("alpha");
    const s = rt.spawnTeammate({
      teamId: team.id,
      name: "w1",
      plan: true,
      prompt:
        "You are in plan mode. Produce a one-line plan: 'Plan: create the PLAN_OK task'. " +
        "Call the ExitPlanMode tool to present it. After it is approved, create a task with subject " +
        "exactly 'PLAN_OK' using the TaskCreate tool from the cc-tasks server. Then stop.",
    });

    // The teammate parks inside ExitPlanMode → canUseTool, so its plan lands in the coordinator inbox
    // before its turn settles. Poll for it.
    const deadline = Date.now() + 45_000;
    let plan: any;
    while (Date.now() < deadline && !plan) {
      plan = rt.checkMessages().find((m) => m.kind === "plan");
      if (!plan) await new Promise((r) => setTimeout(r, 300));
    }
    expect(plan, "no plan envelope arrived").toBeTruthy();
    expect(String((plan.data as any).plan)).toMatch(/PLAN_OK|Plan/i);

    expect(await rt.respondPlan((plan.data as any).requestId, "approve")).toBe(true);
    await s.settled(); // turn resumes after approval → teammate creates the task

    const tasks = await rt.tasks.list();
    expect(tasks.some((t) => /PLAN_OK/i.test(t.subject))).toBe(true);
    await rt.disposeAll();
  }, 90_000);
});
