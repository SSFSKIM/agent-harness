import type { AgentDefinition, McpServerConfig, PermissionMode, SdkPluginConfig } from "@anthropic-ai/claude-agent-sdk";

export type SettingSource = "user" | "project" | "local";

export interface HarnessConfig {
  cwd?: string;
  model?: string;
  fallbackModel?: string;
  maxTurns?: number;
  // settings / context
  settingSources?: SettingSource[];        // default all three
  settings?: Record<string, unknown>;      // inline settings object passed to SDK
  managedSettings?: Record<string, unknown>;
  disableProjectContext?: boolean;         // → settingSources [] (skip CLAUDE.md/files)
  excludeDynamicSections?: boolean;        // drop git/date dynamic blocks
  // persona
  outputStyle?: string;                    // mapped to systemPrompt preset append
  appendSystemPrompt?: string;             // extra append text
  // permissions / tools
  permissionMode?: PermissionMode;
  allowedTools?: string[];
  disallowedTools?: string[];
  toolPreset?: "claude_code" | "none";     // default claude_code
  toolAliases?: Record<string, string>;
  webFetchDomains?: { allow?: string[]; deny?: string[] };
  // sandbox
  sandbox?: boolean | { enabled?: boolean; network?: boolean; autoAllowBashIfSandboxed?: boolean };
  // provider
  provider?: "anthropic" | "bedrock" | "vertex" | "foundry";
  baseUrl?: string;
  customHeaders?: Record<string, string>;
  // agents
  agents?: Record<string, AgentDefinition>;
  includeBuiltinAgents?: boolean;          // default true
  // checkpointing / mcp / plugins
  enableFileCheckpointing?: boolean;       // default true
  mcpServers?: Record<string, McpServerConfig>;
  plugins?: SdkPluginConfig[];
  // escape hatches
  env?: Record<string, string | undefined>;
  extraOptions?: Record<string, unknown>;  // merged last into SDK Options
}

export const DEFAULTS = {
  settingSources: ["user", "project", "local"] as SettingSource[],
  includeBuiltinAgents: true,
  enableFileCheckpointing: true,
  toolPreset: "claude_code" as const,
  provider: "anthropic" as const,
};
