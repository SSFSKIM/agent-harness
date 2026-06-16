import { SessionRegistry } from "./registry.js";
import { DaemonSession } from "./session.js";
import { DaemonError } from "./types.js";
import type { DaemonOptions, SessionRecord } from "./types.js";
import type { QueryFn } from "../swarm/types.js";

export interface DaemonDeps { query: QueryFn; }

/** Owns the in-process session pool + the registry + an idle reaper. */
export class DaemonSupervisor {
  private pool = new Map<string, DaemonSession>();
  private registry: SessionRegistry;
  private seq = 0;
  private maxSessions: number;
  private idleTimeoutMs: number;
  private now: () => number;
  private reaper?: ReturnType<typeof setInterval>;

  constructor(private deps: DaemonDeps, opts: DaemonOptions = {}) {
    this.registry = new SessionRegistry({ dir: opts.dir });
    this.maxSessions = opts.maxSessions ?? 32;
    this.idleTimeoutMs = opts.idleTimeoutMs ?? 30 * 60_000;
    this.now = opts.now ?? Date.now;
    this.registry.reapStale(); // clear records orphaned by a prior crash
    if (this.idleTimeoutMs > 0) {
      this.reaper = setInterval(() => { void this.reapIdle(); }, opts.reapEvery ?? 30_000);
      this.reaper.unref?.(); // don't keep the process alive for the reaper
    }
  }

  spawn(opts: { model?: string } = {}): string {
    if (this.pool.size >= this.maxSessions) throw new DaemonError(`max sessions (${this.maxSessions}) reached`);
    const id = `sess-${++this.seq}`;
    const session = new DaemonSession(id, { query: this.deps.query }, opts.model ? { model: opts.model } : {}, this.now);
    this.pool.set(id, session);
    const t = this.now();
    this.registry.register({ id, daemonPid: process.pid, status: "idle", model: opts.model, createdAt: t, lastActiveAt: t });
    return id;
  }

  async submit(id: string, prompt: string, onMessage: (m: unknown) => void): Promise<{ result: unknown }> {
    const session = this.pool.get(id);
    if (!session) throw new DaemonError(`unknown session ${id}`);
    this.registry.update(id, { status: "busy" });
    try {
      const r = await session.submit(prompt, onMessage);
      this.registry.update(id, { status: "idle", lastActiveAt: session.lastActiveAt });
      return r;
    } catch (e) {
      this.registry.update(id, { status: "errored" });
      throw e;
    }
  }

  list(): SessionRecord[] { return this.registry.list(); }

  async stop(id: string): Promise<void> {
    const session = this.pool.get(id);
    if (!session) throw new DaemonError(`unknown session ${id}`);
    await session.dispose();
    this.pool.delete(id);
    this.registry.remove(id);
  }

  async shutdown(): Promise<void> {
    if (this.reaper) clearInterval(this.reaper);
    await Promise.all([...this.pool].map(async ([id, s]) => { await s.dispose(); this.registry.remove(id); }));
    this.pool.clear();
  }

  /** Stop sessions whose last activity is older than the idle timeout. Public + async so the reaper
   * fires it (void) and tests can await it deterministically. */
  async reapIdle(): Promise<void> {
    const cutoff = this.now() - this.idleTimeoutMs;
    const stale = [...this.pool].filter(([, s]) => s.lastActiveAt < cutoff).map(([id]) => id);
    await Promise.all(stale.map((id) => this.stop(id)));
  }
}
