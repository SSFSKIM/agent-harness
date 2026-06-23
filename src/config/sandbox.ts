import type { HarnessConfig } from "./types.js";

export function resolveSandbox(config: HarnessConfig): Record<string, unknown> | undefined {
  const s = config.sandbox;
  if (s === undefined || s === false) return undefined;
  if (s === true) return { enabled: true };
  // Pass the object through structurally — it is the SDK SandboxSettings shape
  // (enabled/network/filesystem/excludedCommands/failIfUnavailable/…). `enabled`
  // defaults to true; an explicit `enabled: false` in `s` overrides it.
  return { enabled: true, ...s };
}
