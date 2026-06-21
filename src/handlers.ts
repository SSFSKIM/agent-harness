import { openSession, type Session } from "cc-harness";
import { Peer } from "./peer.js";
import { Registry, type ThreadEntry } from "./registry.js";
import { AppServerBroker } from "./approvals.js";
import { TurnTranslator } from "./translator.js";
import { ERR, type DynamicToolSpec, type ThreadStartParams, type TurnStartParams, type UsageTotals } from "./protocol.js";
import { ToolBroker, withDynamicTools } from "./broker.js";
import { resolvePosture } from "./posture.js";

/** Context handed to the session opener so a fake (test) session can drive the dynamic-tool broker
 *  directly; the real opener (openSession) ignores it — the SDK MCP server already closed over the broker. */
export interface OpenCtx { broker?: ToolBroker; dynamicTools?: DynamicToolSpec[] }
export interface OpenFn { (cfg: any, ctx: OpenCtx): Session }

/** Sum the CUMULATIVE per-model token usage from session.usage() (probe 32 shape) into absolute UsageTotals.
 *  inputTokens folds in cached input (cacheRead+cacheCreation) for a meaningful total. Lenient: missing -> 0. */
export function toUsageTotals(u: any): UsageTotals {
  const n = (v: any) => (typeof v === "number" ? v : 0);
  const models = u?.session?.model_usage ?? {};
  let input = 0, output = 0;
  for (const k of Object.keys(models)) {
    const m = models[k];
    input += n(m?.inputTokens) + n(m?.cacheReadInputTokens) + n(m?.cacheCreationInputTokens);
    output += n(m?.outputTokens);
  }
  return { inputTokens: input, outputTokens: output, totalTokens: input + output };
}

export class AppServer {
  private reg = new Registry();
  private open: OpenFn;
  private autoReview: boolean;
  constructor(private peer: Peer, deps: { open?: OpenFn; autoReview?: boolean } = {}) {
    this.open = deps.open ?? ((cfg) => openSession(cfg));
    this.autoReview = deps.autoReview ?? false;
  }

  disposeAll(): Promise<void> { return this.reg.disposeAll(); }

  handleRequest(method: string, params: any, id: number | string): void {
    switch (method) {
      case "initialize": return this.peer.reply(id, { userAgent: "cc-codex-appserver", platformOs: process.platform });
      case "thread/start": return this.threadStart(params as ThreadStartParams, id);
      case "turn/start": return this.turnStart(params as TurnStartParams, id);
      default: console.error("[appserver] unhandled method:", method); return this.peer.replyError(id, ERR.METHOD_NOT_FOUND, `method not found: ${method}`);
    }
  }
  // initialized is a notification — handled by the bin's onNotification (noop). Kept here for clarity.

  private threadStart(params: ThreadStartParams, id: number | string): void {
    const posture = resolvePosture({ approvalPolicy: params.approvalPolicy, autoReview: this.autoReview });
    let cfg: any = { cwd: params.cwd, model: params.model, permissionMode: posture.permissionMode };
    // Allocate a stable threadId so the broker/permission closures can reference it before open() is called.
    const threadId = this.reg.allocId();
    const turnIdOf = () => this.reg.get(threadId)?.currentTurnId ?? "";
    const specs = params.dynamicTools ?? [];
    const broker = new ToolBroker(this.peer, threadId, turnIdOf);
    if (specs.length) cfg = withDynamicTools(cfg, specs, broker);
    if (posture.roundTripApprovals) cfg.permissionBroker = new AppServerBroker(this.peer, { threadId, turnId: turnIdOf });
    const session = this.open(cfg, { broker: specs.length ? broker : undefined, dynamicTools: specs });
    this.reg.register(threadId, session);
    this.peer.reply(id, { thread: { id: threadId } });
    this.peer.notify("thread/started", { thread: { id: threadId } });
  }

  private turnStart(params: TurnStartParams, id: number | string): void {
    const entry = this.reg.get(params.threadId);
    if (!entry) return this.peer.replyError(id, ERR.INVALID_PARAMS, `unknown thread ${params.threadId}`);
    const turnId = this.reg.nextTurnId(params.threadId);
    entry.currentTurnId = turnId;
    this.peer.reply(id, { turn: { id: turnId, status: "inProgress" } });
    this.peer.notify("turn/started", { turn: { id: turnId } });
    const text = (params.input ?? []).map((p) => p.text ?? "").join("");
    const tr = new TurnTranslator(params.threadId, turnId);
    void this.runTurn(entry, text, tr);
  }

  private async runTurn(entry: ThreadEntry, text: string, tr: TurnTranslator): Promise<void> {
    try {
      const { result } = await entry.session.submit(text, (m) => { for (const o of tr.onMessage(m)) this.peer.notify((o as any).method, (o as any).params); });
      let usage: UsageTotals | undefined;
      try { usage = toUsageTotals(await entry.session.usage()); } catch { /* telemetry only — usage() is cumulative per session */ }
      for (const o of tr.finalize({ text: String(result ?? ""), isError: false, usage })) this.peer.notify((o as any).method, (o as any).params);
    } catch (e) {
      console.error("[appserver] turn error:", (e as Error).message);
      for (const o of tr.finalize({ text: "", isError: true })) this.peer.notify((o as any).method, (o as any).params);
    }
  }
}
