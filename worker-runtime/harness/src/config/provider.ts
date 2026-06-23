import type { HarnessConfig } from "./types.js";

const PROVIDER_FLAG: Record<string, string | undefined> = {
  anthropic: undefined,
  bedrock: "CLAUDE_CODE_USE_BEDROCK",
  vertex: "CLAUDE_CODE_USE_VERTEX",
  foundry: "CLAUDE_CODE_USE_FOUNDRY",
};

export function resolveProviderEnv(config: HarnessConfig): Record<string, string | undefined> {
  const env: Record<string, string | undefined> = {};
  const flag = PROVIDER_FLAG[config.provider ?? "anthropic"];
  if (flag) env[flag] = "1";
  if (config.baseUrl) env.ANTHROPIC_BASE_URL = config.baseUrl;
  if (config.customHeaders) {
    env.ANTHROPIC_CUSTOM_HEADERS = Object.entries(config.customHeaders)
      .map(([k, v]) => `${k}: ${v}`).join("\n");
  }
  return { ...env, ...(config.env ?? {}) };
}
