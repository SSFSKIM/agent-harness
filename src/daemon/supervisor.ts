import { SessionRegistry } from "./registry.js";
import { DaemonSession } from "./session.js";
import { DaemonError } from "./types.js";
import type { DaemonOptions, RestartPolicy, SessionRecord } from "./types.js";
import type { QueryFn } from "../swarm/types.js";
import { TaskStore } from "../tasks/store.js";
import { createTaskMcpServer } from "../tasks/server.js";
import { NATIVE_TASK_TOOLS } from "../swarm/coordinator.js";
import { ControlBridge } from "../bridge/control.js";
import type { ControlFrame, ControlResponse } from "../bridge/types.js";
import { ProactiveLoop } from "../proactive/loop.js";
import { resolveProactiveConfig } from "../proactive/types.js";
import type { ProactiveConfigInput, ProactiveStatus } from "../proactive/types.js";
import { defaultIdleDetector } from "../proactive/prompts.js";

export interface DaemonDeps { query: QueryFn; }

interface SpawnConfig { model?: string; restart: RestartPolicy; }

/** Owns the in-process session pool + the registry + an idle reaper + crash-recovery restarts. */
export class DaemonSupervisor {
  tasks?: TaskStore; // shared cc-tasks store when `sharedTasks` is set (D3); public for inspection
  private pool = new Map<string, DaemonSession>();
  private proactive = new Map<string, ProactiveLoop>(); // active heartbeats by session id (Phase 2 C)
  private configs = new Map<string, SpawnConfig>();   // per-session config, for re-creation on restart
  private registry: SessionRegistry;
  private seq = 0;
  private maxSessions: number;
  private idleTimeoutMs: number;
  private now: () => number;
  private reaper?: ReturnType<typeof setInterval>;
  // restart machinery
  private restartPolicy: RestartPolicy;
  private maxRestarts: number;
  private backoffMs: number;
  private maxBackoffMs: number;
  private scheduleRestart: (fn: () => void, ms: number) => () => void;
  private restartCancels = new Map<string, () => void>(); // pending restart cancellers, by id
  private stopping = new Set<string>();                   // ids being intentionally torn down
  private shuttingDown = false;
  private sessionOptions?: (sessionId: string) => Record<string, unknown>; // per-session options factory (D3)

  constructor(private deps: DaemonDeps, opts: DaemonOptions = {}) {
    this.registry = new SessionRegistry({ dir: opts.dir });
    this.maxSessions = opts.maxSessions ?? 32;
    this.idleTimeoutMs = opts.idleTimeoutMs ?? 30 * 60_000;
    this.now = opts.now ?? Date.now;
    this.restartPolicy = opts.restart ?? "no";
    this.maxRestarts = opts.maxRestarts ?? 5;
    this.backoffMs = opts.backoffMs ?? 500;
    this.maxBackoffMs = opts.maxBackoffMs ?? 30_000;
    this.scheduleRestart = opts.scheduleRestart ?? ((fn, ms) => { const t = setTimeout(fn, ms); (t as any).unref?.(); return () => clearTimeout(t); });
    this.registry.reapStale(); // clear records orphaned by a prior crash
    if (this.idleTimeoutMs > 0) {
      this.reaper = setInterval(() => { void this.reapIdle(); }, opts.reapEvery ?? 30_000);
      this.reaper.unref?.();
    }
    const CC_TASKS_TOOLS = ["TaskCreate", "TaskUpdate", "TaskGet", "TaskList"].map((t) => `mcp__cc-tasks__${t}`);
    if (opts.sharedTasks) {
      const t = opts.sharedTasks === true ? {} : opts.sharedTasks;
      this.tasks = new TaskStore({ dir: t.dir, listId: t.listId }); // TaskStore defaults the rest
      this.sessionOptions = opts.sessionOptions ?? (() => ({
        mcpServers: { "cc-tasks": createTaskMcpServer(this.tasks!) }, // FRESH instance per call
        disallowedTools: [...NATIVE_TASK_TOOLS],                      // native task tools off → cc-tasks authoritative
        allowedTools: CC_TASKS_TOOLS,                                // auto-approve the cc-tasks tools
      }));
    } else {
      this.sessionOptions = opts.sessionOptions;
    }
  }

