import { DEFAULTS, type HarnessConfig } from "./types.js";
import { resolveSettings } from "./settings.js";
import { resolveSystemPrompt } from "./outputStyle.js";
import { resolveSandbox } from "./sandbox.js";
import { resolveProviderEnv } from "./provider.js";
import { resolveTools } from "./tools.js";
import { resolveAgents } from "./agents.js";
import { resolveAutoModel } from "./autoModel.js";
import { createPermissionGate } from "../permissions/gate.js";

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
  // SDK contract (sdk.d.ts): a provided `env` REPLACES the subprocess environment
  // entirely — it is NOT merged with process.env. Spread process.env first so our
  // provider flags/overrides augment (not erase) PATH/HOME/ANTHROPIC_API_KEY/etc.
  if (Object.keys(env).length) options.env = { ...process.env, ...env };
  const model = config.model ?? DEFAULTS.model;
  options.model = model;
  if (config.fallbackModel) options.fallbackModel = config.fallbackModel;
  if (config.maxTurns !== undefined) options.maxTurns = config.maxTurns;
  const effort = config.effort ?? DEFAULTS.effort;
  if (effort) options.effort = effort;
  if (config.thinking) options.thinking = config.thinking;
  if (config.maxBudgetUsd !== undefined) options.maxBudgetUsd = config.maxBudgetUsd;
  if (config.taskBudget) options.taskBudget = config.taskBudget;
  if (config.includePartialMessages) options.includePartialMessages = config.includePartialMessages;
  if (config.forwardSubagentText) options.forwardSubagentText = config.forwardSubagentText;
  const mode = config.permissionMode ?? DEFAULTS.permissionMode;
  if (mode) options.permissionMode = mode;
  // `auto` is MODEL-GATED (Opus 4.6+/Sonnet 4.6). Force a supported model ONLY when the caller EXPLICITLY
  // chose auto — do NOT run the gate when auto is merely the default, or an explicit non-auto-capable model
  // (e.g. haiku) would be silently overridden to sonnet. The opus-4-8 default is itself auto-capable.
  if (config.permissionMode === "auto") options.model = resolveAutoModel(model);
  // SDK contract: bypassPermissions REQUIRES allowDangerouslySkipPermissions. Centralized here.
  if (mode === "bypassPermissions") options.allowDangerouslySkipPermissions = true;
  if (config.permissionBroker) options.canUseTool = createPermissionGate(config.permissionBroker);
  if (config.mcpServers) options.mcpServers = config.mcpServers;
  if (config.plugins) options.plugins = config.plugins;
  if (config.cwd) options.cwd = config.cwd;
  if (config.resume) options.resume = config.resume;
  if (config.persistSession !== undefined) options.persistSession = config.persistSession;
  if (config.sessionStore) options.sessionStore = config.sessionStore;
  if (config.hooks) options.hooks = config.hooks;
  return { ...options, ...(config.extraOptions ?? {}) };
}
