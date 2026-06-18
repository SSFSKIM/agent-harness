import type { AgentDefinition, McpServerConfig, PermissionMode, SdkPluginConfig, SessionStore, EffortLevel, ThinkingConfig } from "@anthropic-ai/claude-agent-sdk";
import type { HooksMap } from "../hooks/types.js";

export type SettingSource = "user" | "project" | "local";

export interface HarnessConfig {
  cwd?: string;
  model?: string;
  fallbackModel?: string;
  maxTurns?: number;
  // turn controls (verified live 2026-06-18; specs/2026-06-18-sdk-capability-closeout-design.md)
  effort?: EffortLevel;                    // 'low'|'medium'|'high'|'xhigh'|'max' — reasoning effort
  thinking?: ThinkingConfig;               // {type:'adaptive'|'disabled'} | {type:'enabled',budgetTokens}
  maxBudgetUsd?: number;                   // hard USD ceiling; EXCEEDED → hard stop: throws OR empty result (timing-dependent)
  taskBudget?: { total: number };          // token-pacing hint; opus-4-8-only (sonnet/haiku return 400)
  includePartialMessages?: boolean;        // emit SDKPartialAssistantMessage stream_event frames
  forwardSubagentText?: boolean;           // forward nested subagent text/thinking (parent_tool_use_id set)
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
  // permissionMode: 6 SDK modes. acceptEdits auto-accepts edits but still routes non-edit tools to
  // canUseTool; dontAsk replaces canUseTool entirely (joins auto/bypass as broker-replacing) — verified.
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
  // hooks (domain 8): programmatic SDK hooks (Partial<Record<HookEvent, HookCallbackMatcher[]>>).
  // Build with the src/hooks builders + mergeHooks. NOTE: SessionStart/SessionEnd do NOT fire via
  // this programmatic path (verified) — no builder exists for them; raw passthrough is the user's choice.
  hooks?: HooksMap;
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
