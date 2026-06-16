import { DEFAULTS, type HarnessConfig, type SettingSource } from "./types.js";

export interface ResolvedSettings {
  settingSources: SettingSource[];
  settings?: Record<string, unknown>;
  managedSettings?: Record<string, unknown>;
  systemPromptExcludeDynamic: boolean;
}

export function resolveSettings(config: HarnessConfig): ResolvedSettings {
  const settingSources = config.disableProjectContext
    ? []
    : config.settingSources ?? DEFAULTS.settingSources;
  const systemPromptExcludeDynamic =
    config.excludeDynamicSections ?? config.disableProjectContext ?? false;
  return {
    settingSources,
    settings: config.settings,
    managedSettings: config.managedSettings,
    systemPromptExcludeDynamic,
  };
}
