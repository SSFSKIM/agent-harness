import { z } from "zod/v4";

export class DaemonError extends Error {}

export type SessionStatus = "idle" | "busy" | "errored" | "restarting";
export type RestartPolicy = "no" | "on-failure";

export interface SessionRecord {
  id: string;
  daemonPid: number;
  status: SessionStatus;
  model?: string;
  createdAt: number;
  lastActiveAt: number;
  restarts?: number;       // count of automatic restarts (D2)
}

export interface DaemonOptions {
  dir?: string;            // registry dir (default ~/.claude/cc-daemon/sessions)
  maxSessions?: number;    // default 32
  idleTimeoutMs?: number;  // default 30 min; 0 disables idle reaping
  reapEvery?: number;      // reaper interval ms; default 30_000
  now?: () => number;      // injectable clock (testing)
  restart?: RestartPolicy; // daemon-wide default restart policy (default "no")
  maxRestarts?: number;    // cumulative cap before giving up; default 5
  backoffMs?: number;      // base restart backoff; default 500
  maxBackoffMs?: number;   // backoff cap; default 30_000
  scheduleRestart?: (fn: () => void, ms: number) => () => void; // returns a canceller (testing seam)
}

// NDJSON op protocol (one request per client connection).
const spawnOp = z.object({ op: z.literal("spawn"), model: z.string().optional(), restart: z.enum(["no", "on-failure"]).optional() });
const submitOp = z.object({ op: z.literal("submit"), id: z.string(), prompt: z.string() });
const listOp = z.object({ op: z.literal("list") });
const stopOp = z.object({ op: z.literal("stop"), id: z.string() });
const shutdownOp = z.object({ op: z.literal("shutdown") });

export const daemonOp = z.discriminatedUnion("op", [spawnOp, submitOp, listOp, stopOp, shutdownOp]);
export type DaemonOp = z.infer<typeof daemonOp>;
