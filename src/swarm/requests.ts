/** Correlates an async request id with a pending promise the holder resolves later (bus-RPC). */
export class RequestRegistry<T = unknown> {
  private pending = new Map<string, (value: T) => void>();
  private seq = 0;

  create(): { id: string; promise: Promise<T> } {
    const id = `req-${++this.seq}`;
    const promise = new Promise<T>((resolve) => this.pending.set(id, resolve));
    return { id, promise };
  }

  resolve(id: string, value: T): boolean {
    const resolve = this.pending.get(id);
    if (!resolve) return false;
    this.pending.delete(id);
    resolve(value);
    return true;
  }
}
