import type { HarnessConfig } from "./types.js";

export function resolveSandbox(config: HarnessConfig): Record<string, unknown> | undefined {
  const s = config.sandbox;
  if (s === undefined || s === false) return undefined;
  if (s === true) return { enabled: true };
  return { enabled: s.enabled ?? true, ...(s.network !== undefined ? { network: s.network } : {}),
    ...(s.autoAllowBashIfSandboxed !== undefined ? { autoAllowBashIfSandboxed: s.autoAllowBashIfSandboxed } : {}) };
}
