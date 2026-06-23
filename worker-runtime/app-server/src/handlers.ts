import { openSession, type Session } from "cc-harness";
import { Peer } from "./peer.js";
import { Registry, type ThreadEntry } from "./registry.js";
import { AppServerBroker } from "./approvals.js";
import { TurnTranslator } from "./translator.js";
import { ERR, type DynamicToolSpec, type ThreadStartParams, type TurnStartParams, type UsageTotals } from "./protocol.js";
import { ToolBroker, withDynamicTools } from "./broker.js";
import { resolvePosture } from "./posture.js";
import { resolveSandbox } from "./sandbox.js";

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
  private network: boolean;
  private heartbeatMs: number;
  constructor(private peer: Peer, deps: { open?: OpenFn; autoReview?: boolean; network?: boolean; heartbeatMs?: number } = {}) {
    this.open = deps.open ?? ((cfg) => openSession(cfg));
    this.autoReview = deps.autoReview ?? false;
    this.network = deps.network ?? false;
    // Per-turn usage-heartbeat cadence. ~30s sits well under the Director's DEFAULT
    // read_timeout (180s), so a long silent tool run (a full check.py between streamed
    // messages) can never look like a hung worker — a notification lands every tick.
    this.heartbeatMs = deps.heartbeatMs ?? 30_000;
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
    // Self-introspection: every worker session gets cc-context (GetContextUsage) and
    // cc-compact (RequestCompaction) so the agent can read its own context usage and
    // schedule a self-compaction before exhausting the window — essential for long
    // multi-turn Director tickets. Additive: openSession only APPENDS these to
    // allowedTools (same mechanism as withDynamicTools), so built-in tools stay available.
    cfg.contextTool = true;
    cfg.compactTool = true;
    // OS-level sandbox (Seatbelt/bubblewrap) for Bash + L3 credential-read deny rules,
    // translated from the Director's codex sandbox posture. Opt-out modes return {} (no change).
    const plan = resolveSandbox({
      mode: params.sandbox,
      autoReview: this.autoReview,
      network: this.network,
      strict: process.env.CC_APPSERVER_SANDBOX_STRICT === "1",
      allowedDomains: process.env.CC_APPSERVER_SANDBOX_DOMAINS
        ? process.env.CC_APPSERVER_SANDBOX_DOMAINS.split(",").map((s) => s.trim()).filter(Boolean)
        : undefined,
    });
    if (plan.sandbox) cfg.sandbox = plan.sandbox;
    if (plan.settings) cfg.settings = plan.settings;
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
    const stopBeat = this.startUsageHeartbeat(entry, tr);
    try {
      const { result } = await entry.session.submit(text, (m) => { for (const o of tr.onMessage(m)) this.peer.notify((o as any).method, (o as any).params); });
      let usage: UsageTotals | undefined;
      try { usage = toUsageTotals(await entry.session.usage()); } catch { /* telemetry only — usage() is cumulative per session */ }
      for (const o of tr.finalize({ text: String(result ?? ""), isError: false, usage })) this.peer.notify((o as any).method, (o as any).params);
    } catch (e) {
      console.error("[appserver] turn error:", (e as Error).message);
      for (const o of tr.finalize({ text: "", isError: true })) this.peer.notify((o as any).method, (o as any).params);
    } finally {
      stopBeat();
    }
  }

  /** Start a per-turn usage heartbeat: every `heartbeatMs`, read the session's cumulative usage
   *  (a control-plane query, safe mid-turn like getContextUsage/interrupt) and emit a
   *  thread/tokenUsage/updated. Two jobs at once: (1) LIVE mid-turn token accrual on the Director
   *  dashboard (codex streams usage per-event; the SDK adapter otherwise only emits at finalize),
   *  and (2) a keep-alive — any notification resets the Director's inter-read timeout, so a long
   *  silent tool run no longer trips ReadTimeout and mislabels a SUCCEEDING worker as failed (the
   *  read_timeout band-aid becomes belt-and-suspenders). Best-effort: a failed usage() keeps the
   *  last value and still beats; nothing emits after the turn finalized (the `stopped` guard).
   *  Returns the stop function (called in runTurn's finally). */
  private startUsageHeartbeat(entry: ThreadEntry, tr: TurnTranslator): () => void {
    let last: UsageTotals = { totalTokens: 0, inputTokens: 0, outputTokens: 0 };
    let stopped = false;
    const tick = async () => {
      try { last = toUsageTotals(await entry.session.usage()); } catch { /* keep last; still beat */ }
      if (stopped) return;                    // the turn finalized while usage() was in flight — don't emit out of order
      const o = tr.tokenUsage(last) as any;
      this.peer.notify(o.method, o.params);
    };
    const iv = setInterval(() => { void tick(); }, this.heartbeatMs);
    (iv as any).unref?.();                     // a pending heartbeat must never keep the process alive on its own
    return () => { stopped = true; clearInterval(iv); };
  }
}
