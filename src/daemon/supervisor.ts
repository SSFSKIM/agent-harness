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
import { listSessions, getSessionMessages } from "../sessions/reader.js";
import { forkSession } from "../sessions/fork.js";
import { renameSession, tagSession, deleteSession } from "../sessions/mutate.js";
import type { CompactOutcome } from "../compaction/server.js";

export interface DaemonDeps {
  query: QueryFn;
  listSessions?: (opts?: Parameters<typeof listSessions>[0]) => Promise<unknown[]>;
  getSessionMessages?: (id: string, opts?: Parameters<typeof getSessionMessages>[1]) => Promise<unknown[]>;
  forkSession?: (id: string, opts?: Parameters<typeof forkSession>[1]) => Promise<{ sessionId: string }>;
  renameSession?: (id: string, title: string, opts?: { cwd?: string }) => Promise<void>;
  tagSession?: (id: string, tag: string | null, opts?: { cwd?: string }) => Promise<void>;
  deleteSession?: (id: string, opts?: { cwd?: string }) => Promise<void>;
}

interface SpawnConfig { model?: string; restart: RestartPolicy; }

/** Owns the in-process session pool + the registry + an idle reaper + crash-recovery restarts. */
export class DaemonSupervisor {
  tasks?: TaskStore; // shared cc-tasks store when `sharedTasks` is set (D3); public for inspection
  private pool = new Map<string, DaemonSession>();
  private proactive = new Map<string, ProactiveLoop>(); // active heartbeats by session id (Phase 2 C)
  private configs = new Map<string, SpawnConfig>();   // per-session config, for re-creation on restart
  private rehydratable = new Set<string>();           // ids claimed at boot, awaiting first-access revival (boot-rehydration)
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
  private contextTool: boolean;
  private compactTool: boolean;

  constructor(private deps: DaemonDeps, opts: DaemonOptions = {}) {
    this.registry = new SessionRegistry({ dir: opts.dir, isAlive: opts.isAlive });
    this.maxSessions = opts.maxSessions ?? 32;
    this.idleTimeoutMs = opts.idleTimeoutMs ?? 30 * 60_000;
    this.now = opts.now ?? Date.now;
    this.restartPolicy = opts.restart ?? "no";
    this.maxRestarts = opts.maxRestarts ?? 5;
    this.backoffMs = opts.backoffMs ?? 500;
    this.maxBackoffMs = opts.maxBackoffMs ?? 30_000;
    this.scheduleRestart = opts.scheduleRestart ?? ((fn, ms) => { const t = setTimeout(fn, ms); (t as any).unref?.(); return () => clearTimeout(t); });
    this.contextTool = opts.contextTool ?? false;
    this.compactTool = opts.compactTool ?? false;
    if (opts.rehydrate) {                              // adopt the prior process's sessions (lazy: no subprocess here)
      for (const rec of this.registry.rehydrate(process.pid)) {
        this.configs.set(rec.id, { model: rec.model, restart: rec.restart ?? this.restartPolicy });
        this.rehydratable.add(rec.id);
        const n = Number(rec.id.replace(/^sess-/, ""));
        if (Number.isFinite(n) && n > this.seq) this.seq = n;    // mint new ids past rehydrated ones → no collision
      }
    } else {
      this.registry.reapStale();                      // default: clear records orphaned by a prior crash
    }
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
    this.registry.register({ id, daemonPid: process.pid, status: "idle", model: opts.model, restart: cfg.restart, createdAt: t, lastActiveAt: t });
    return id;
  }

  async submit(id: string, prompt: string, onMessage: (m: unknown) => void): Promise<{ result: unknown }> {
    const session = this.ensureLive(id);
    if (!session) {
      const rec = this.registry.get(id);
      throw new DaemonError(rec ? `session ${id} is ${rec.status}` : `unknown session ${id}`);
    }
    const loop = this.proactive.get(id);
    if (loop) await loop.pause();                     // human turn preempts the heartbeat
    this.registry.update(id, { status: "busy" });
    try {
      const r = await session.submit(prompt, onMessage);
      this.registry.update(id, { status: "idle", lastActiveAt: session.lastActiveAt, ...(session.sessionId ? { sessionId: session.sessionId } : {}) });
      return r;
    } catch (e) {
      this.registry.update(id, { status: "errored" });
      throw e;
    } finally {
      if (loop && loop.status().state !== "stopped") loop.resume();
    }
  }

  list(): SessionRecord[] { return this.registry.list(); }

  // Persisted on-disk transcripts (SDKSessionInfo / SessionMessage) — DISTINCT from list() (live registry).
  listPersistedSessions(opts: { cwd?: string; limit?: number; offset?: number } = {}): Promise<unknown[]> {
    return (this.deps.listSessions ?? listSessions)(opts);
  }
  getPersistedMessages(id: string, opts: { cwd?: string; limit?: number; offset?: number } = {}): Promise<unknown[]> {
    return (this.deps.getSessionMessages ?? getSessionMessages)(id, opts);
  }
  renamePersisted(id: string, title: string, opts: { cwd?: string } = {}): Promise<void> {
    return (this.deps.renameSession ?? renameSession)(id, title, opts);
  }
  tagPersisted(id: string, tag: string | null, opts: { cwd?: string } = {}): Promise<void> {
    return (this.deps.tagSession ?? tagSession)(id, tag, opts);
  }
  deletePersisted(id: string, opts: { cwd?: string } = {}): Promise<void> {
    return (this.deps.deleteSession ?? deleteSession)(id, opts);
  }

