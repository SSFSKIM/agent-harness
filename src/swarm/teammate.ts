import type { SDKUserMessage } from "@anthropic-ai/claude-agent-sdk";
import { AsyncQueue } from "./asyncQueue.js";
import type { MessageBus } from "./bus.js";
import type { MessageKind, QueryFn, TeammateSpec } from "./types.js";

export interface TeammateDeps { query: QueryFn; }

function userTurn(text: string): SDKUserMessage {
  return { type: "user", message: { role: "user", content: text }, parent_tool_use_id: null } as SDKUserMessage;
}

export class TeammateSession {
  readonly name: string;
  readonly teamId: string;
  readonly done: Promise<void>;
  private input = new AsyncQueue<SDKUserMessage>();
  private q: AsyncIterable<any>;
  private settleResolvers: (() => void)[] = [];

  constructor(spec: TeammateSpec, private bus: MessageBus, deps: TeammateDeps, options?: Record<string, unknown>) {
    this.name = spec.name;
    this.teamId = spec.teamId;
    // Construction has no external side effects (the runtime wires the inbound bus
    // subscription after registration), so a throwing query() leaves no dirty state.
    this.input.push(userTurn(spec.prompt));                      // seed turn
    this.q = deps.query({ prompt: this.input, options });
    // A dead/errored teammate query must not reject teardown (dispose/disposeAll await this).
    this.done = this.readLoop().catch(() => {});
  }

  /** Deliver a new user turn into this teammate's query. */
  send(turn: string): void { this.input.push(userTurn(turn)); }

  /** Resolves after the next turn settles (result + maybe idle emitted). */
  settled(): Promise<void> { return new Promise((r) => this.settleResolvers.push(r)); }

  /** End the underlying query and wait for the read-loop to finish. */
  async dispose(): Promise<void> { this.input.close(); await this.done; }

  /** Graceful shutdown handshake: ack the coordinator, then end the query (current turn finishes first). */
  async shutdown(): Promise<void> {
    this.emit("shutdown", "");
    await this.dispose();
  }

  private emit(kind: MessageKind, body: string): void {
    this.bus.send("coordinator", { from: this.name, to: "coordinator", kind, body, ts: new Date().toISOString() });
  }

  private settle(): void {
    const waiters = this.settleResolvers;
    this.settleResolvers = [];
    for (const w of waiters) w();
  }

  private async readLoop(): Promise<void> {
    try {
      for await (const m of this.q) {
        const mm = m as any;
        if (mm.type === "system" && mm.subtype === "worker_shutting_down") this.emit("shutdown", String(mm.reason ?? ""));
        if (mm.type === "result") {
          this.emit("result", String(mm.result ?? ""));
          if (this.input.pending === 0) this.emit("idle", "");
          this.settle();
        }
      }
    } finally {
      this.settle(); // release any pending settled() waiters when the query ends
    }
  }
}
