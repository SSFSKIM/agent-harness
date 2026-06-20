import { describe, it, expect } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { query } from "@anthropic-ai/claude-agent-sdk";
import { SessionRegistry } from "../../src/daemon/registry.js";
import { DaemonSupervisor } from "../../src/daemon/supervisor.js";

const live = (process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_CODE_OAUTH_TOKEN) ? describe : describe.skip;
const MODEL = "claude-haiku-4-5-20251001";

live("live daemon boot-rehydration (real SDK)", () => {
  it("a restarted daemon rehydrates an orphaned record and resumes its context", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "cc-rehydrate-live-"));   // shared cwd → same transcript location
    const regDir = mkdtempSync(join(tmpdir(), "cc-daemon-"));
    // 1) Plant a codeword in a real session; capture its real session_id (the "prior daemon's" session).
    let sessionId: string | undefined;
    for await (const m of query({
      prompt: "Remember this codeword: HERON9. Reply with just OK.",
      options: { model: MODEL, permissionMode: "bypassPermissions", maxTurns: 1, cwd },
    })) {
      if (m.type === "system" && (m as any).subtype === "init") sessionId = (m as any).session_id;
      if ("result" in m) break;
    }
    expect(sessionId).toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/);
    // 2) Seed the registry as a DEAD prior daemon's orphan (pid 999999 is unused on darwin → reads as dead).
    new SessionRegistry({ dir: regDir }).register({
      id: "sess-1", daemonPid: 999999, status: "idle", sessionId, model: MODEL, createdAt: 1, lastActiveAt: 1,
    });
    // 3) A fresh daemon boots with rehydrate:true → claims the orphan; the first submit resumes it.
    const sup = new DaemonSupervisor({ query }, {
      dir: regDir, rehydrate: true,
      sessionOptions: () => ({ permissionMode: "bypassPermissions", allowDangerouslySkipPermissions: true, cwd }),
    });
    try {
      expect(sup.list()[0]).toMatchObject({ id: "sess-1", daemonPid: process.pid, status: "idle" }); // claimed
      const r = await sup.submit("sess-1", "What codeword did I give you earlier? Reply with just the word.", () => {});
      expect(String(r.result)).toMatch(/HERON9/);
    } finally {
      await sup.shutdown();
      rmSync(cwd, { recursive: true, force: true });
      rmSync(regDir, { recursive: true, force: true });
    }
  }, 90_000);
});
