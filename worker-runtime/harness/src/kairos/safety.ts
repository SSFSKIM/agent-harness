export interface PostureConfig { permissionMode?: string; allowBypass?: boolean; denyTools?: string[] }

/** Resolve the autonomous-mode permission posture: always native `auto` (the model classifier governs),
 *  unless the caller explicitly escalates to bypass. The denylist is optional defense-in-depth, not a
 *  security boundary (a regex deny is trivially bypassable; the sandbox is the real hardening). */
export function resolveAssistantPosture(config: PostureConfig = {}): { permissionMode: string; disallowedTools?: string[] } {
  if (config.permissionMode === "bypassPermissions" && !config.allowBypass)
    throw new Error("Kairos refuses bypassPermissions in autonomous mode without allowBypass:true");
  const permissionMode = config.permissionMode === "bypassPermissions" ? "bypassPermissions" : "auto";
  const out: { permissionMode: string; disallowedTools?: string[] } = { permissionMode };
  if (config.denyTools && config.denyTools.length) out.disallowedTools = config.denyTools;
  return out;
}
