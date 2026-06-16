import { query as sdkQuery } from "@anthropic-ai/claude-agent-sdk";
import type { HarnessConfig } from "./config/types.js";
import { resolveOptions } from "./config/resolveOptions.js";
import { TaskStore } from "./tasks/store.js";
import { createTaskMcpServer } from "./tasks/server.js";

export interface HarnessDeps { query?: typeof sdkQuery; }

export interface RunResult { result: unknown; messages: unknown[]; sessionId?: string; }

export interface Harness {
  options: Record<string, unknown>;
  run(prompt: string): Promise<RunResult>;
  stream(prompt: string): AsyncGenerator<unknown>;
  rewind(userMessageId: string, opts?: { dryRun?: boolean }): Promise<unknown>;
  supportedCommands(): Promise<unknown>;
  supportedModels(): Promise<unknown>;
  supportedAgents(): Promise<unknown>;
  tasks?: TaskStore;
}

export function createHarness(config: HarnessConfig = {}, deps: HarnessDeps = {}): Harness {
  const query = deps.query ?? sdkQuery;
  const options = resolveOptions(config);

  let tasks: TaskStore | undefined;
  if (config.taskTools) {
    const opts = config.taskTools === true ? {} : config.taskTools;
    tasks = new TaskStore({ cwd: config.cwd, dir: opts.dir, listId: opts.listId, agentName: opts.agentName });
    const existing = (options.mcpServers as Record<string, unknown>) ?? {};
    options.mcpServers = { ...existing, "cc-tasks": createTaskMcpServer(tasks) };
  }
  // A Harness drives ONE query at a time; `active` tracks the most recent one.
  // Control methods (rewind/supported*) are SDK control requests that require an
  // OPEN transport (sdk.d.ts:2242, streaming mode) — call them while a query is
  // still streaming, not after run() completes. Concurrent/interactive multi-session
  // use (per-query control handles) is a Phase-2 concern.
  let active: any = null;

  function start(prompt: string) {
    active = query({ prompt, options: options as any });
    return active;
  }

  async function* stream(prompt: string) {
    const q = start(prompt);
    for await (const m of q) yield m;
  }

  async function run(prompt: string): Promise<RunResult> {
    const messages: unknown[] = [];
    let result: unknown; let sessionId: string | undefined;
    for await (const m of stream(prompt)) {
      messages.push(m);
      const mm = m as any;
      if (mm.type === "system" && mm.subtype === "init") sessionId = mm.session_id;
      if ("result" in mm) result = mm.result;
    }
    return { result, messages, sessionId };
  }

  const call = (name: string) => async (...args: any[]) => {
    if (!active || typeof active[name] !== "function")
      throw new Error(`${name}() unavailable: start a query first`);
    return active[name](...args);
  };

  return {
    options,
    run,
    stream,
    rewind: (id, opts) => call("rewindFiles")(id, opts),
    supportedCommands: call("supportedCommands"),
    supportedModels: call("supportedModels"),
    supportedAgents: call("supportedAgents"),
    tasks,
  };
}
