import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DaemonSupervisor } from "../../src/daemon/supervisor.js";
import { DaemonServer } from "../../src/daemon/server.js";
import { daemonRequest } from "../../src/daemon/client.js";

const tmp = () => mkdtempSync(join(tmpdir(), "cc-daemon-"));
function fakeQuery({ prompt }: any) {
  return (async function* () { for await (const t of prompt) yield { type: "result", result: "did:" + t.message.content }; })();
}

describe("list response carries proactive status", () => {
  it("a session with no proactive loop has proactive=undefined; a started loop reports a state string", async () => {
    const d = tmp(); const sock = join(d, "sock");
    const sup = new DaemonSupervisor({ query: fakeQuery }, { dir: join(d, "sessions") });
    const server = new DaemonServer(sup, sock);
    await server.listen();

    const a = (await daemonRequest(sock, { op: "spawn" }))[0].id;
    const b = (await daemonRequest(sock, { op: "spawn" }))[0].id;
    // start a proactive loop on `a` with a 1h interval so no tick fires during the test
    await daemonRequest(sock, { op: "start_proactive", id: a, config: { intervalMs: 3_600_000 } });

    const { sessions } = (await daemonRequest(sock, { op: "list" }))[0];
    const ea = sessions.find((s: any) => s.id === a);
    const eb = sessions.find((s: any) => s.id === b);
    expect(typeof ea.proactive?.state).toBe("string"); // loop present → a ProactiveStatus
    expect(eb.proactive).toBeUndefined();               // no loop → field absent

    await daemonRequest(sock, { op: "stop_proactive", id: a });
    await daemonRequest(sock, { op: "shutdown" });
    await server.closed;
  });
});
