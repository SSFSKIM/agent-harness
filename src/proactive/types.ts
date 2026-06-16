import { z } from "zod/v4";
import { DEFAULT_TICK_PROMPT } from "./prompts.js";

export type ProactiveState = "idle" | "running" | "paused" | "stopped";

export interface ProactiveStatus {
  state: ProactiveState;
  tickCount: number;
  idleCount: number;
  errorCount: number;
  reason?: string;
}

/** Injected seams — the loop knows nothing about sessions or networks. */
export interface ProactiveDeps {
  runTurn: (prompt: string) => Promise<{ result: unknown }>; // daemon passes a session.submit wrapper
  schedule: (fn: () => void, ms: number) => () => void;      // returns a cancel (mirrors scheduleRestart)
  idleDetector: (result: unknown) => boolean;                // "did this tick do nothing?"
  interrupt?: () => Promise<void>;                           // bridge.interrupt — pause an in-flight tick
}

export interface ProactiveConfig {
  tickPrompt: string;
  intervalMs: number;
  maxTicks?: number;                                          // undefined → rely on idle/error stop
  idleBackoff: { factor: number; maxIntervalMs: number; stopAfterIdle: number };
  errorBackoff: { factor: number; maxIntervalMs: number; stopAfterErrors: number };
}

const backoffInput = z.object({ factor: z.number().optional(), maxIntervalMs: z.number().optional() });
export const proactiveConfig = z.object({
  tickPrompt: z.string().optional(),
  intervalMs: z.number().optional(),
  maxTicks: z.number().optional(),
  idleBackoff: backoffInput.extend({ stopAfterIdle: z.number().optional() }).optional(),
  errorBackoff: backoffInput.extend({ stopAfterErrors: z.number().optional() }).optional(),
});
export type ProactiveConfigInput = z.infer<typeof proactiveConfig>;

export const DEFAULT_PROACTIVE_CONFIG: ProactiveConfig = {
  tickPrompt: DEFAULT_TICK_PROMPT,
  intervalMs: 60_000,
  idleBackoff: { factor: 2, maxIntervalMs: 900_000, stopAfterIdle: 3 },
  errorBackoff: { factor: 2, maxIntervalMs: 300_000, stopAfterErrors: 5 },
};

/** Fill defaults over a partial input; nested backoff objects merge field-by-field. */
export function resolveProactiveConfig(input?: ProactiveConfigInput): ProactiveConfig {
  return {
    tickPrompt: input?.tickPrompt ?? DEFAULT_PROACTIVE_CONFIG.tickPrompt,
    intervalMs: input?.intervalMs ?? DEFAULT_PROACTIVE_CONFIG.intervalMs,
    maxTicks: input?.maxTicks ?? DEFAULT_PROACTIVE_CONFIG.maxTicks,
    idleBackoff: { ...DEFAULT_PROACTIVE_CONFIG.idleBackoff, ...(input?.idleBackoff ?? {}) },
    errorBackoff: { ...DEFAULT_PROACTIVE_CONFIG.errorBackoff, ...(input?.errorBackoff ?? {}) },
  };
}
