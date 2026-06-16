import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DaemonSupervisor } from "../../src/daemon/supervisor.js";
import { DaemonServer } from "../../src/daemon/server.js";
import { daemonRequest } from "../../src/daemon/client.js";

const tmp = () => mkdtempSync(join(tmpdir(), "cc-daemon-"));
function fakeQuery({ prompt }: any) {
  return (async function* () {
    for await (const turn of prompt) {
      yield { type: "assistant", message: { content: [{ type: "text", text: "ack" }] } };
      yield { type: "result", result: "did:" + turn.message.content };
    }
  })();
}

describe("DaemonServer over a real UDS", () => {
  it("round-trips spawn → submit (streamed) → list → stop → shutdown", async () => {
    const d = tmp();
    const sock = join(d, "sock");
    const sup = new DaemonSupervisor({ query: fakeQuery }, { dir: join(d, "sessions") });
    const server = new DaemonServer(sup, sock);
    await server.listen();

    const spawn = await daemonRequest(sock, { op: "spawn", model: "m1" });
    const id = spawn[0].id;
    expect(spawn[0]).toEqual({ ok: true, id });

    const lines: any[] = [];
    await daemonRequest(sock, { op: "submit", id, prompt: "hi" }, (o) => lines.push(o));
    expect(lines.find((l) => l.type === "chunk")).toBeTruthy();
    expect(lines.find((l) => l.type === "done")?.result).toBe("did:hi");

    const list = await daemonRequest(sock, { op: "list" });
    expect(list[0].sessions.map((s: any) => s.id)).toEqual([id]);

    expect((await daemonRequest(sock, { op: "stop", id }))[0]).toEqual({ ok: true });
    expect((await daemonRequest(sock, { op: "list" }))[0].sessions).toEqual([]);

    await daemonRequest(sock, { op: "shutdown" });
    await server.closed;
  });
  it("refuses to start a second daemon on a live socket", async () => {
    const d = tmp();
    const sock = join(d, "sock");
    const a = new DaemonServer(new DaemonSupervisor({ query: fakeQuery }, { dir: join(d, "s1") }), sock);
    await a.listen();
    const b = new DaemonServer(new DaemonSupervisor({ query: fakeQuery }, { dir: join(d, "s2") }), sock);
    await expect(b.listen()).rejects.toThrow(/already running/);
    await a.close();
  });
});
