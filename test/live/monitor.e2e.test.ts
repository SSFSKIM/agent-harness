import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { query as sdkQuery } from "@anthropic-ai/claude-agent-sdk";
import { DaemonSupervisor } from "../../src/daemon/supervisor.js";
import { DaemonServer } from "../../src/daemon/server.js";
import { daemonRequest } from "../../src/daemon/client.js";
import { daemonMonitorClient } from "../../src/monitor/client.js";
import { collect } from "../../src/monitor/snapshot.js";

const live = process.env.ANTHROPIC_API_KEY ? describe : describe.skip;
const tmp = () => mkdtempSync(join(tmpdir(), "cc-mon-"));

live("monitor e2e (live daemon)", () => {
  it("collect reflects a real spawned+submitted session with populated ctx", async () => {
    const d = tmp(); const sock = join(d, "sock");
    const sup = new DaemonSupervisor({ query: sdkQuery }, { dir: join(d, "sessions") });
    const server = new DaemonServer(sup, sock);
    await server.listen();
    try {
      const id = (await daemonRequest(sock, { op: "spawn", model: "claude-haiku-4-5-20251001" }))[0].id;
      await daemonRequest(sock, { op: "submit", id, prompt: "say hi in one word" }, () => {});
      const snap = await collect(daemonMonitorClient(sock), { now: () => Date.now(), socketPath: sock });
      const row = snap.sessions.find((r) => r.id === id)!;
      expect(row).toBeTruthy();
      expect(typeof row.tokens).toBe("number"); // real getContextUsage populated tokens after a turn
    } finally {
      await daemonRequest(sock, { op: "shutdown" }).catch(() => {});
      await server.closed;
    }
  });
});
