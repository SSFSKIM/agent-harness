import type { AgentDefinition } from "@anthropic-ai/claude-agent-sdk";
import { DEFAULTS, type HarnessConfig } from "./types.js";

const READONLY_DISALLOW = ["Edit", "Write", "NotebookEdit"];

export const BUILTIN_AGENTS: Record<string, AgentDefinition> = {
  "general-purpose": {
    description: "General-purpose agent for researching complex questions and multi-step tasks.",
    prompt: "You are a capable general-purpose agent. Complete the assigned task and report results.",
  },
  Explore: {
    description: "Read-only search agent for broad codebase exploration.",
    prompt: "You are a read-only exploration agent. Locate and summarize code; never modify files.",
    disallowedTools: READONLY_DISALLOW,
  },
  Plan: {
    description: "Software architect agent for designing implementation plans.",
    prompt: "You are an architect. Produce step-by-step implementation plans; do not modify files.",
    disallowedTools: READONLY_DISALLOW,
  },
};

export function resolveAgents(config: HarnessConfig): Record<string, AgentDefinition> {
  const includeBuiltins = config.includeBuiltinAgents ?? DEFAULTS.includeBuiltinAgents;
  const base = includeBuiltins ? { ...BUILTIN_AGENTS } : {};
  return { ...base, ...(config.agents ?? {}) };
}
