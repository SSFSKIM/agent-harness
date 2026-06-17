import { query as sdkQuery } from "@anthropic-ai/claude-agent-sdk";
import type { HarnessConfig } from "./config/types.js";
import { resolveOptions } from "./config/resolveOptions.js";
import { TaskStore } from "./tasks/store.js";
import { createTaskMcpServer } from "./tasks/server.js";
import { SwarmRuntime } from "./swarm/runtime.js";
import { createSwarmMcpServer } from "./swarm/server.js";
import { applyCoordinatorPersona, NATIVE_TASK_TOOLS } from "./swarm/coordinator.js";

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
  swarm?: SwarmRuntime;
}

export function createHarness(config: HarnessConfig = {}, deps: HarnessDeps = {}): Harness {
  const query = deps.query ?? sdkQuery;
  const options = resolveOptions(config);

  let tasks: TaskStore | undefined;
  let swarm: SwarmRuntime | undefined;

  if (config.swarm) {
    const so = config.swarm === true ? {} : config.swarm;
    const to = config.taskTools && config.taskTools !== true ? config.taskTools : {};
    swarm = new SwarmRuntime({ query }, { cwd: config.cwd, taskOptions: to, permissions: so.permissions });
    tasks = swarm.tasks; // share the runtime's store with cc-tasks if enabled
    const existing = (options.mcpServers as Record<string, unknown>) ?? {};
    options.mcpServers = { ...existing, "cc-swarm": createSwarmMcpServer(swarm) };
    // Disable native per-session Task tools so the shared cc-tasks store is authoritative (avoids split-brain).
    const dis = (options.disallowedTools as string[] | undefined) ?? [];
    options.disallowedTools = [...new Set([...dis, ...NATIVE_TASK_TOOLS])];
    if (so.coordinatorPersona) applyCoordinatorPersona(options, so.tools);
  }

  if (config.taskTools) {
    const opts = config.taskTools === true ? {} : config.taskTools;
    tasks = tasks ?? new TaskStore({ cwd: config.cwd, dir: opts.dir, listId: opts.listId, agentName: opts.agentName });
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
    swarm,
  };
}

/** Resume a prior session by id: a thin wrapper over createHarness with `resume` set.
 *  Stateless — the returned handle applies `sessionId` to EVERY run() it makes, so the idiomatic
 *  use is ONE continuation run per handle; thread the returned run().sessionId forward for the next
 *  turn (for linear multi-turn, prefer the daemon's long-lived session). */
export function resumeHarness(sessionId: string, config: HarnessConfig = {}, deps?: HarnessDeps): Harness {
  return createHarness({ ...config, resume: sessionId }, deps);
}
