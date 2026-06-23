import { DEFAULTS, type HarnessConfig, type SettingSource } from "./types.js";

export interface ResolvedSettings {
  settingSources: SettingSource[];
  settings?: Record<string, unknown>;
  managedSettings?: Record<string, unknown>;
  systemPromptExcludeDynamic: boolean;
}

/** Fold the typed autocompact fields into the inline settings object (they are SDK Settings).
 *  Typed fields win on key collision; returns undefined when nothing is set (preserves prior behavior). */
function mergeAutoCompact(config: HarnessConfig): Record<string, unknown> | undefined {
  const base: Record<string, unknown> = config.settings ? { ...config.settings } : {};
  if (config.autoCompactEnabled !== undefined) base.autoCompactEnabled = config.autoCompactEnabled;
  if (config.autoCompactWindow !== undefined) base.autoCompactWindow = config.autoCompactWindow;
  return Object.keys(base).length ? base : undefined;
}

export function resolveSettings(config: HarnessConfig): ResolvedSettings {
  const settingSources = config.disableProjectContext
    ? []
    : config.settingSources ?? DEFAULTS.settingSources;
  const systemPromptExcludeDynamic =
    config.excludeDynamicSections ?? config.disableProjectContext ?? false;
  return {
    settingSources,
    settings: mergeAutoCompact(config),
    managedSettings: config.managedSettings,
    systemPromptExcludeDynamic,
  };
}
