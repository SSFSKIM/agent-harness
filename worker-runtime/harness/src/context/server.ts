import { createSdkMcpServer, tool } from "@anthropic-ai/claude-agent-sdk";

/** The model-facing tool id the harness must allowlist for the agent to call it. */
export const CONTEXT_TOOL = "mcp__cc-context__GetContextUsage";

/** The subset of the SDK getContextUsage() payload this tool needs (it returns ~17 fields). */
export interface RawContextUsage { totalTokens?: number; maxTokens?: number; autoCompactThreshold?: number; isAutoCompactEnabled?: boolean }
export interface ContextUsageSummary { percentUsed: number; tokensUsed: number; maxTokens: number; tokensRemaining: number; status: "ok" | "approaching-limit" }
/** Late-binding seam: built before query() exists; `query` is set to the active Query the moment query() returns. */
export interface QueryHolder { query?: { getContextUsage(): Promise<RawContextUsage> } }

/** Pure mapping — the one piece of real logic. percentUsed is computed from totalTokens/maxTokens directly
 *  (robust; not the ambiguous SDK `percentage` field). `approaching-limit` honors the SDK's OWN autocompact trigger. */
export function summarizeUsage(raw: RawContextUsage): ContextUsageSummary {
  const tokensUsed = raw.totalTokens ?? 0;
  const maxTokens = raw.maxTokens ?? 0;
  const tokensRemaining = Math.max(0, maxTokens - tokensUsed);
  const percentUsed = maxTokens > 0 ? Math.round((tokensUsed / maxTokens) * 100) : 0;
  const nearAutoCompact = !!raw.isAutoCompactEnabled && typeof raw.autoCompactThreshold === "number" && tokensUsed >= raw.autoCompactThreshold;
  const status = nearAutoCompact || percentUsed >= 80 ? "approaching-limit" : "ok";
  return { percentUsed, tokensUsed, maxTokens, tokensRemaining, status };
}

/** Exported for direct handler testing (mirrors kairos/brief.ts buildBriefTools). */
export function buildContextTools(holder: QueryHolder) {
  return [
    tool("GetContextUsage",
      "Report how full your own context window is: tokens used vs max, percent, and a status flag. Use this to decide whether to wrap up, summarize, or hand off before running low.",
      {},
      async () => {
        try {
          const q = holder.query;
          if (!q) return { content: [{ type: "text" as const, text: "context usage unavailable" }] };
          return { content: [{ type: "text" as const, text: JSON.stringify(summarizeUsage(await q.getContextUsage())) }] };
        } catch { return { content: [{ type: "text" as const, text: "context usage unavailable" }] }; }
      }),
  ];
}

/** Wrap a QueryHolder as an in-process SDK MCP server exposing the GetContextUsage tool. */
export function createContextMcpServer(holder: QueryHolder) {
  return createSdkMcpServer({ name: "cc-context", version: "0.1.0", tools: buildContextTools(holder) });
}

/** Return a COPY of `options` with the cc-context server + its allowed tool merged in (deduped).
 *  Never mutates the input — the single merge path shared by createHarness (lib) and DaemonSession (daemon). */
export function withContextTool(options: Record<string, unknown>, holder: QueryHolder): Record<string, unknown> {
  const existing = (options.mcpServers as Record<string, unknown> | undefined) ?? {};
  const allowed = (options.allowedTools as string[] | undefined) ?? [];
  return {
    ...options,
    mcpServers: { ...existing, "cc-context": createContextMcpServer(holder) },
    allowedTools: [...new Set([...allowed, CONTEXT_TOOL])],
  };
}
