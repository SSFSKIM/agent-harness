import type { ListEntry } from "../daemon/types.js";
import type { ProactiveState } from "../proactive/types.js";
import type { MonitorClient } from "../daemon/connect.js";
import type { PendingEntry } from "../daemon/permissions.js";

/** Re-exported so existing importers (app.ts, client.ts, tests) keep their `./snapshot.js` import. */
export type { MonitorClient } from "../daemon/connect.js";
export type { PendingEntry } from "../daemon/permissions.js";

export interface SessionRow {
  id: string;
  status: ListEntry["status"];
  model?: string;
  ctxPercent?: number;   // computed from totalTokens/maxTokens; undefined when not derivable
  tokens?: number;       // totalTokens from the context_usage payload
  createdAt: number;
  proactive?: ProactiveState;
}

export interface DashboardSnapshot {
  daemonUp: boolean;
  sessions: SessionRow[];
  proactive?: ProactiveState;  // highest-priority proactive state across sessions
  at: number;                  // collection timestamp (drives age rendering)
  socketPath?: string;
  pending: PendingEntry[];     // parked permission requests awaiting a human decision (increment 4)
}

export interface CollectOpts { now: () => number; socketPath?: string; }

const PROACTIVE_PRIORITY: ProactiveState[] = ["running", "paused", "stopped", "idle"];
function aggregateProactive(states: (ProactiveState | undefined)[]): ProactiveState | undefined {
  const present = states.filter((s): s is ProactiveState => s !== undefined);
  if (!present.length) return undefined;
  return PROACTIVE_PRIORITY.find((p) => present.includes(p));
}

/** Poll the daemon once: list the pool, then fetch per-session context usage. Never throws — a dead daemon
 *  yields { daemonUp: false }; a per-session usage failure leaves that row's ctx undefined. */
export async function collect(client: MonitorClient, opts: CollectOpts): Promise<DashboardSnapshot> {
  let entries: ListEntry[];
  try { entries = await client.list(); }
  catch { return { daemonUp: false, sessions: [], proactive: undefined, at: opts.now(), socketPath: opts.socketPath, pending: [] }; }
  const sessions: SessionRow[] = [];
  for (const e of entries) {
    let ctxPercent: number | undefined, tokens: number | undefined;
    if (e.status !== "errored") {
      try {
        const u = (await client.contextUsage(e.id)) as { totalTokens?: number; maxTokens?: number } | undefined;
        tokens = typeof u?.totalTokens === "number" ? u.totalTokens : undefined;
        ctxPercent = u && typeof u.totalTokens === "number" && typeof u.maxTokens === "number" && u.maxTokens > 0
          ? Math.round((u.totalTokens / u.maxTokens) * 100) : undefined;
      } catch { /* per-session failure → leave ctx/tokens undefined */ }
    }
    sessions.push({ id: e.id, status: e.status, model: e.model, ctxPercent, tokens, createdAt: e.createdAt, proactive: e.proactive?.state });
  }
  let pending: PendingEntry[] = [];
  try { pending = client.pendingPermissions ? await client.pendingPermissions() : []; }
  catch { /* a pending-fetch failure must not break the snapshot */ }
  return { daemonUp: true, sessions, proactive: aggregateProactive(sessions.map((r) => r.proactive)), at: opts.now(), socketPath: opts.socketPath, pending };
}
