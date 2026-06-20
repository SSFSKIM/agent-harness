import { z } from "zod/v4";
import { controlFrame } from "../bridge/types.js";
import { proactiveConfig } from "../proactive/types.js";
import type { ProactiveStatus } from "../proactive/types.js";

export class DaemonError extends Error {}

export type SessionStatus = "idle" | "busy" | "errored" | "restarting";
export type RestartPolicy = "no" | "on-failure";

export interface SessionRecord {
  id: string;
  daemonPid: number;
  status: SessionStatus;
  model?: string;
  permissionMode?: string;        // live permission mode (Increment C); written back on set_permission_mode
  restart?: RestartPolicy;   // persisted spawn restart posture, for faithful boot-rehydration
  sessionId?: string;      // the SDK session_id (captured from Session.sessionId), for durable resume (Spec 2)
  createdAt: number;
  lastActiveAt: number;
  restarts?: number;       // count of automatic restarts (D2)
}

/** A live-pool entry on the wire: a SessionRecord enriched with the session's proactive status (if any). */
export type ListEntry = SessionRecord & { proactive?: ProactiveStatus };

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
  sessionOptions?: (sessionId: string) => Record<string, unknown>; // per-session options merged over { model } (D3)
  sharedTasks?: boolean | { dir?: string; listId?: string };       // wire a shared cc-tasks store into every session (D3)
  contextTool?: boolean;   // daemon-wide: expose the cc-context GetContextUsage tool to every session's agent (D6)
  compactTool?: boolean;   // daemon-wide: expose the cc-compact RequestCompaction tool to every session's agent (Spec B)
  permissionTimeoutMs?: number; // parked permission-request lifetime before auto-deny (default 30_000)
  rehydrate?: boolean;     // adopt orphaned sessions on boot (resume on first access) instead of reaping them; default false
  isAlive?: (pid: number) => boolean; // override the daemonPid-liveness check (testing seam; default process.kill(pid,0))
}

// NDJSON op protocol (one request per client connection).
const spawnOp = z.object({ op: z.literal("spawn"), model: z.string().optional(), restart: z.enum(["no", "on-failure"]).optional(), resume: z.string().optional(), permissionMode: z.string().optional() });
const submitOp = z.object({ op: z.literal("submit"), id: z.string(), prompt: z.string() });
const listOp = z.object({ op: z.literal("list") });
const stopOp = z.object({ op: z.literal("stop"), id: z.string() });
const shutdownOp = z.object({ op: z.literal("shutdown") });
const controlOp = z.object({ op: z.literal("control"), id: z.string(), frame: controlFrame });
const startProactiveOp = z.object({ op: z.literal("start_proactive"), id: z.string(), config: proactiveConfig.optional() });
const stopProactiveOp = z.object({ op: z.literal("stop_proactive"), id: z.string() });
const sessionsOp = z.object({ op: z.literal("sessions"), cwd: z.string().optional(), limit: z.number().optional(), offset: z.number().optional() });
const messagesOp = z.object({ op: z.literal("messages"), id: z.string(), cwd: z.string().optional(), limit: z.number().optional(), offset: z.number().optional() });
const compactOp = z.object({ op: z.literal("compact"), id: z.string() });
const forkOp = z.object({ op: z.literal("fork"), id: z.string() });
const usageOp = z.object({ op: z.literal("usage"), id: z.string() });
const initOp = z.object({ op: z.literal("init"), id: z.string() });
const applyFlagSettingsOp = z.object({ op: z.literal("apply_flag_settings"), id: z.string(), settings: z.record(z.string(), z.unknown()) });
const renameSessionOp = z.object({ op: z.literal("rename"), id: z.string(), title: z.string(), cwd: z.string().optional() });
const tagSessionOp = z.object({ op: z.literal("tag"), id: z.string(), tag: z.string().nullable(), cwd: z.string().optional() });
const deleteSessionOp = z.object({ op: z.literal("delete"), id: z.string(), cwd: z.string().optional() });
const permissionDecision = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("allow_once") }),
  z.object({ kind: z.literal("allow_always") }),
  z.object({ kind: z.literal("deny") }),
]);
const pendingPermissionsOp = z.object({ op: z.literal("pending_permissions") });
const permissionResponseOp = z.object({ op: z.literal("permission_response"), toolUseID: z.string(), decision: permissionDecision });

export const daemonOp = z.discriminatedUnion("op", [spawnOp, submitOp, listOp, stopOp, shutdownOp, controlOp, startProactiveOp, stopProactiveOp, sessionsOp, messagesOp, compactOp, forkOp, usageOp, initOp, applyFlagSettingsOp, renameSessionOp, tagSessionOp, deleteSessionOp, pendingPermissionsOp, permissionResponseOp]);
export type DaemonOp = z.infer<typeof daemonOp>;
