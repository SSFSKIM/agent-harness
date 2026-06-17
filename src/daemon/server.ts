import { createServer, connect } from "node:net";
import type { Server, Socket } from "node:net";
import { existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname } from "node:path";
import { daemonOp } from "./types.js";
import type { DaemonSupervisor } from "./supervisor.js";

/** UDS listener speaking the NDJSON op protocol; routes ops to a DaemonSupervisor. */
export class DaemonServer {
  private server: Server;
  private closeResolve!: () => void;
  private closing = false;        // idempotency guard for close()
  private shuttingDown = false;   // stop accepting new ops once a shutdown is in progress
  readonly closed: Promise<void> = new Promise((r) => { this.closeResolve = r; });

  constructor(private supervisor: DaemonSupervisor, private socketPath: string) {
    this.server = createServer((sock) => this.onConnection(sock));
  }

  async listen(): Promise<void> {
    await this.ensureFreeSocket();
    mkdirSync(dirname(this.socketPath), { recursive: true, mode: 0o700 });
    await new Promise<void>((resolve, reject) => {
      const onErr = (e: Error) => reject(e);
      this.server.once("error", onErr);
      this.server.listen(this.socketPath, () => { this.server.off("error", onErr); resolve(); });
    });
  }

  async close(): Promise<void> {
    if (this.closing) return;
    this.closing = true;
    await new Promise<void>((resolve) => this.server.close(() => resolve()));
    rmSync(this.socketPath, { force: true });
    this.closeResolve();
  }

  /** Single-daemon invariant: refuse if a live daemon answers; clear a stale socket otherwise. */
  private async ensureFreeSocket(): Promise<void> {
    if (!existsSync(this.socketPath)) return;
    const alive = await new Promise<boolean>((resolve) => {
      const c = connect(this.socketPath)
        .on("connect", () => { c.destroy(); resolve(true); })
        .on("error", () => resolve(false));
    });
    if (alive) throw new Error(`daemon already running at ${this.socketPath}`);
    rmSync(this.socketPath, { force: true });
  }

  private onConnection(sock: Socket): void {
    let buf = "";
    const onData = (d: Buffer) => {
      buf += d.toString("utf8");
      const nl = buf.indexOf("\n");
      if (nl < 0) return;
      sock.off("data", onData);              // one op per connection (first line)
      void this.handle(sock, buf.slice(0, nl));
    };
    sock.on("data", onData);
    sock.on("error", () => {});               // ignore client-side resets
  }

  private async handle(sock: Socket, line: string): Promise<void> {
    const send = (o: unknown) => sock.write(JSON.stringify(o) + "\n");
    let op;
    try { op = daemonOp.parse(JSON.parse(line)); }
    catch (e) { send({ ok: false, error: `bad request: ${(e as Error).message}` }); sock.end(); return; }
    if (this.shuttingDown) { send({ ok: false, error: "daemon shutting down" }); sock.end(); return; }
    try {
      switch (op.op) {
        case "spawn": send({ ok: true, id: this.supervisor.spawn({ model: op.model, restart: op.restart, resume: op.resume }) }); sock.end(); break;
        case "list": send({ ok: true, sessions: this.supervisor.list() }); sock.end(); break;
        case "sessions": send({ ok: true, sessions: await this.supervisor.listPersistedSessions({ cwd: op.cwd, limit: op.limit, offset: op.offset }) }); sock.end(); break;
        case "messages": send({ ok: true, messages: await this.supervisor.getPersistedMessages(op.id, { cwd: op.cwd, limit: op.limit, offset: op.offset }) }); sock.end(); break;
        case "control": send(await this.supervisor.control(op.id, op.frame)); sock.end(); break;
        case "compact": send({ ok: true, outcome: await this.supervisor.compact(op.id) }); sock.end(); break;
        case "start_proactive": send({ ok: true, status: this.supervisor.startProactive(op.id, op.config) }); sock.end(); break;
        case "stop_proactive": send(await this.supervisor.stopProactive(op.id)); sock.end(); break;
        case "stop": await this.supervisor.stop(op.id); send({ ok: true }); sock.end(); break;
        case "submit": {
          const r = await this.supervisor.submit(op.id, op.prompt, (m) => send({ type: "chunk", message: m }));
          send({ type: "done", result: r.result }); sock.end(); break;
        }
        case "shutdown":
          this.shuttingDown = true; // set before any await → concurrent ops are refused, none escape cleanup
          send({ ok: true }); sock.end();
          await this.supervisor.shutdown();
          await this.close();
          break;
      }
    } catch (e) { send({ ok: false, error: (e as Error).message }); sock.end(); }
  }
}