  spawn(opts: { model?: string; restart?: RestartPolicy; resume?: string } = {}): string {
    if (this.pool.size >= this.maxSessions) throw new DaemonError(`max sessions (${this.maxSessions}) reached`);
    const id = `sess-${++this.seq}`;
    const cfg: SpawnConfig = { model: opts.model, restart: opts.restart ?? this.restartPolicy };
    this.configs.set(id, cfg);
    this.pool.set(id, this.makeSession(id, cfg, opts.resume));
    const t = this.now();
    this.registry.register({ id, daemonPid: process.pid, status: "idle", model: opts.model, createdAt: t, lastActiveAt: t });
    return id;
  }

  async submit(id: string, prompt: string, onMessage: (m: unknown) => void): Promise<{ result: unknown }> {
    const session = this.pool.get(id);
    if (!session) {
      const rec = this.registry.get(id);
      throw new DaemonError(rec ? `session ${id} is ${rec.status}` : `unknown session ${id}`);
    }
    const loop = this.proactive.get(id);
    if (loop) await loop.pause();                     // human turn preempts the heartbeat
    this.registry.update(id, { status: "busy" });
    try {
      const r = await session.submit(prompt, onMessage);
      this.registry.update(id, { status: "idle", lastActiveAt: session.lastActiveAt });
      return r;
    } catch (e) {
      this.registry.update(id, { status: "errored" });
      throw e;
    } finally {
      if (loop && loop.status().state !== "stopped") loop.resume();
    }
  }

  list(): SessionRecord[] { return this.registry.list(); }

  async control(id: string, frame: ControlFrame): Promise<ControlResponse> {
    const session = this.pool.get(id);
    if (!session || session.isEnded()) {
      const rec = this.registry.get(id);
      throw new DaemonError(rec ? `session ${id} is ${rec.status}` : `unknown session ${id}`);
    }
    return ControlBridge.apply(session, frame);
  }

  startProactive(id: string, config?: ProactiveConfigInput): ProactiveStatus {
    const session = this.pool.get(id);
    if (!session || session.isEnded()) {
      const rec = this.registry.get(id);
      throw new DaemonError(rec ? `session ${id} is ${rec.status}` : `unknown session ${id}`);
    }
    if (this.proactive.has(id)) throw new DaemonError(`session ${id} already proactive`);
    const loop = new ProactiveLoop(resolveProactiveConfig(config), {
      runTurn: (p) => this.runProactiveTurn(id, p),
      schedule: this.scheduleRestart,                 // reuse the injected scheduler
      idleDetector: defaultIdleDetector,
      interrupt: () => session.interrupt(),           // bridge.interrupt pauses an in-flight tick
    });
    this.proactive.set(id, loop);
    loop.start();
    return loop.status();
  }

  async stopProactive(id: string): Promise<{ ok: true }> {
    const loop = this.proactive.get(id);
    if (!loop) throw new DaemonError(`session ${id} is not proactive`);
    await loop.stop("stopped");
    this.proactive.delete(id);
    return { ok: true };
  }

  proactiveStatus(id: string): ProactiveStatus | undefined { return this.proactive.get(id)?.status(); }

  private runProactiveTurn(id: string, prompt: string): Promise<{ result: unknown }> {
    const session = this.pool.get(id);
    if (!session || session.isEnded()) {
      const rec = this.registry.get(id);
      throw new DaemonError(rec ? `session ${id} is ${rec.status}` : `unknown session ${id}`);
    }
    return session.submit(prompt, () => {});          // tick output discarded; result drives idleDetector
  }

