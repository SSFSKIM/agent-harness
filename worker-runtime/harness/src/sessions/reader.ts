import { listSessions as sdkListSessions, getSessionMessages as sdkGetSessionMessages,
         getSessionInfo as sdkGetSessionInfo } from "@anthropic-ai/claude-agent-sdk";
import type { SessionStore, SDKSessionInfo, SessionMessage } from "@anthropic-ai/claude-agent-sdk";

// Harness convention is `cwd`; the SDK readers filter by `dir`. These wrappers' only job is that
// rename (plus passthrough). The SDK persists transcripts to ~/.claude/projects; `dir` scopes to a
// project (and its git worktrees by default). DI `deps` defaults to the real SDK fn for testability.
export interface ListSessionsOpts { cwd?: string; limit?: number; offset?: number; includeWorktrees?: boolean; sessionStore?: SessionStore; }
export interface GetMessagesOpts { cwd?: string; limit?: number; offset?: number; includeSystemMessages?: boolean; sessionStore?: SessionStore; }
export interface GetInfoOpts { cwd?: string; sessionStore?: SessionStore; }

export function listSessions(opts: ListSessionsOpts = {}, deps = { listSessions: sdkListSessions }): Promise<SDKSessionInfo[]> {
  const { cwd, ...rest } = opts;
  return deps.listSessions({ ...rest, ...(cwd ? { dir: cwd } : {}) });
}
export function getSessionMessages(id: string, opts: GetMessagesOpts = {}, deps = { getSessionMessages: sdkGetSessionMessages }): Promise<SessionMessage[]> {
  const { cwd, ...rest } = opts;
  return deps.getSessionMessages(id, { ...rest, ...(cwd ? { dir: cwd } : {}) });
}
export function getSessionInfo(id: string, opts: GetInfoOpts = {}, deps = { getSessionInfo: sdkGetSessionInfo }): Promise<SDKSessionInfo | undefined> {
  const { cwd, ...rest } = opts;
  return deps.getSessionInfo(id, { ...rest, ...(cwd ? { dir: cwd } : {}) });
}
