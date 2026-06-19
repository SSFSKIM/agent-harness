// harness/test/live/daemon-permissions.e2e.test.ts
import { describe, it, expect } from "vitest";
import { query } from "@anthropic-ai/claude-agent-sdk";
import { mkdtempSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DaemonSupervisor } from "../../src/daemon/supervisor.js";
import type { PendingEntry } from "../../src/daemon/permissions.js";

const live = process.env.ANTHROPIC_API_KEY ? describe : describe.skip;

function workdir(): string {
  const dir = mkdtempSync(join(tmpdir(), "daemon-perms-live-"));
  writeFileSync(join(dir, "note.txt"), "ORIGINAL\n");
  return dir;
}
async function waitForPending(sup: DaemonSupervisor, timeoutMs: number): Promise<PendingEntry> {
  const start = Date.now();
  for (;;) {
    const p = sup.pendingPermissions();
    if (p.length) return p[0];
    if (Date.now() - start > timeoutMs) throw new Error("no pending permission appeared");
    await new Promise((r) => setTimeout(r, 250));
  }
}

live("daemon-attached interactive permissions (live)", () => {
  it("default-mode session: an edit parks → respond allow → applies", async () => {
    const cwd = workdir();
    const sup = new DaemonSupervisor({ query }, { dir: join(cwd, "reg"), idleTimeoutMs: 0, sessionOptions: () => ({ cwd, settingSources: [] }) });
    const id = sup.spawn({ model: "claude-sonnet-4-6" });          // default mode → Edit routes to the broker
    const submitP = sup.submit(id, "Edit note.txt, replacing ORIGINAL with CHANGED. Do nothing else.", () => {});
    const entry = await waitForPending(sup, 60_000);
    expect(entry.sessionId).toBe(id);
    expect(sup.respondPermission(entry.toolUseID, { kind: "allow_once" })).toBe(true);
    await submitP;
    expect(readFileSync(join(cwd, "note.txt"), "utf8")).toContain("CHANGED");
    await sup.shutdown();
  }, 90_000);

  it("auto session on sonnet-4-6: an edit auto-approves with no pending", async () => {
    const cwd = workdir();
    const sup = new DaemonSupervisor({ query }, { dir: join(cwd, "reg"), idleTimeoutMs: 0, sessionOptions: () => ({ cwd, settingSources: [] }) });
    const id = sup.spawn({ model: "claude-sonnet-4-6", permissionMode: "auto" }); // classifier owns the trusted surface
    await sup.submit(id, "Edit note.txt, replacing ORIGINAL with CHANGED. Do nothing else.", () => {});
    expect(sup.pendingPermissions()).toEqual([]);                  // never parked — no human in the loop
    expect(readFileSync(join(cwd, "note.txt"), "utf8")).toContain("CHANGED");
    await sup.shutdown();
  }, 90_000);
});
