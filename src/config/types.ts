import type { AgentDefinition, McpServerConfig, PermissionMode, SdkPluginConfig, SessionStore } from "@anthropic-ai/claude-agent-sdk";

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
  // sandbox — `network` mirrors the SDK SandboxNetworkSettings object
  // (allowedDomains/allowLocalBinding/allowUnixSockets/…), NOT a boolean.
  sandbox?: boolean | { enabled?: boolean; network?: Record<string, unknown>; autoAllowBashIfSandboxed?: boolean };
  // provider
  provider?: "anthropic" | "bedrock" | "vertex" | "foundry";
  baseUrl?: string;
  customHeaders?: Record<string, string>;
  // agents
  agents?: Record<string, AgentDefinition>;
  includeBuiltinAgents?: boolean;          // default true
  // checkpointing / mcp / plugins
  enableFileCheckpointing?: boolean;       // default true
  // session persistence — the SDK persists transcripts to ~/.claude/projects by default
  resume?: string;                         // SDK session_id to reload prior context
  persistSession?: boolean;                // default SDK-true; false = ephemeral (no disk persistence)
  sessionStore?: SessionStore;             // BYO transcript-mirror backend (advanced; pure passthrough)
  // compaction (Spec B): tune/disable the SDK's native auto-compaction (these are SDK Settings fields)
  autoCompactEnabled?: boolean;            // false disables the native ~167k safety net
  autoCompactWindow?: number;              // tokens of headroom before auto-compaction
  // task tools (Phase 2 A1): durable Task* MCP server
  taskTools?: boolean | { dir?: string; listId?: string; agentName?: string };
  // swarm / coordinator (Phase 2 A2): peer teammate orchestration over an in-process bus
  swarm?: boolean | { team?: string; coordinatorPersona?: boolean; tools?: string[]; permissions?: { allow?: string[]; escalateToCoordinator?: boolean; onPlanApproval?: "default" | "acceptEdits" | "auto" | "bypassPermissions" } };
  // context introspection (domain 6, agent-facing): expose a GetContextUsage MCP tool to the model
  contextTool?: boolean;
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
