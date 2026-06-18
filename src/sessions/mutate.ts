import { renameSession as sdkRenameSession, tagSession as sdkTagSession, deleteSession as sdkDeleteSession } from "@anthropic-ai/claude-agent-sdk";
import type { SessionStore } from "@anthropic-ai/claude-agent-sdk";

// Harness convention is `cwd`; the SDK mutation fns filter by `dir`. These wrappers do that rename +
// passthrough (plus DI `deps`), mirroring sessions/fork.ts + reader.ts. They mutate the PERSISTED
// transcript store (~/.claude/projects), not a live session. renameSession sets the displayed title
// (a `customTitle` field). deleteSession is DESTRUCTIVE and irreversible — afterward the id is gone
// from listSessions and getSessionMessages returns [].
export interface MutateSessionOpts { cwd?: string; sessionStore?: SessionStore; }

export function renameSession(id: string, title: string, opts: MutateSessionOpts = {}, deps = { renameSession: sdkRenameSession }): Promise<void> {
  const { cwd, ...rest } = opts;
  return deps.renameSession(id, title, { ...rest, ...(cwd ? { dir: cwd } : {}) });
}
export function tagSession(id: string, tag: string | null, opts: MutateSessionOpts = {}, deps = { tagSession: sdkTagSession }): Promise<void> {
  const { cwd, ...rest } = opts;
  return deps.tagSession(id, tag, { ...rest, ...(cwd ? { dir: cwd } : {}) });
}
export function deleteSession(id: string, opts: MutateSessionOpts = {}, deps = { deleteSession: sdkDeleteSession }): Promise<void> {
  const { cwd, ...rest } = opts;
  return deps.deleteSession(id, { ...rest, ...(cwd ? { dir: cwd } : {}) });
}
