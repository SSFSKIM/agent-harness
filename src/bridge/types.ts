import { z } from "zod/v4";

/** A live session the bridge can control. The control methods are optional → the bridge feature-detects
 *  and reports `unsupported` for any the session does not provide (fake/partial sessions, SDK drift). */
export interface ControllableSession {
  setModel?(model?: string): Promise<void>;
  setPermissionMode?(mode: string): Promise<void>;
  setMaxThinkingTokens?(maxTokens: number | null): Promise<void>;
  interrupt?(): Promise<void>;
  getContextUsage?(): Promise<unknown>;
  accountInfo?(): Promise<unknown>;
  capabilities(): Promise<{ models: unknown[]; commands: unknown[]; mcpServers: unknown[] }>;
}

// Full SDK PermissionMode (sdk.d.ts:2055); the bridge translates faithfully and does not restrict the set.
const permissionMode = z.enum(["default", "acceptEdits", "bypassPermissions", "plan", "dontAsk", "auto"]);

export const controlFrame = z.discriminatedUnion("type", [
  z.object({ type: z.literal("initialize") }),
  z.object({ type: z.literal("set_model"), model: z.string().optional() }),
  z.object({ type: z.literal("set_permission_mode"), mode: permissionMode }),
  z.object({ type: z.literal("set_thinking"), maxTokens: z.number().nullable() }),
  z.object({ type: z.literal("interrupt") }),
  z.object({ type: z.literal("context_usage") }),
  z.object({ type: z.literal("account_info") }),
]);
export type ControlFrame = z.infer<typeof controlFrame>;

export type ControlResponse = ({ ok: true } & Record<string, unknown>) | { ok: false; error: string };
