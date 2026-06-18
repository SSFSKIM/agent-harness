import { z } from "zod/v4";

/** Thrown at the public front doors on a malformed config — mirrors DaemonError / SwarmError / TaskError. */
export class HarnessConfigError extends Error {}

// Validates ONLY the fields with invalidate-able constraints; z.looseObject() leaves every other field
// (incl. escape hatches extraOptions/settings/managedSettings/customHeaders) untouched.
export const harnessConfigSchema = z.looseObject({
  model: z.string().min(1).optional(),
  fallbackModel: z.string().min(1).optional(),
  maxTurns: z.number().int().positive().optional(),
  maxBudgetUsd: z.number().nonnegative().optional(),
  effort: z.enum(["low", "medium", "high", "xhigh", "max"]).optional(),
  permissionMode: z.enum(["default", "plan", "acceptEdits", "auto", "bypassPermissions", "dontAsk"]).optional(),
  provider: z.enum(["anthropic", "bedrock", "vertex", "foundry"]).optional(),
  toolPreset: z.enum(["claude_code", "none"]).optional(),
  thinking: z.union([
    z.object({ type: z.enum(["adaptive", "disabled"]) }),
    z.object({ type: z.literal("enabled"), budgetTokens: z.number().int().positive().optional() }),
  ]).optional(),
  taskBudget: z.object({ total: z.number().int().positive() }).optional(),
  settingSources: z.array(z.enum(["user", "project", "local"])).optional(),
  autoCompactWindow: z.number().int().positive().optional(),
  sandbox: z.union([z.boolean(), z.record(z.string(), z.unknown())]).optional(),
});

export const daemonOptionsSchema = z.looseObject({
  model: z.string().min(1).optional(),
  restart: z.enum(["no", "on-failure"]).optional(),
  maxSessions: z.number().int().positive().optional(),
  idleTimeoutMs: z.number().int().nonnegative().optional(),
  maxRestarts: z.number().int().nonnegative().optional(),
});

function check(schema: z.ZodType, value: unknown): void {
  const r = schema.safeParse(value);
  if (!r.success) { const i = r.error.issues[0]; throw new HarnessConfigError(`invalid config at ${i.path.join(".") || "(root)"}: ${i.message}`); }
}

export function validateHarnessConfig(config: unknown): void { check(harnessConfigSchema, config); }
export function validateDaemonOptions(opts: unknown): void { check(daemonOptionsSchema, opts); }
