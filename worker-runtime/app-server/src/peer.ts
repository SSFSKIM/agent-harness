import { isRequest, isNotification, isResponse, type Incoming, type RpcResponse } from "./protocol.js";

export class Peer {
  private nextId = 1;
  private pending = new Map<number | string, (r: RpcResponse) => void>();
  private buf = "";
  constructor(
    private sink: (obj: object) => void,
    private onRequest: (method: string, params: any, id: number | string) => void,
    private onNotification?: (method: string, params: any) => void,
  ) {}

  feed(chunk: string | Buffer): void {
    this.buf += chunk.toString();
    let nl: number;
    while ((nl = this.buf.indexOf("\n")) >= 0) {
      const line = this.buf.slice(0, nl).trim();
      this.buf = this.buf.slice(nl + 1);
      if (!line) continue;
      let msg: Incoming;
      try { msg = JSON.parse(line); } catch { console.error("[appserver] bad json line:", line.slice(0, 200)); continue; }
      this.dispatch(msg);
    }
  }

  private dispatch(msg: Incoming): void {
    if (isResponse(msg)) { const r = this.pending.get((msg as any).id); if (r) { this.pending.delete((msg as any).id); r(msg as RpcResponse); } return; }
    if (isRequest(msg)) { this.onRequest(msg.method, (msg as any).params, msg.id); return; }
    if (isNotification(msg)) { this.onNotification?.(msg.method, (msg as any).params); return; }
  }

  reply(id: number | string, result: unknown): void { this.sink({ id, result }); }
  replyError(id: number | string, code: number, message: string): void { this.sink({ id, error: { code, message } }); }
  notify(method: string, params: unknown): void { this.sink({ method, params }); }
  request(method: string, params: unknown): Promise<RpcResponse> {
    const id = this.nextId++;
    return new Promise((resolve) => { this.pending.set(id, resolve); this.sink({ id, method, params }); });
  }
}
