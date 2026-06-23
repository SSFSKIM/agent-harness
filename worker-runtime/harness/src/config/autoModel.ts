// harness/src/config/autoModel.ts
/** Models that support `auto` permission mode on the Anthropic API (Opus 4.6+ or Sonnet 4.6). On an
 *  unsupported model `auto` silently falls back to `default` (probe 18d), so the daemon forces a supported
 *  model when autonomy is requested. */
export const DEFAULT_AUTO_MODEL = "claude-sonnet-4-6";

const SUPPORTED = new Set(["claude-sonnet-4-6", "claude-opus-4-6", "claude-opus-4-7", "claude-opus-4-8"]);

export function isAutoSupportedModel(model: string | undefined): boolean {
  return model !== undefined && SUPPORTED.has(model);
}

/** The model an autonomous session actually runs on: the requested one if it supports `auto`, else DEFAULT. */
export function resolveAutoModel(model?: string): string {
  return isAutoSupportedModel(model) ? model! : DEFAULT_AUTO_MODEL;
}
