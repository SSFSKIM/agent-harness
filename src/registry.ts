import type { Session } from "cc-harness";

export interface ThreadEntry { session: Session; turnSeq: number }

export class Registry {
  private threads = new Map<string, ThreadEntry>();
  private threadN = 0;
  newThread(session: Session): { id: string } {
    const id = `thr_${++this.threadN}`;
    this.threads.set(id, { session, turnSeq: 0 });
    return { id };
  }
  get(id: string): ThreadEntry | undefined { return this.threads.get(id); }
  nextTurnId(id: string): string { const e = this.threads.get(id); if (!e) throw new Error(`unknown thread ${id}`); return `turn_${id}_${++e.turnSeq}`; }
  async disposeAll(): Promise<void> { for (const e of this.threads.values()) { try { await e.session.dispose(); } catch {} } this.threads.clear(); }
}
