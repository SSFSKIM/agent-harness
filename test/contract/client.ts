import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";

/** A faithful port of the Director's wire client (director/worker/app_server.py): it speaks the same codex v2
 *  JSON-RPC "lite" over stdio, answers server-initiated approval + item/tool/call requests, and tracks
 *  notifications. Used to prove cc-codex-appserver is a true drop-in. */
export class DirectorClient {
  private proc: ChildProcessWithoutNullStreams; private buf = ""; private id = 0;
  private pending = new Map<number, (r: any) => void>(); private notes: any[] = [];
  /** Every item/tool/call params the server asked us to execute (assertion surface for the round-trip). */
  public toolCalls: any[] = [];
  constructor(command: string[], env: Record<string, string>) {
    this.proc = spawn(command[0], command.slice(1), { stdio: ["pipe", "pipe", "inherit"], env }) as any;
    this.proc.stdout.on("data", (c) => { this.buf += c.toString(); let nl: number; while ((nl = this.buf.indexOf("\n")) >= 0) { const l = this.buf.slice(0, nl).trim(); this.buf = this.buf.slice(nl + 1); if (l) this.onLine(JSON.parse(l)); } });
  }
  private send(o: object) { this.proc.stdin.write(JSON.stringify(o) + "\n"); }
  private onLine(m: any) {
    if (m.method && m.id !== undefined) { this.send({ id: m.id, result: this.serverReq(m) }); return; }     // server-initiated request
    if (m.method) { this.notes.push(m); this.resolveNote?.(m); return; }                                     // notification
    const r = this.pending.get(m.id); if (r) { this.pending.delete(m.id); r(m); }                            // response
  }
  private resolveNote?: (m: any) => void;
  // Director-side executor: approvals auto-accept; a dynamic tool runs here (the key + guardrail stay client-side).
  private serverReq(m: any): any {
    if (m.method === "item/tool/call") { this.toolCalls.push(m.params); return { contentItems: [{ type: "inputText", text: `executed ${m.params.tool}` }], success: true }; }
    return m.method.includes("requestApproval") ? { decision: "accept" } : null;
  }
  private req(method: string, params: any): Promise<any> { const id = ++this.id; return new Promise((res) => { this.pending.set(id, res); this.send({ id, method, params }); }); }
  async initialize() { await this.req("initialize", { clientInfo: { name: "director", title: "Director", version: "0.1.0" }, capabilities: { experimentalApi: true } }); this.send({ method: "initialized", params: {} }); }
  async threadStart(cwd: string, dynamicTools?: any[]) {
    const params: any = { cwd, approvalPolicy: "on-request", sandbox: "workspace-write" };
    if (dynamicTools) params.dynamicTools = dynamicTools;
    const r = await this.req("thread/start", params); return r.result.thread.id;
  }
  async runTurn(threadId: string, text: string, cwd: string): Promise<{ status: string; final: string | null }> {
    const id = ++this.id; this.send({ id, method: "turn/start", params: { threadId, input: [{ type: "text", text }], cwd, approvalPolicy: "on-request" } });
    let final: string | null = null;
    return await new Promise((resolve) => {
      this.resolveNote = (m: any) => {
        if (m.method === "item/completed" && m.params?.item?.type === "agentMessage" && m.params.item.phase === "final_answer") final = m.params.item.text;
        if (m.method === "turn/completed" || m.method === "turn/failed" || m.method === "turn/cancelled") resolve({ status: m.method.split("/")[1], final });
      };
    });
  }
  stop() { try { this.proc.stdin.end(); this.proc.kill(); } catch {} }
}
