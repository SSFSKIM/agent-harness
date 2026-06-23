import { forkSession as sdkForkSession } from "@anthropic-ai/claude-agent-sdk";
import type { ForkSessionResult } from "@anthropic-ai/claude-agent-sdk";

// Harness convention is `cwd`; the SDK fork fn filters by `dir`. This wrapper does that rename + passthrough
// (plus a DI `deps` default for testability), mirroring sessions/reader.ts. `forkSession` mints a NEW session id
// (the original is untouched); reach the branch with resumeSession(result.sessionId). `upToMessageId` truncates
// the copied transcript at that message (inclusive); omitted = full copy.
export interface ForkSessionOpts { cwd?: string; upToMessageId?: string; title?: string; }

export function forkSession(id: string, opts: ForkSessionOpts = {}, deps = { forkSession: sdkForkSession }): Promise<ForkSessionResult> {
  const { cwd, ...rest } = opts;
  return deps.forkSession(id, { ...rest, ...(cwd ? { dir: cwd } : {}) });
}