  async control(id: string, frame: ControlFrame): Promise<ControlResponse> {
    const session = this.ensureLive(id);
    if (!session || session.isEnded()) {
      const rec = this.registry.get(id);
      throw new DaemonError(rec ? `session ${id} is ${rec.status}` : `unknown session ${id}`);
    }
    return ControlBridge.apply(session, frame);
  }

  async compact(id: string): Promise<CompactOutcome> {
    const session = this.ensureLive(id);
    if (!session || session.isEnded()) {
      const rec = this.registry.get(id);
      throw new DaemonError(rec ? `session ${id} is ${rec.status}` : `unknown session ${id}`);
    }
    return session.compact();
  }

  async usage(id: string): Promise<unknown> {
    const session = this.ensureLive(id);
    if (!session || session.isEnded()) { const rec = this.registry.get(id); throw new DaemonError(rec ? `session ${id} is ${rec.status}` : `unknown session ${id}`); }
    return session.usage();
  }
  async initializationResult(id: string): Promise<unknown> {
    const session = this.ensureLive(id);
    if (!session || session.isEnded()) { const rec = this.registry.get(id); throw new DaemonError(rec ? `session ${id} is ${rec.status}` : `unknown session ${id}`); }
    return session.initializationResult();
  }
  async applyFlagSettings(id: string, settings: Record<string, unknown>): Promise<void> {
    const session = this.ensureLive(id);
    if (!session || session.isEnded()) { const rec = this.registry.get(id); throw new DaemonError(rec ? `session ${id} is ${rec.status}` : `unknown session ${id}`); }
    await session.applyFlagSettings(settings);
  }

  async fork(id: string): Promise<{ id: string; sessionId: string }> {
    const session = this.ensureLive(id);
    if (!session || session.isEnded()) {
      const rec = this.registry.get(id);
      throw new DaemonError(rec ? `session ${id} is ${rec.status}` : `unknown session ${id}`);
    }
    const sourceSdkId = session.sessionId;   // Spec 1 capture; a live session has it after its first turn
    if (!sourceSdkId) throw new DaemonError(`session ${id} has no session_id yet (take a turn first)`);
    const { sessionId } = await (this.deps.forkSession ?? forkSession)(sourceSdkId);
    const handle = this.spawn({ model: this.configs.get(id)?.model, resume: sessionId }); // new daemon session on the branch
    return { id: handle, sessionId };
  }

  startProactive(id: string, config?: ProactiveConfigInput): ProactiveStatus {
    const session = this.ensureLive(id);
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
    const session = this.pool.get(id);                       // NOT ensureLive — never spawn just to dispose
    if (!session && !this.registry.get(id)) throw new DaemonError(`unknown session ${id}`);
    this.rehydratable.delete(id);                            // drop any pending boot-revival flag
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
    for (const id of this.rehydratable) this.registry.remove(id);   // claimed-not-revived records: forget on graceful shutdown
    this.rehydratable.clear();
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

  /** Return the live session for `id`, reviving it from a boot-claimed record on first access (lazy
   *  rehydration). Returns the pool entry (even if ended — callers still check isEnded()), a freshly
   *  resumed session for a rehydratable id, or undefined when neither exists. */
  private ensureLive(id: string): DaemonSession | undefined {
    const live = this.pool.get(id);
    if (live) return live;
    if (!this.rehydratable.has(id)) return undefined;
    this.rehydratable.delete(id);                                  // revive once
    const rec = this.registry.get(id);
    if (!rec?.sessionId) return undefined;                         // defensive — rehydrate() guaranteed a sessionId
    const cfg = this.configs.get(id) ?? { model: rec.model, restart: this.restartPolicy };
    const s = this.makeSession(id, cfg, rec.sessionId);            // resume the captured sdk session
    this.pool.set(id, s);
    return s;
  }

  private makeSession(id: string, cfg: SpawnConfig, resume?: string): DaemonSession {
    const base: Record<string, unknown> = cfg.model ? { model: cfg.model } : {};
    if (resume) base.resume = resume;                        // spawn hint or captured sdk session id (restart resumes the captured id)
    const extra = this.sessionOptions?.(id);                 // fresh servers + tool posture for THIS session
    const options = extra ? { ...base, ...extra } : base;    // factory keys win; never sets model
    const session = new DaemonSession(id, { query: this.deps.query }, options, this.now, { contextTool: this.contextTool, compactTool: this.compactTool });
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
    const resume = this.registry.get(id)?.sessionId;       // resume the CAPTURED sdk session (context intact); fresh if none
    this.pool.set(id, this.makeSession(id, this.configs.get(id)!, resume));
    this.registry.update(id, { status: "idle", lastActiveAt: this.now() });
  }

  private cancelRestart(id: string): void {
    const cancel = this.restartCancels.get(id);
    if (cancel) { cancel(); this.restartCancels.delete(id); }
  }
}
