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

  it("two sessions collaborate through one shared task store (sharedTasks)", async () => {
    const d = mkdtempSync(join(tmpdir(), "cc-daemon-shared-"));
    const sock = join(d, "sock");
    const sup = new DaemonSupervisor({ query }, { dir: join(d, "sessions"), sharedTasks: { dir: join(d, "tasks") } });
    const server = new DaemonServer(sup, sock);
    await server.listen();

    const a = (await daemonRequest(sock, { op: "spawn" }))[0].id;
    const b = (await daemonRequest(sock, { op: "spawn" }))[0].id;

    // Session A creates a task via the cc-tasks MCP tool...
    await daemonRequest(sock, { op: "submit", id: a,
      prompt: "Use the TaskCreate tool to create a task with subject SHARED_OK. Then stop. Do not ask me anything." });
    // ...and it lands in the one shared store.
    const direct = await sup.tasks!.list();
    expect(direct.map((t) => t.subject)).toContain("SHARED_OK");

    // Session B sees it through its own fresh cc-tasks server over the same store.
    const lines: any[] = [];
    await daemonRequest(sock, { op: "submit", id: b,
      prompt: "Call the TaskList tool and report the subjects of all tasks. Do not ask me anything." },
      (o) => lines.push(o));
    const done = lines.find((l) => l.type === "done");
    expect(String(done?.result)).toMatch(/SHARED_OK/i);

    await daemonRequest(sock, { op: "shutdown" });
    await server.closed;
  }, 120_000);
});
