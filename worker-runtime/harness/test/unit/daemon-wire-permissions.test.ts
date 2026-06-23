import { describe, it, expect, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { daemonOp } from "../../src/daemon/types.js";
import { DaemonSupervisor } from "../../src/daemon/supervisor.js";
import { DaemonServer } from "../../src/daemon/server.js";
import { daemonRequest } from "../../src/daemon/client.js";
import type { QueryFn } from "../../src/swarm/types.js";

const captureQuery: QueryFn = (({ prompt }: any) => (async function* () {
  yield { type: "system", subtype: "init", session_id: "sdk-x" };
  for await (const _ of prompt) { /* drain so input.close() exits on shutdown */ }
})()) as unknown as QueryFn;

describe("permission wire ops", () => {
  it("the schema validates the new ops + spawn.permissionMode and rejects a bad decision", () => {
    expect(daemonOp.parse({ op: "pending_permissions" }).op).toBe("pending_permissions");
    expect(daemonOp.parse({ op: "permission_response", toolUseID: "t", decision: { kind: "deny" } }).op).toBe("permission_response");
    expect(daemonOp.parse({ op: "spawn", permissionMode: "auto" }).op).toBe("spawn");
    expect(() => daemonOp.parse({ op: "permission_response", toolUseID: "t", decision: { kind: "nope" } })).toThrow();
  });

  let server: DaemonServer | undefined;
  afterEach(async () => { await server?.close(); server = undefined; });

  it("dispatches pending_permissions (empty) and permission_response (no match → ok:false)", async () => {
    const dir = mkdtempSync(join(tmpdir(), "wire-perms-"));
    const sock = join(dir, "d.sock");
    const sup = new DaemonSupervisor({ query: captureQuery }, { dir: join(dir, "reg"), idleTimeoutMs: 0 });
    server = new DaemonServer(sup, sock);
    await server.listen();
    const [pend] = await daemonRequest(sock, { op: "pending_permissions" });
    expect(pend).toEqual({ ok: true, pending: [] });
    const [resp] = await daemonRequest(sock, { op: "permission_response", toolUseID: "ghost", decision: { kind: "deny" } });
    expect(resp).toEqual({ ok: false, error: "no pending request" });
    const [spawned] = await daemonRequest(sock, { op: "spawn", model: "claude-haiku-4-5-20251001", permissionMode: "auto" });
    expect(spawned.ok).toBe(true);
    expect(sup.list()[0].model).toBe("claude-sonnet-4-6");     // forced supported model, end-to-end over the wire
    await sup.shutdown();
    rmSync(dir, { recursive: true, force: true });
  });
});
