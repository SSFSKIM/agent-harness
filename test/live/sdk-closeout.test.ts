// test/live/sdk-closeout.test.ts
import { describe, it, expect } from "vitest";
import { openSession, listSessions, getSessionMessages, renameSession, tagSession, deleteSession } from "../../src/index.js";

const live = process.env.ANTHROPIC_API_KEY ? describe : describe.skip;
const MODEL = "claude-haiku-4-5-20251001";
const OPUS = "claude-opus-4-8";

live("SDK capability closeout (real SDK)", () => {
  // Part A — turn controls
  it("effort + thinking are accepted and complete a turn", async () => {
    const s = openSession({ model: MODEL, permissionMode: "bypassPermissions", effort: "low", thinking: { type: "enabled", budgetTokens: 1024 } });
    try { expect(String((await s.submit("Reply with the single word OK.")).result).length).toBeGreaterThan(0); }
    finally { await s.dispose(); }
  }, 60_000);

  it("maxBudgetUsd, when exceeded, throws (pass-through, no graceful result)", async () => {
    const s = openSession({ model: MODEL, permissionMode: "bypassPermissions", maxBudgetUsd: 0.0001 });
    try { await expect(s.submit("Run three bash commands one at a time: echo a; echo b; echo c, then summarize.")).rejects.toThrow(); }
    finally { await s.dispose(); }
  }, 60_000);

  it("taskBudget is accepted on opus-4-8", async () => {
    const s = openSession({ model: OPUS, permissionMode: "bypassPermissions", taskBudget: { total: 60000 } });
    try { expect(String((await s.submit("Reply with the single word OK.")).result)).toMatch(/OK/i); }
    finally { await s.dispose(); }
  }, 90_000);

  it("includePartialMessages yields stream_event frames", async () => {
    const s = openSession({ model: MODEL, permissionMode: "bypassPermissions", includePartialMessages: true });
    try {
      const types: string[] = [];
      for await (const m of s.stream("In one short sentence, say hello.")) types.push((m as any).type);
      expect(types).toContain("stream_event");
    } finally { await s.dispose(); }
  }, 60_000);

  // Part B — introspection methods
  it("usage()/initializationResult() return structured data; applyFlagSettings resolves", async () => {
    const s = openSession({ model: MODEL, permissionMode: "bypassPermissions" });
    try {
      await s.submit("Reply OK."); // open the transport
      expect((await s.usage() as any)?.session).toBeTruthy();
      expect((await s.initializationResult() as any)?.models).toBeTruthy();
      await s.applyFlagSettings({});
    } finally { await s.dispose(); }
  }, 60_000);

  // Part C — session-store mutation
  it("tag → rename → delete round-trips on the default store", async () => {
    const s = openSession({ model: MODEL, permissionMode: "bypassPermissions" });
    let sid: string | undefined;
    try { await s.submit("Reply OK."); sid = s.sessionId; } finally { await s.dispose(); }
    expect(sid).toBeTruthy();
    await tagSession(sid!, "closeout-test");
    await renameSession(sid!, "Closeout Renamed");
    const listed = (await listSessions()).find((x: any) => x.sessionId === sid);
    expect(JSON.stringify(listed)).toContain("Closeout Renamed");
    await deleteSession(sid!);
    expect((await listSessions()).find((x: any) => x.sessionId === sid)).toBeUndefined();
    expect(await getSessionMessages(sid!)).toEqual([]);
  }, 90_000);
});
