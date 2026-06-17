#!/usr/bin/env node
import { query as sdkQuery } from "@anthropic-ai/claude-agent-sdk";
import { parseArgs, composePrompt } from "./cliArgs.js";
import { createHarness } from "./harness.js";
import { DaemonSupervisor } from "./daemon/supervisor.js";
import { DaemonServer } from "./daemon/server.js";
import { daemonRequest } from "./daemon/client.js";
import { daemonSocketPath } from "./daemon/paths.js";

async function readStdin(): Promise<string | undefined> {
  if (process.stdin.isTTY) return undefined;
  const chunks: Buffer[] = [];
  for await (const c of process.stdin) chunks.push(c as Buffer);
  const s = Buffer.concat(chunks).toString("utf8");
  return s.trim() ? s : undefined;
}

async function runDaemon(): Promise<void> {
  const sock = daemonSocketPath();
  const sup = new DaemonSupervisor({ query: sdkQuery }, {});
  const server = new DaemonServer(sup, sock);
  await server.listen();
  let stopping = false;
  const stop = async () => {
    if (stopping) return; // a second signal (e.g. double Ctrl-C) is a no-op
    stopping = true;
    await sup.shutdown().catch(() => {});
    await server.close().catch(() => {});
  };
  process.on("SIGINT", stop);
  process.on("SIGTERM", stop);
  console.error(`cc-harness daemon listening at ${sock}`);
  await server.closed; // resolves on `shutdown` op or signal
}

/** Daemon subcommands (daemon / daemon stop / ps / submit). Returns true if handled. */
async function daemonCli(args: string[]): Promise<boolean> {
  const sock = daemonSocketPath();
  if (args[0] === "daemon" && args[1] === "stop") { await daemonRequest(sock, { op: "shutdown" }); return true; }
  if (args[0] === "daemon") { await runDaemon(); return true; }
  if (args[0] === "ps") {
    const [{ sessions }] = await daemonRequest(sock, { op: "list" });
    for (const s of sessions) console.log(`${s.id}\t${s.status}\t${s.model ?? "-"}`);
    return true;
  }
  if (args[0] === "submit") {
    await daemonRequest(sock, { op: "submit", id: args[1], prompt: args.slice(2).join(" ") }, (o: any) => {
      if (o.type === "chunk") { for (const b of o.message?.message?.content ?? []) if (b.type === "text") process.stdout.write(b.text); }
      else if (o.type === "done") process.stdout.write("\n");
    });
    return true;
  }
  return false;
}

async function main() {
  if (await daemonCli(process.argv.slice(2))) return;
  const { prompt: argPrompt, config } = parseArgs(process.argv.slice(2));
  const stdin = await readStdin();
  const prompt = composePrompt(argPrompt, stdin);
  if (!prompt) { console.error("usage: cc-harness \"<prompt>\" [--model ...] [--output-style ...]"); process.exit(2); }

  const harness = createHarness({ permissionMode: "bypassPermissions", ...config });
  for await (const m of harness.stream(prompt)) {
    const mm = m as any;
    if (mm.type === "assistant") {
      for (const block of mm.message?.content ?? []) if (block.type === "text") process.stdout.write(block.text);
    } else if (mm.type === "result") {
      process.stdout.write("\n");
    }
  }
}
main().catch((e) => { console.error(e); process.exit(1); });
