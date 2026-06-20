// harness/test/live/daemon-permissions.e2e.test.ts
import { describe, it, expect } from "vitest";
import { query } from "@anthropic-ai/claude-agent-sdk";
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DaemonSupervisor } from "../../src/daemon/supervisor.js";

const live = (process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_CODE_OAUTH_TOKEN) ? describe : describe.skip;

function workdir(): string {
  const dir = mkdtempSync(join(tmpdir(), "daemon-perms-live-"));
  writeFileSync(join(dir, "note.txt"), "ORIGINAL\n");
  return dir;
}

live("daemon-attached interactive permissions (live)", () => {
  it("default-mode session: edits park → respond allow (draining all parks) → applies", async () => {
    const cwd = workdir();
    const sup = new DaemonSupervisor({ query }, { dir: join(cwd, "reg"), idleTimeoutMs: 0, sessionOptions: () => ({ cwd, settingSources: [] }) });
    try {
      const id = sup.spawn({ model: "claude-sonnet-4-6" });          // default mode → gated tools route to the broker
      let done = false;
      const submitP = sup.submit(id, "Edit note.txt, replacing ORIGINAL with CHANGED. Do nothing else.", () => {}).finally(() => { done = true; });
      let sawEdit = false;
      const deadline = Date.now() + 80_000;
      while (!done) {                                                 // human-like responder: allow each park as it appears
        for (const e of sup.pendingPermissions()) {
          if (e.sessionId === id && e.toolName === "Edit") sawEdit = true;
          sup.respondPermission(e.toolUseID, { kind: "allow_once" });
        }
        if (Date.now() > deadline) throw new Error("default-mode permission loop timed out");
        await new Promise((r) => setTimeout(r, 200));
      }
      await submitP;
      expect(sawEdit).toBe(true);                                    // the Edit specifically parked and we allowed it
      expect(readFileSync(join(cwd, "note.txt"), "utf8")).toContain("CHANGED");
    } finally {
      await sup.shutdown();
      rmSync(cwd, { recursive: true, force: true });
    }
  }, 90_000);

  it("auto session on sonnet-4-6: an edit auto-approves with no pending", async () => {
    const cwd = workdir();
    const sup = new DaemonSupervisor({ query }, { dir: join(cwd, "reg"), idleTimeoutMs: 0, sessionOptions: () => ({ cwd, settingSources: [] }) });
    try {
      const id = sup.spawn({ model: "claude-sonnet-4-6", permissionMode: "auto" }); // classifier owns the trusted surface
      await sup.submit(id, "Edit note.txt, replacing ORIGINAL with CHANGED. Do nothing else.", () => {});
      expect(sup.pendingPermissions()).toEqual([]);                  // never parked — no human in the loop
      expect(readFileSync(join(cwd, "note.txt"), "utf8")).toContain("CHANGED");
    } finally {
      await sup.shutdown();
      rmSync(cwd, { recursive: true, force: true });
    }
  }, 90_000);
});
