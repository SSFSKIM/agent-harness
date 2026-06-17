import { createSdkMcpServer, tool } from "@anthropic-ai/claude-agent-sdk";

/** The model-facing tool id the harness must allowlist for the agent to call it. */
export const COMPACT_TOOL = "mcp__cc-compact__RequestCompaction";

/** Late-binding seam: the daemon sets `request` to the session's requestCompaction() after query() starts. */
export interface CompactHolder { request?: () => void }
export interface CompactOutcome { ok: boolean; result?: "success" | "failed"; error?: string; preTokens?: number; postTokens?: number }

/** Pure — scan the collected `/compact` status/boundary frames into a structured outcome. */
export function parseCompactOutcome(frames: unknown[]): CompactOutcome {
  let result: "success" | "failed" | undefined, error: string | undefined, preTokens: number | undefined, postTokens: number | undefined;
  for (const f of frames as any[]) {
    if (f.subtype === "status" && f.compact_result) { result = f.compact_result; error = f.compact_error; }
    if (f.subtype === "compact_boundary") { preTokens = f.compact_metadata?.pre_tokens; postTokens = f.compact_metadata?.post_tokens; }
  }
  return { ok: result === "success", result, error, preTokens, postTokens };
}

/** Exported for direct handler testing (mirrors context/server.ts buildContextTools). */
export function buildCompactTools(holder: CompactHolder) {
  return [
    tool("RequestCompaction",
      "Schedule a context compaction to run at the end of THIS turn (after you finish responding). Call this when your context window is getting full and you want to free space before continuing.",
      {},
      async () => { holder.request?.(); return { content: [{ type: "text" as const, text: "compaction scheduled for the end of this turn" }] }; }),
  ];
}

/** Wrap a CompactHolder as an in-process SDK MCP server exposing the RequestCompaction tool. */
export function createCompactMcpServer(holder: CompactHolder) {
  return createSdkMcpServer({ name: "cc-compact", version: "0.1.0", tools: buildCompactTools(holder) });
}

/** COPY of options with the cc-compact server + its allowed tool merged in (deduped); never mutates input. */
export function withCompactTool(options: Record<string, unknown>, holder: CompactHolder): Record<string, unknown> {
  const existing = (options.mcpServers as Record<string, unknown> | undefined) ?? {};
  const allowed = (options.allowedTools as string[] | undefined) ?? [];
  return { ...options, mcpServers: { ...existing, "cc-compact": createCompactMcpServer(holder) }, allowedTools: [...new Set([...allowed, COMPACT_TOOL])] };
}
