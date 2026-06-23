import { mkdirSync, readdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { SessionRecord } from "./types.js";

export interface SessionRegistryOptions {
  dir?: string;
  isAlive?: (pid: number) => boolean;
}

function defaultIsAlive(pid: number): boolean {
  try { process.kill(pid, 0); return true; } catch { return false; }
}

/** JSON record store, one file per session under <dir>/<id>.json — the `ps` foundation (33.3). */
export class SessionRegistry {
  private dir: string;
  private isAlive: (pid: number) => boolean;

  constructor(opts: SessionRegistryOptions = {}) {
    this.dir = opts.dir ?? join(homedir(), ".claude", "cc-daemon", "sessions");
    this.isAlive = opts.isAlive ?? defaultIsAlive;
    mkdirSync(this.dir, { recursive: true, mode: 0o700 });
  }

  register(rec: SessionRecord): void {
    writeFileSync(this.path(rec.id), JSON.stringify(rec), { mode: 0o600 });
  }

  update(id: string, patch: Partial<SessionRecord>): void {
    const cur = this.get(id);
    if (cur) this.register({ ...cur, ...patch });
  }

  get(id: string): SessionRecord | undefined {
    try { return JSON.parse(readFileSync(this.path(id), "utf8")) as SessionRecord; } catch { return undefined; }
  }

  list(): SessionRecord[] {
    return readdirSync(this.dir)
      .filter((f) => f.endsWith(".json"))
      .map((f) => { try { return JSON.parse(readFileSync(join(this.dir, f), "utf8")) as SessionRecord; } catch { return undefined; } })
      .filter((r): r is SessionRecord => r !== undefined)
      .sort((a, b) => a.createdAt - b.createdAt);
  }

  remove(id: string): void { rmSync(this.path(id), { force: true }); }

  /** Drop records whose owning daemon pid is gone (orphaned by a prior crash). Returns the count. */
  reapStale(): number {
    let n = 0;
    for (const r of this.list()) if (!this.isAlive(r.daemonPid)) { this.remove(r.id); n++; }
    return n;
  }

  /** Boot adoption: claim orphaned-but-resumable records for `pid` (normalize status to idle, reset the
   *  restart budget), reap the rest (errored / never-took-a-turn), and return the claimed records. Records
   *  owned by a still-live daemon are left untouched (shared registry dir). Counterpart to reapStale(). */
  rehydrate(pid: number): SessionRecord[] {
    const claimed: SessionRecord[] = [];
    for (const r of this.list()) {
      if (this.isAlive(r.daemonPid)) continue;                                                  // a live daemon owns it
      const resumable = !!r.sessionId && (r.status === "idle" || r.status === "busy" || r.status === "restarting");
      if (!resumable) { this.remove(r.id); continue; }                                          // errored / no transcript → reap
      const next: SessionRecord = { ...r, daemonPid: pid, status: "idle", restarts: 0 };
      this.register(next); claimed.push(next);
    }
    return claimed;
  }

  private path(id: string): string { return join(this.dir, `${id}.json`); }
}
