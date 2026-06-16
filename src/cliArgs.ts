import type { HarnessConfig } from "./config/types.js";

export interface ParsedArgs { prompt?: string; config: HarnessConfig; }

export function parseArgs(argv: string[]): ParsedArgs {
  const config: HarnessConfig = {};
  let prompt: string | undefined;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--model") config.model = argv[++i];
    else if (a === "--output-style") config.outputStyle = argv[++i];
    else if (a === "--permission-mode") config.permissionMode = argv[++i] as any;
    else if (a === "--max-turns") config.maxTurns = Number(argv[++i]);
    else if (a === "--cwd") config.cwd = argv[++i];
    else if (a === "--no-project-context") config.disableProjectContext = true;
    else if (a === "--sandbox") config.sandbox = true;
    else if (!a.startsWith("--") && prompt === undefined) prompt = a;
  }
  return { prompt, config };
}

export function composePrompt(argPrompt: string | undefined, stdin: string | undefined): string {
  const parts = [argPrompt, stdin].map((s) => (s ?? "").trim()).filter(Boolean);
  return parts.join("\n\n");
}
