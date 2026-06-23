#!/usr/bin/env node
import { realpathSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { Peer } from "./peer.js";
import { AppServer } from "./handlers.js";
import { parseConfigFlags } from "./posture.js";
import { fakeOpen } from "./_fake.js";

export function runServer(io: { stdin: NodeJS.ReadableStream; stdout: { write(s: string): void }; argv: string[]; onExit?: () => void }) {
  const { autoReview, network } = parseConfigFlags(io.argv);
  const sink = (o: object) => io.stdout.write(JSON.stringify(o) + "\n");      // ONE NDJSON line; never console.log
  const open = process.env.CC_APPSERVER_FAKE === "1" ? fakeOpen : undefined;  // key-free path for tests
  let server!: AppServer;
  const peer = new Peer(sink, (m, p, id) => server.handleRequest(m, p, id), (_m, _p) => { /* initialized: noop */ });
  server = new AppServer(peer, { autoReview, network, open });
  io.stdin.on("data", (c) => peer.feed(c));
  const shutdown = async () => { try { await server.disposeAll(); } catch {} io.onExit?.(); };
  io.stdin.on("end", () => { void shutdown(); });
  return { peer, shutdown };
}

// Only auto-run when invoked as the binary (not when imported by a test).
// Realpath argv[1] before comparing: an npm bin is always a symlink, and Node keeps
// the symlink path in argv[1] while import.meta.url is the module's realpath — so a
// bare `file://${argv[1]}` compare fails for any installed/linked bin and the server
// silently never starts. Resolving both to a canonical file URL makes the guard hold
// whether invoked as `node dist/bin.js` or via a PATH-linked `cc-codex-appserver`.
const entry = process.argv[1] ? pathToFileURL(realpathSync(process.argv[1])).href : "";
if (import.meta.url === entry) {
  process.stdin.resume();
  const { shutdown } = runServer({ stdin: process.stdin, stdout: process.stdout, argv: process.argv.slice(2), onExit: () => process.exit(0) });
  process.on("SIGINT", () => void shutdown());
  process.on("SIGTERM", () => void shutdown());
}
