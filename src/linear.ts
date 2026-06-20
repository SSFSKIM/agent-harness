import { createSdkMcpServer, tool } from "@anthropic-ai/claude-agent-sdk";
import { z } from "zod";

export const LINEAR_TOOL_ID = "mcp__cc-linear__linear_graphql";
const ENDPOINT = "https://api.linear.app/graphql";

async function defaultPost(url: string, body: string, headers: Record<string, string>): Promise<any> {
  const res = await fetch(url, { method: "POST", body, headers });
  return await res.json();
}

/** Reads pass; mutations pass only if forward-only and not obviously destructive. */
export function authorize(query: string): { allowed: boolean; reason?: string } {
  const q = query.trimStart();
  if (!/^mutation\b/i.test(q)) return { allowed: true };
  if (/(delete|archive|remove)/i.test(q)) return { allowed: false, reason: "destructive mutation refused by guardrail" };
  return { allowed: true };
}

export function buildLinearTools(deps: { apiKey: string; post?: (url: string, body: string, headers: Record<string, string>) => Promise<any> }) {
  const post = deps.post ?? defaultPost;
  return [
    tool("linear_graphql", "Execute a raw GraphQL query or mutation against Linear using the session's configured auth.", {
      query: z.string(),
      variables: z.record(z.string(), z.any()).optional(),
    }, async (args: any) => {
      const query = String(args.query ?? "");
      if (!query.trim()) return { content: [{ type: "text" as const, text: "linear_graphql requires a non-empty 'query'" }] };
      const verdict = authorize(query);
      if (!verdict.allowed) return { content: [{ type: "text" as const, text: `blocked by guardrail: ${verdict.reason}` }] };
      try {
        const resp = await post(ENDPOINT, JSON.stringify({ query, variables: args.variables ?? {} }), { "Authorization": deps.apiKey, "Content-Type": "application/json" });
        if (resp?.errors) return { content: [{ type: "text" as const, text: `error: ${JSON.stringify(resp.errors)}` }] };
        return { content: [{ type: "text" as const, text: JSON.stringify(resp?.data ?? resp) }] };
      } catch (e) {
        console.error("[linear]", (e as Error).message);
        return { content: [{ type: "text" as const, text: `linear request failed: ${(e as Error).message}` }] };
      }
    }),
  ];
}

export function withLinear(cfg: any, apiKey: string): any {
  const existing = (cfg.mcpServers as Record<string, unknown> | undefined) ?? {};
  const allowed = (cfg.allowedTools as string[] | undefined) ?? [];
  return {
    ...cfg,
    mcpServers: { ...existing, "cc-linear": createSdkMcpServer({ name: "cc-linear", version: "0.1.0", tools: buildLinearTools({ apiKey }) }) },
    allowedTools: [...new Set([...allowed, LINEAR_TOOL_ID])],
  };
}
