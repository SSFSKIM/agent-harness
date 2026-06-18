import { daemonRequest } from "./client.js";
import type { ListEntry, RestartPolicy } from "./types.js";
import type { ControlFrame, ControlResponse } from "../bridge/types.js";
import type { CompactOutcome } from "../compaction/index.js";
import type { ProactiveStatus, ProactiveConfigInput } from "../proactive/types.js";

/** The minimal daemon-read surface collect() needs (injected → unit-testable without a socket). */
export interface MonitorClient {
  list(): Promise<ListEntry[]>;
  contextUsage(id: string): Promise<unknown>;
}

/** The full operator client: the read subset + the drive ops. Each method wraps daemonRequest with the
 *  matching op and throws on { ok:false } — EXCEPT control(), which returns the raw ControlResponse so the
 *  UI can surface { ok:false, error } itself. */
export interface DaemonClient extends MonitorClient {
  submit(id: string, prompt: string, onChunk: (m: unknown) => void): Promise<{ result: unknown }>;
  control(id: string, frame: ControlFrame): Promise<ControlResponse>;
  compact(id: string): Promise<CompactOutcome>;
  spawn(opts?: { model?: string; restart?: RestartPolicy; resume?: string }): Promise<string>;
  stop(id: string): Promise<void>;
  fork(id: string): Promise<{ id: string; sessionId?: string }>;
  startProactive(id: string, config?: ProactiveConfigInput): Promise<ProactiveStatus>;
  stopProactive(id: string): Promise<void>;
}

export type RequestFn = (socketPath: string, op: unknown, onLine?: (o: unknown) => void) => Promise<any[]>;

/** Typed client over the daemon UDS op protocol — a thin wrapper over the already-public daemonRequest
 *  (no protocol duplication). The transport is injectable for unit tests; defaults to the real socket. */
export function connectDaemon(socketPath: string, request: RequestFn = daemonRequest): DaemonClient {
  const one = async (op: unknown): Promise<any> => {
    const [res] = await request(socketPath, op);
    if (!res?.ok) throw new Error(res?.error ?? "daemon op failed");
    return res;
  };
  return {
    async list() { return (await one({ op: "list" })).sessions as ListEntry[]; },
    async contextUsage(id) { return (await one({ op: "control", id, frame: { type: "context_usage" } })).usage; },
    async control(id, frame) { const [res] = await request(socketPath, { op: "control", id, frame }); return res as ControlResponse; },
    async submit(id, prompt, onChunk) {
      const lines = await request(socketPath, { op: "submit", id, prompt }, (o: any) => { if (o?.type === "chunk") onChunk(o.message); });
      const done = lines.find((l: any) => l?.type === "done");
      if (!done) { const err = lines.find((l: any) => l && l.ok === false); throw new Error(err?.error ?? "submit produced no result"); }
      return { result: done.result };
    },
    async compact(id) { return (await one({ op: "compact", id })).outcome as CompactOutcome; },
    async spawn(opts) { return (await one({ op: "spawn", ...(opts ?? {}) })).id as string; },
    async stop(id) { await one({ op: "stop", id }); },
    async fork(id) { const r = await one({ op: "fork", id }); return { id: r.id, sessionId: r.sessionId }; },
    async startProactive(id, config) { return (await one({ op: "start_proactive", id, ...(config ? { config } : {}) })).status as ProactiveStatus; },
    async stopProactive(id) { await one({ op: "stop_proactive", id }); },
  };
}
