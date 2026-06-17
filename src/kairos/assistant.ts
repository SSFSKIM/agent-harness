import { DaemonSupervisor } from "../daemon/supervisor.js";
import type { QueryFn } from "../swarm/types.js";
import type { ProactiveConfigInput, ProactiveStatus } from "../proactive/types.js";
import { applyProactivePersona } from "../proactive/prompts.js";
import { applyAssistantPersona } from "./persona.js";
import { resolveAssistantPosture } from "./safety.js";
import type { PostureConfig } from "./safety.js";
import { createBriefMcpServer, stdoutBriefSink } from "./brief.js";
import type { BriefSink } from "./brief.js";

export interface KairosConfig {
  cwd?: string;
  model?: string;
  sink?: BriefSink;
  proactive?: ProactiveConfigInput;
  posture?: PostureConfig;
}

/** Autonomous scheduled assistant: one long-lived session, self-paced by the proactive heartbeat,
 *  permission-gated by native `auto`, reporting through the Brief channel. */
export class KairosAssistant {
  private sup: DaemonSupervisor;
  private model?: string;
  private proactiveCfg?: ProactiveConfigInput;
  private id?: string;
  private stopped = false;

  constructor(deps: { query: QueryFn }, config: KairosConfig = {}) {
    const sink = config.sink ?? stdoutBriefSink;
    this.model = config.model;
    this.proactiveCfg = config.proactive;
    // Build the COMPLETE assistant session options (a daemon session's base is only { model }).
    const sessionOptions = (_id: string): Record<string, unknown> => {
      const opts: Record<string, unknown> = {};
      if (config.cwd) opts.cwd = config.cwd;
      applyProactivePersona(opts);                 // heartbeat/IDLE contract
      applyAssistantPersona(opts);                 // assistant + Brief instructions
      Object.assign(opts, resolveAssistantPosture(config.posture)); // permissionMode 'auto' (+ optional denylist)
      opts.mcpServers = { "cc-brief": createBriefMcpServer(sink) };
      opts.allowedTools = ["mcp__cc-brief__SendUserMessage"]; // never let the Brief channel be gated
      return opts;
    };
    this.sup = new DaemonSupervisor(deps, { sessionOptions, idleTimeoutMs: 0 }); // 0 → no idle reaper
  }

  async start(seedPrompt?: string): Promise<void> {
    if (this.id) throw new Error("KairosAssistant already started");
    this.id = this.sup.spawn({ model: this.model });
    if (seedPrompt) await this.sup.submit(this.id, seedPrompt, () => {}); // seed context; output via the sink
    this.sup.startProactive(this.id, this.proactiveCfg);
  }

  status(): { sessionId?: string; proactive?: ProactiveStatus } {
    return { sessionId: this.id, proactive: this.id ? this.sup.proactiveStatus(this.id) : undefined };
  }

  async stop(): Promise<void> {
    if (this.stopped || !this.id) return; // nothing started, or already stopped → no-op (no latch before start)
    this.stopped = true;
    await this.sup.shutdown();        // stops the heartbeat loop + disposes the session
  }
}
