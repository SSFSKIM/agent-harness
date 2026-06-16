import type { SDKUserMessage } from "@anthropic-ai/claude-agent-sdk";
import { AsyncQueue } from "../swarm/asyncQueue.js";
import type { QueryFn } from "../swarm/types.js";

export interface DaemonSessionDeps { query: QueryFn; }

function userTurn(text: string): SDKUserMessage {
  return { type: "user", message: { role: "user", content: text }, parent_tool_use_id: null } as SDKUserMessage;
}

interface Waiter { onMessage: (m: unknown) => void; resolve: (r: { result: unknown }) => void; reject: (e: Error) => void; }

/** One long-lived query() session. A turn is submit(prompt,onMessage) → streamed messages → resolved result. */
export class DaemonSession {
  readonly id: string;
  lastActiveAt: number;
  private input = new AsyncQueue<SDKUserMessage>();
  private q: AsyncIterable<unknown>;
  readonly done: Promise<void>; // resolves when the read-loop ends; the supervisor attaches its restart end-hook here
  private waiters: Waiter[] = []; // FIFO: query emits one result per submitted turn, in order
  private ended = false;          // true once the read-loop finishes (query disposed or died)

  constructor(id: string, deps: DaemonSessionDeps, options: Record<string, unknown>, private now: () => number = Date.now) {
    this.id = id;
    this.lastActiveAt = now();
    this.q = deps.query({ prompt: this.input, options });
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
