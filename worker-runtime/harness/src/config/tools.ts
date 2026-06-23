import type { HarnessConfig } from "./types.js";

export interface ResolvedTools {
  tools: { type: "preset"; preset: "claude_code" } | string[];
  allowedTools?: string[];
  disallowedTools?: string[];
  toolAliases?: Record<string, string>;
}

export function resolveTools(config: HarnessConfig): ResolvedTools {
  const tools = (config.toolPreset ?? "claude_code") === "none"
    ? []
    : { type: "preset" as const, preset: "claude_code" as const };

  const allowedTools = [...(config.allowedTools ?? [])];
  const disallowedTools = [...(config.disallowedTools ?? [])];
  for (const d of config.webFetchDomains?.allow ?? []) allowedTools.push(`WebFetch(domain:${d})`);
  for (const d of config.webFetchDomains?.deny ?? []) disallowedTools.push(`WebFetch(domain:${d})`);

  const out: ResolvedTools = { tools };
  if (allowedTools.length) out.allowedTools = allowedTools;
  if (disallowedTools.length) out.disallowedTools = disallowedTools;
  if (config.toolAliases) out.toolAliases = config.toolAliases;
  return out;
}
