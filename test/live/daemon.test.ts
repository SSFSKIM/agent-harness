import { describe, it, expect } from "vitest";
import { query } from "@anthropic-ai/claude-agent-sdk";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DaemonSupervisor } from "../../src/daemon/supervisor.js";
import { DaemonServer } from "../../src/daemon/server.js";
import { daemonRequest } from "../../src/daemon/client.js";

const live = process.env.ANTHROPIC_API_KEY ? describe : describe.skip;

live("live daemon (real SDK)", () => {
  it("hosts a real session: spawn → submit → streamed PONG result", async () => {
    const d = mkdtempSync(join(tmpdir(), "cc-daemon-live-"));
    const sock = join(d, "sock");
    const sup = new DaemonSupervisor({ query }, { dir: join(d, "sessions") });
    const server = new DaemonServer(sup, sock);
    await server.listen();

    const id = (await daemonRequest(sock, { op: "spawn" }))[0].id;
    const lines: any[] = [];
    await daemonRequest(
      sock,
      { op: "submit", id, prompt: "Reply with exactly the single word PONG and nothing else. Do not use any tools." },
      (o) => lines.push(o),
    );
    const done = lines.find((l) => l.type === "done");
    expect(String(done?.result)).toMatch(/PONG/i);

    await daemonRequest(sock, { op: "shutdown" });
    await server.closed;
  }, 60_000);
});