  async stop(id: string): Promise<void> {
    const session = this.pool.get(id);
    if (!session && !this.registry.get(id)) throw new DaemonError(`unknown session ${id}`);
    const loop = this.proactive.get(id);
    if (loop) { await loop.stop("session stopped"); this.proactive.delete(id); }
    this.stopping.add(id);                       // flag BEFORE dispose so the end hook won't restart
    this.cancelRestart(id);
    if (session) await session.dispose();
    this.pool.delete(id);
    this.configs.delete(id);
    this.registry.remove(id);
    this.stopping.delete(id);
  }

  async shutdown(): Promise<void> {
    this.shuttingDown = true;                    // end hooks early-return from here on
    if (this.reaper) clearInterval(this.reaper);
    for (const cancel of this.restartCancels.values()) cancel();
    this.restartCancels.clear();
    await Promise.all([...this.proactive.values()].map((l) => l.stop("shutdown")));
    this.proactive.clear();
    await Promise.all([...this.pool].map(async ([id, s]) => { await s.dispose(); this.registry.remove(id); }));
    this.pool.clear();
    this.configs.clear();
  }

  /** Stop sessions whose last activity is older than the idle timeout. */
  async reapIdle(): Promise<void> {
    const cutoff = this.now() - this.idleTimeoutMs;
    const stale = [...this.pool].filter(([id, s]) => {
      const loop = this.proactive.get(id);
      const heartbeatActive = loop !== undefined && loop.status().state !== "stopped";
      return !heartbeatActive && s.lastActiveAt < cutoff;
    }).map(([id]) => id);
    await Promise.all(stale.map((id) => this.stop(id)));
  }

  // ---- restart machinery ----

  private makeSession(id: string, cfg: SpawnConfig, resume?: string): DaemonSession {
    const base: Record<string, unknown> = cfg.model ? { model: cfg.model } : {};
    if (resume) base.resume = resume;                        // initial spawn only; restart() omits it (stays fresh)
    const extra = this.sessionOptions?.(id);                 // fresh servers + tool posture for THIS session
    const options = extra ? { ...base, ...extra } : base;    // factory keys win; never sets model
    const session = new DaemonSession(id, { query: this.deps.query }, options, this.now);
    session.done.then(() => this.handleSessionEnd(id)).catch(() => {}); // end hook
    return session;
  }

  /** Fires when a session's query ends. Restart only on an UNEXPECTED death (the core invariant). */
  private handleSessionEnd(id: string): void {
    if (this.shuttingDown || this.stopping.has(id)) return;     // intentional end — never restart
    const cfg = this.configs.get(id);
    if (!cfg || cfg.restart !== "on-failure") { this.registry.update(id, { status: "errored" }); return; }
    const restarts = (this.registry.get(id)?.restarts ?? 0) + 1;
    if (restarts > this.maxRestarts) { this.registry.update(id, { status: "errored", restarts }); return; }
    this.pool.delete(id);                                       // not submittable during the backoff window
    this.registry.update(id, { status: "restarting", restarts });
    const delay = Math.min(this.backoffMs * 2 ** (restarts - 1), this.maxBackoffMs);
    const cancel = this.scheduleRestart(() => this.restart(id), delay);
    // A synchronous scheduler can run restart() before this line — only keep the canceller if a
    // restart is still actually pending (status is back to "idle" once restart() has run).
    if (this.registry.get(id)?.status === "restarting") this.restartCancels.set(id, cancel);
    else cancel();
  }

  private restart(id: string): void {
    this.restartCancels.delete(id);
    if (this.shuttingDown || this.stopping.has(id) || !this.configs.has(id)) return; // stopped during backoff
    this.pool.set(id, this.makeSession(id, this.configs.get(id)!));
    this.registry.update(id, { status: "idle", lastActiveAt: this.now() });
  }

  private cancelRestart(id: string): void {
    const cancel = this.restartCancels.get(id);
    if (cancel) { cancel(); this.restartCancels.delete(id); }
  }
}
