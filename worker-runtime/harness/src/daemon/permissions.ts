// harness/src/daemon/permissions.ts
import type { PermissionBroker, PermissionDecision, PermissionRequest } from "../permissions/types.js";

/** A parked permission request on the wire — the serializable view of a PermissionRequest (no AbortSignal). */
export interface PendingEntry {
  sessionId: string;
  toolUseID: string;
  toolName: string;
  input: Record<string, unknown>;
  title?: string;
  displayName?: string;
  description?: string;
  createdAt: number;
}

export interface PendingPermissionsOpts {
  timeoutMs?: number;                                    // park lifetime before auto-deny (default 30_000)
  now?: () => number;                                    // injectable clock (createdAt + tests)
  schedule?: (fn: () => void, ms: number) => () => void; // timeout scheduler → canceller (testing seam)
}

/** Supervisor-owned registry of parked daemon permission requests. A daemon session's canUseTool parks here
 *  (brokerFor(id).request) until a client answers (respond), the park times out, the request's signal aborts,
 *  or the session/daemon tears down (denyAllForSession / denyAll) — every path settles the awaited promise. */
export class PendingPermissions {
  private pending = new Map<string, { entry: PendingEntry; resolve: (d: PermissionDecision) => void; cancel: () => void }>();
  private timeoutMs: number;
  private now: () => number;
  private schedule: (fn: () => void, ms: number) => () => void;

  constructor(opts: PendingPermissionsOpts = {}) {
    this.timeoutMs = opts.timeoutMs ?? 30_000;
    this.now = opts.now ?? Date.now;
    this.schedule = opts.schedule ?? ((fn, ms) => { const t = setTimeout(fn, ms); (t as any).unref?.(); return () => clearTimeout(t); });
  }

  /** A session-bound broker; its request() parks until settled. */
  brokerFor(sessionId: string): PermissionBroker {
    return { request: (req) => this.park(sessionId, req) };
  }

  private park(sessionId: string, req: PermissionRequest): Promise<PermissionDecision> {
    return new Promise((resolve) => {
      const entry: PendingEntry = {
        sessionId, toolUseID: req.toolUseID, toolName: req.toolName, input: req.input,
        title: req.title, displayName: req.displayName, description: req.description, createdAt: this.now(),
      };
      const cancelTimer = this.schedule(() => this.settle(req.toolUseID, { kind: "deny" }), this.timeoutMs);
      const onAbort = () => this.settle(req.toolUseID, { kind: "deny" });
      req.signal?.addEventListener("abort", onAbort, { once: true });
      const cancel = () => { cancelTimer(); req.signal?.removeEventListener("abort", onAbort); };
      this.pending.set(req.toolUseID, { entry, resolve, cancel });
    });
  }

  private settle(toolUseID: string, decision: PermissionDecision): boolean {
    const p = this.pending.get(toolUseID);
    if (!p) return false;
    p.cancel();
    this.pending.delete(toolUseID);
    p.resolve(decision);
    return true;
  }

  /** Answer a parked request. Returns false if none matches (already answered/timed out → idempotent). */
  respond(toolUseID: string, decision: PermissionDecision): boolean { return this.settle(toolUseID, decision); }

  /** The serializable list of currently-parked requests (for the poll). */
  list(): PendingEntry[] { return [...this.pending.values()].map((p) => p.entry); }

  /** Deny + settle every parked request for one session (session stop/teardown). */
  denyAllForSession(sessionId: string): void {
    for (const [id, p] of [...this.pending]) if (p.entry.sessionId === sessionId) this.settle(id, { kind: "deny" });
  }

  /** Deny + settle every parked request (daemon shutdown). */
  denyAll(): void { for (const id of [...this.pending.keys()]) this.settle(id, { kind: "deny" }); }
}
