import { DEFAULTS, type HarnessConfig } from "./types.js";
import { resolveSettings } from "./settings.js";
import { resolveSystemPrompt } from "./outputStyle.js";
import { resolveSandbox } from "./sandbox.js";
import { resolveProviderEnv } from "./provider.js";
import { resolveTools } from "./tools.js";
import { resolveAgents } from "./agents.js";

// Produces a plain object that is structurally the SDK `Options`.
export function resolveOptions(config: HarnessConfig): Record<string, unknown> {
  const settings = resolveSettings(config);
  const systemPrompt = resolveSystemPrompt(config, settings.systemPromptExcludeDynamic);
  const tools = resolveTools(config);
  const sandbox = resolveSandbox(config);
  const env = resolveProviderEnv(config);
  const agents = resolveAgents(config);

  const options: Record<string, unknown> = {
    settingSources: settings.settingSources,
    systemPrompt,
    tools: tools.tools,
    agents,
    enableFileCheckpointing: config.enableFileCheckpointing ?? DEFAULTS.enableFileCheckpointing,
  };
  if (settings.settings) options.settings = settings.settings;
  if (settings.managedSettings) options.managedSettings = settings.managedSettings;
  if (tools.allowedTools) options.allowedTools = tools.allowedTools;
  if (tools.disallowedTools) options.disallowedTools = tools.disallowedTools;
  if (tools.toolAliases) options.toolAliases = tools.toolAliases;
  if (sandbox) options.sandbox = sandbox;
  if (Object.keys(env).length) options.env = env;
  if (config.model) options.model = config.model;
  if (config.fallbackModel) options.fallbackModel = config.fallbackModel;
  if (config.maxTurns !== undefined) options.maxTurns = config.maxTurns;
  if (config.permissionMode) options.permissionMode = config.permissionMode;
  if (config.mcpServers) options.mcpServers = config.mcpServers;
  if (config.plugins) options.plugins = config.plugins;
  if (config.cwd) options.cwd = config.cwd;
  return { ...options, ...(config.extraOptions ?? {}) };
}
