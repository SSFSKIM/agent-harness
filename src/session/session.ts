import type { SDKUserMessage } from "@anthropic-ai/claude-agent-sdk";
import { AsyncQueue } from "../swarm/asyncQueue.js";
import type { QueryFn } from "../swarm/types.js";
import type { ControllableSession } from "../bridge/types.js";
import { withContextTool, type QueryHolder, type RawContextUsage } from "../context/server.js";
import { withCompactTool, parseCompactOutcome, type CompactHolder, type CompactOutcome } from "../compaction/server.js";

export interface SessionDeps { query: QueryFn; }
export interface SessionOpts { contextTool?: boolean; compactTool?: boolean; label?: string; now?: () => number; }

function userTurn(text: string): SDKUserMessage {
  return { type: "user", message: { role: "user", content: text }, parent_tool_use_id: null } as SDKUserMessage;
}

interface Waiter { onMessage: (m: unknown) => void; resolve: (r: { result: unknown }) => void; reject: (e: Error) => void; }

/** One long-lived query() session. A turn is submit(prompt,onMessage) → streamed messages → resolved result.
 *  Captures the SDK session_id from the first system/init frame (stable per probe) → .sessionId. */
export class Session implements ControllableSession {
  lastActiveAt: number;
  readonly done: Promise<void>;            // resolves when the read-loop ends (query disposed or died)
  private input = new AsyncQueue<SDKUserMessage>();
  private q: AsyncIterable<unknown>;
  private waiters: Waiter[] = [];          // FIFO: query emits one result per submitted turn, in order
  private ended = false;
  private compactRequested = false;        // set by the cc-compact tool; fires one /compact at the next boundary
  private now: () => number;
  private label: string;                   // used only in error messages
  private _sessionId?: string;             // captured from the first system/init frame

  constructor(deps: SessionDeps, options: Record<string, unknown>, sessionOpts: SessionOpts = {}) {
    this.now = sessionOpts.now ?? Date.now;
    this.label = sessionOpts.label ?? "session";
    this.lastActiveAt = this.now();
    let opts = options;
    let ctxHolder: QueryHolder | undefined;
    let compactHolder: CompactHolder | undefined;
    if (sessionOpts.contextTool) { ctxHolder = {}; opts = withContextTool(opts, ctxHolder); }
    if (sessionOpts.compactTool) { compactHolder = {}; opts = withCompactTool(opts, compactHolder); }
    this.q = deps.query({ prompt: this.input, options: opts });
    if (ctxHolder) ctxHolder.query = this.q as unknown as { getContextUsage(): Promise<RawContextUsage> };
    if (compactHolder) compactHolder.request = () => this.requestCompaction();
    this.done = this.readLoop().catch(() => {});
  }

  /** The SDK session_id, available after the first turn's init frame; undefined before then. */
  get sessionId(): string | undefined { return this._sessionId; }
  isEnded(): boolean { return this.ended; }

  /** Push a turn + its waiter onto the FIFO. Shared by submit() and compact() so every injected turn
   *  gets its own waiter (its result resolves ITS waiter, never another turn's). */
  private enqueueTurn(prompt: string, onMessage: (m: unknown) => void): Promise<{ result: unknown }> {
    return new Promise((resolve, reject) => { this.waiters.push({ onMessage, resolve, reject }); this.input.push(userTurn(prompt)); });
  }

  /** Run one turn; non-result messages stream to onMessage; resolves with the turn's result.
   *  Rejects immediately if the underlying query has already ended (else the waiter would never drain). */
  submit(prompt: string, onMessage: (m: unknown) => void = () => {}): Promise<{ result: unknown }> {
    if (this.ended) return Promise.reject(new Error(`${this.label} is not running`));
    return this.enqueueTurn(prompt, onMessage);
  }

  /** Inject `/compact` as a turn (its own FIFO waiter) and return the structured outcome. */
  async compact(): Promise<CompactOutcome> {
    this.assertRunning();
    const frames: unknown[] = [];
    await this.enqueueTurn("/compact", (m) => {
      const mm = m as any;
      if (mm.type === "system" && (mm.subtype === "status" || mm.subtype === "compact_boundary")) frames.push(mm);
    });
    return parseCompactOutcome(frames);
  }

  /** Record intent (set by the cc-compact tool); consumed at the next turn boundary in readLoop. */
  requestCompaction(): void { this.compactRequested = true; }

  /** End the query (in-flight turn finishes) and wait for the read-loop. */
  async dispose(): Promise<void> { this.input.close(); await this.done; }

  protected assertRunning(): void { if (this.ended) throw new Error(`${this.label} is not running`); }

  private callQ(name: string, ...args: unknown[]): Promise<void> {
    const fn = (this.q as any)[name];
    if (typeof fn !== "function") return Promise.reject(new Error(`unsupported: ${name}`));
    return fn.apply(this.q, args);
  }
  private callQValue(name: string): Promise<unknown> {
    const fn = (this.q as any)[name];
    if (typeof fn !== "function") return Promise.reject(new Error(`unsupported: ${name}`));
    return fn.apply(this.q);
  }

  async setModel(model?: string): Promise<void> { this.assertRunning(); await this.callQ("setModel", model); }
  async setPermissionMode(mode: string): Promise<void> { this.assertRunning(); await this.callQ("setPermissionMode", mode); }
  async setMaxThinkingTokens(maxTokens: number | null): Promise<void> { this.assertRunning(); await this.callQ("setMaxThinkingTokens", maxTokens); }
  async interrupt(): Promise<void> { await this.callQ("interrupt"); } // benign no-op when idle; unsupported if absent

  async getContextUsage(): Promise<unknown> { this.assertRunning(); return this.callQValue("getContextUsage"); }
  async accountInfo(): Promise<unknown> { this.assertRunning(); return this.callQValue("accountInfo"); }

  /** Rewind the file checkpoint to a prior user-prompt message. The anchor must be a real user-prompt UUID
   *  from the transcript (getSessionMessages), NOT a live-stream type:"user" frame. */
  async rewind(userMessageId: string, opts?: { dryRun?: boolean }): Promise<unknown> {
    this.assertRunning();
    const fn = (this.q as any).rewindFiles;
    if (typeof fn !== "function") return Promise.reject(new Error("unsupported: rewindFiles"));
    return fn.call(this.q, userMessageId, opts);
  }

  async capabilities(): Promise<{ models: unknown[]; commands: unknown[]; mcpServers: unknown[] }> {
    const q = this.q as any;
    const [models, commands, mcpServers] = await Promise.all([
      q.supportedModels?.() ?? [], q.supportedCommands?.() ?? [], q.mcpServerStatus?.() ?? [],
    ]);
    return { models, commands, mcpServers };
  }

  private async readLoop(): Promise<void> {
    try {
      for await (const m of this.q) {
        this.lastActiveAt = this.now();
        const mm = m as any;
        if (mm.type === "system" && mm.subtype === "init" && !this._sessionId) this._sessionId = mm.session_id;
        if (mm.type === "result") {
          this.waiters.shift()?.resolve({ result: mm.result });
          if (this.compactRequested && !this.ended) { this.compactRequested = false; void this.compact().catch(() => {}); }
        } else this.waiters[0]?.onMessage(m);
      }
    } finally {
      this.ended = true;
      for (const w of this.waiters.splice(0)) w.reject(new Error(`${this.label} disposed`));
    }
  }
}
