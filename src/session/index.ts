import { query as sdkQuery } from "@anthropic-ai/claude-agent-sdk";
import { resolveOptions } from "../config/resolveOptions.js";
import type { HarnessConfig } from "../config/types.js";
import { Session, type SessionDeps } from "./session.js";

export interface OpenSessionConfig extends HarnessConfig { contextTool?: boolean; compactTool?: boolean; }
export interface SessionDepsInput { query?: SessionDeps["query"]; }

/** Open a new interactive multi-turn session. Honors the full HarnessConfig (via resolveOptions).
 *  `contextTool`/`compactTool` are session-level booleans — they wire the in-process MCP tools, never SDK options. */
export function openSession(config: OpenSessionConfig = {}, deps: SessionDepsInput = {}): Session {
  const query = deps.query ?? sdkQuery;
  return new Session({ query }, resolveOptions(config), { contextTool: config.contextTool, compactTool: config.compactTool });
}

/** Resume a prior session by id. `resume` PRESERVES the session_id, so the returned Session's
 *  .sessionId equals `id` once its first turn's init fires. */
export function resumeSession(id: string, config: OpenSessionConfig = {}, deps?: SessionDepsInput): Session {
  return openSession({ ...config, resume: id }, deps);
}

export { Session };
export type { SessionDeps, SessionOpts } from "./session.js";
