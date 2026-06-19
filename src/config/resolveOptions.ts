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
  if (config.model) options.model = config.model;
  if (config.fallbackModel) options.fallbackModel = config.fallbackModel;
  if (config.maxTurns !== undefined) options.maxTurns = config.maxTurns;
  if (config.effort) options.effort = config.effort;
  if (config.thinking) options.thinking = config.thinking;
  if (config.maxBudgetUsd !== undefined) options.maxBudgetUsd = config.maxBudgetUsd;
  if (config.taskBudget) options.taskBudget = config.taskBudget;
  if (config.includePartialMessages) options.includePartialMessages = config.includePartialMessages;
  if (config.forwardSubagentText) options.forwardSubagentText = config.forwardSubagentText;
  if (config.permissionMode) options.permissionMode = config.permissionMode;
  // `auto` is MODEL-GATED (Opus 4.6+/Sonnet 4.6); on an unsupported model it silently degrades to `default`
  // (probe 24-P2a). Centralize the gate here — like bypassPermissions below — so every lib/createHarness caller
  // is born auto-safe: force a supported model (a supported explicit one is preserved; undefined → DEFAULT).
  if (config.permissionMode === "auto") options.model = resolveAutoModel(config.model);
  // SDK contract (sdk.d.ts:1719): bypassPermissions REQUIRES allowDangerouslySkipPermissions.
  // Centralize it here so no path (CLI/lib/tests) can set the mode without satisfying it.
  if (config.permissionMode === "bypassPermissions") options.allowDangerouslySkipPermissions = true;
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
