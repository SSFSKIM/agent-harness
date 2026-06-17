import type { SDKUserMessage } from "@anthropic-ai/claude-agent-sdk";
import { AsyncQueue } from "../swarm/asyncQueue.js";
import type { QueryFn } from "../swarm/types.js";
import type { ControllableSession } from "../bridge/types.js";
import { withContextTool, type QueryHolder, type RawContextUsage } from "../context/server.js";

export interface DaemonSessionDeps { query: QueryFn; }

function userTurn(text: string): SDKUserMessage {
  return { type: "user", message: { role: "user", content: text }, parent_tool_use_id: null } as SDKUserMessage;
}

interface Waiter { onMessage: (m: unknown) => void; resolve: (r: { result: unknown }) => void; reject: (e: Error) => void; }

/** One long-lived query() session. A turn is submit(prompt,onMessage) → streamed messages → resolved result. */
export class DaemonSession implements ControllableSession {
  readonly id: string;
  lastActiveAt: number;
  private input = new AsyncQueue<SDKUserMessage>();
  private q: AsyncIterable<unknown>;
  readonly done: Promise<void>; // resolves when the read-loop ends; the supervisor attaches its restart end-hook here
  private waiters: Waiter[] = []; // FIFO: query emits one result per submitted turn, in order
  private ended = false;          // true once the read-loop finishes (query disposed or died)

  constructor(
    id: string,
    deps: DaemonSessionDeps,
    options: Record<string, unknown>,
    private now: () => number = Date.now,
    sessionOpts: { contextTool?: boolean } = {},
  ) {
    this.id = id;
    this.lastActiveAt = now();
    let opts = options;
    let ctxHolder: QueryHolder | undefined;
    if (sessionOpts.contextTool) { ctxHolder = {}; opts = withContextTool(options, ctxHolder); }
    this.q = deps.query({ prompt: this.input, options: opts });
    if (ctxHolder) ctxHolder.query = this.q as unknown as { getContextUsage(): Promise<RawContextUsage> };
    // A dead/errored query must not reject teardown (dispose awaits this).
    this.done = this.readLoop().catch(() => {});
  }

  /** Run one turn; non-result messages stream to onMessage; resolves with the turn's result.
   * Rejects immediately if the underlying query has already ended (else the waiter would never drain). */
  submit(prompt: string, onMessage: (m: unknown) => void): Promise<{ result: unknown }> {
    if (this.ended) return Promise.reject(new Error(`session ${this.id} is not running`));
    return new Promise((resolve, reject) => {
      this.waiters.push({ onMessage, resolve, reject });
      this.input.push(userTurn(prompt));
    });
  }

  /** End the query (in-flight turn finishes) and wait for the read-loop. */
  async dispose(): Promise<void> { this.input.close(); await this.done; }

  // ---- control surface (Phase 2 B): guarded delegations to the underlying Query ----
  isEnded(): boolean { return this.ended; }
  private assertRunning(): void { if (this.ended) throw new Error(`session ${this.id} is not running`); }

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
        if ((m as any).type === "result") this.waiters.shift()?.resolve({ result: (m as any).result }); // consume a waiter only if present
        else this.waiters[0]?.onMessage(m);
      }
    } finally {
      this.ended = true;
      // Reject (not silently resolve) any turn left in flight when the query ends — it never completed.
      for (const w of this.waiters.splice(0)) w.reject(new Error(`session ${this.id} disposed`));
    }
  }
}
