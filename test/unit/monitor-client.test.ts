import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DaemonSupervisor } from "../../src/daemon/supervisor.js";
import { DaemonServer } from "../../src/daemon/server.js";
import { daemonRequest } from "../../src/daemon/client.js";
import { daemonMonitorClient } from "../../src/monitor/client.js";
import { collect } from "../../src/monitor/snapshot.js";

const tmp = () => mkdtempSync(join(tmpdir(), "cc-daemon-"));
// a session whose live query exposes getContextUsage (so the context_usage control frame returns a payload)
function ctxQuery({ prompt }: any) {
  const gen: any = (async function* () {
    for await (const t of prompt) { yield { type: "system", subtype: "init", session_id: "sdk-1" }; yield { type: "result", result: "did:" + t.message.content }; }
  })();
  gen.getContextUsage = async () => ({ totalTokens: 1000, maxTokens: 5000 });
  return gen;
}

describe("daemonMonitorClient + collect over a real UDS", () => {
  it("round-trips list + context_usage into a snapshot", async () => {
    const d = tmp(); const sock = join(d, "sock");
    const sup = new DaemonSupervisor({ query: ctxQuery }, { dir: join(d, "sessions") });
    const server = new DaemonServer(sup, sock);
    await server.listen();

    const id = (await daemonRequest(sock, { op: "spawn", model: "opus-4.8" }))[0].id;
    await daemonRequest(sock, { op: "submit", id, prompt: "hi" }, () => {}); // open the transport so getContextUsage is live

    const snap = await collect(daemonMonitorClient(sock), { now: () => 0, socketPath: sock });
    expect(snap.daemonUp).toBe(true);
    const row = snap.sessions.find((r) => r.id === id)!;
    expect(row.model).toBe("opus-4.8");
    expect(row.tokens).toBe(1000);
    expect(row.ctxPercent).toBe(20); // 1000/5000

    await daemonRequest(sock, { op: "shutdown" });
    await server.closed;
  });

  it("list() rejects when no daemon is listening → collect reports daemonUp=false", async () => {
    const snap = await collect(daemonMonitorClient(join(tmp(), "absent")), { now: () => 0, socketPath: "absent" });
    expect(snap.daemonUp).toBe(false);
  });
});
