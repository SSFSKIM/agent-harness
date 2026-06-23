import { describe, it, expect } from "vitest";
import { query } from "@anthropic-ai/claude-agent-sdk";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DaemonSupervisor } from "../../src/daemon/supervisor.js";
import { DaemonServer } from "../../src/daemon/server.js";
import { daemonRequest } from "../../src/daemon/client.js";

const live = (process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_CODE_OAUTH_TOKEN) ? describe : describe.skip;

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

  it("control-plane drives a live session: initialize, set_model, set_thinking, interrupt", async () => {
    const d = mkdtempSync(join(tmpdir(), "cc-daemon-ctl-"));
    const sock = join(d, "sock");
    const sup = new DaemonSupervisor({ query }, { dir: join(d, "sessions") });
    const server = new DaemonServer(sup, sock);
    await server.listen();
    const id = (await daemonRequest(sock, { op: "spawn" }))[0].id;

    // initialize → real capability menus
    const init = (await daemonRequest(sock, { op: "control", id, frame: { type: "initialize" } }))[0];
    expect(init.ok).toBe(true);
    expect(Array.isArray(init.models) && init.models.length > 0).toBe(true);
    expect(Array.isArray(init.commands)).toBe(true);

    // set_model (to a model the SDK itself reports) + set_thinking → { ok: true }
    const model = init.models[0].value as string;
    expect((await daemonRequest(sock, { op: "control", id, frame: { type: "set_model", model } }))[0].ok).toBe(true);
    expect((await daemonRequest(sock, { op: "control", id, frame: { type: "set_thinking", maxTokens: null } }))[0].ok).toBe(true);

    // interrupt a long turn started on a SEPARATE connection → submit must settle (no hang)
    const submitP = daemonRequest(sock, { op: "submit", id, prompt: "Slowly count from 1 to 300, one number per line." }, () => {});
    await new Promise((r) => setTimeout(r, 1500));
    expect((await daemonRequest(sock, { op: "control", id, frame: { type: "interrupt" } }))[0].ok).toBe(true);
    await submitP.catch(() => {}); // resolves or rejects, but must not hang

    await daemonRequest(sock, { op: "shutdown" });
    await server.closed;
  }, 120_000);

  it("proactive heartbeat self-wakes a real session (a tick fires with no human turn)", async () => {
    const d = mkdtempSync(join(tmpdir(), "cc-daemon-proactive-"));
    const sock = join(d, "sock");
    const sup = new DaemonSupervisor({ query }, { dir: join(d, "sessions"), sharedTasks: { dir: join(d, "tasks") } });
    const server = new DaemonServer(sup, sock);
    await server.listen();
    const id = (await daemonRequest(sock, { op: "spawn" }))[0].id;

    // A tick with an OBSERVABLE side effect: create a task, then report IDLE. High stopAfterIdle so it keeps ticking.
    const started = (await daemonRequest(sock, {
      op: "start_proactive", id,
      config: {
        tickPrompt: "Use the TaskCreate tool to create a task with subject HEARTBEAT_TICK. Then reply with exactly IDLE.",
        intervalMs: 1500,
        idleBackoff: { stopAfterIdle: 100 },
      },
    }))[0];
    expect(started.ok).toBe(true);
    expect(started.status.state).toBe("running");

    // No human submits at all — if a tick fires, the shared store gains a HEARTBEAT_TICK task.
    const sawTick = await new Promise<boolean>((resolve) => {
      const t0 = Date.now();
      const poll = async () => {
        const items = await sup.tasks!.list();
        if (items.some((t) => /HEARTBEAT_TICK/i.test(t.subject))) return resolve(true);
        if (Date.now() - t0 > 60_000) return resolve(false);
        setTimeout(poll, 2000);
      };
      void poll();
    });
    expect(sawTick).toBe(true); // a real heartbeat tick ran with no human in the loop

    // Clean teardown of the control plane.
    expect((await daemonRequest(sock, { op: "stop_proactive", id }))[0].ok).toBe(true);
    await daemonRequest(sock, { op: "shutdown" });
    await server.closed;
  }, 120_000);
});
