import { z } from "zod/v4";

export type MessageKind = "text" | "task" | "result" | "idle";

export interface Message {
  from: string;            // sender agent name
  to: string;              // recipient agent name ("coordinator" | teammate name)
  kind: MessageKind;
  body: string;
  ts: string;              // ISO timestamp, stamped by the bus/session
}

export interface TeammateSpec {
  name: string;            // unique within the runtime
  teamId: string;
  agent?: string;          // per-teammate model hint (30.9); forwarded to the teammate query as options.model
  prompt: string;          // seed turn
}

export interface SwarmOptions {
  cwd?: string;
  taskOptions?: { dir?: string; listId?: string; agentName?: string };
}

/** Minimal structural type for the SDK `query` fn so units can be tested with a fake (DI). */
export type QueryFn = (args: { prompt: any; options?: any }) => AsyncIterable<any>;

export class SwarmError extends Error {}

const KIND = z.enum(["text", "task", "result", "idle"]);

// zod raw shapes for the five cc-swarm tools.
export const teamCreateShape = {
  name: z.string(),
  members: z.array(z.string()).optional(),
};
export const teamDeleteShape = { teamId: z.string() };
export const spawnTeammateShape = {
  teamId: z.string(),
  name: z.string(),
  agent: z.string().optional(),
  prompt: z.string(),
};
export const sendMessageShape = {
  to: z.string(),
  body: z.string(),
  kind: KIND.optional(),
};
export const checkMessagesShape = {};

export type TeamCreateInput = z.infer<z.ZodObject<typeof teamCreateShape>>;
export type SpawnTeammateInput = z.infer<z.ZodObject<typeof spawnTeammateShape>>;
export type SendMessageInput = z.infer<z.ZodObject<typeof sendMessageShape>>;
