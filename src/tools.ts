import { createSdkMcpServer, tool } from "@anthropic-ai/claude-agent-sdk";
import { z } from "zod";
import type { Outcome } from "./protocol.js";

export const REPORT_OUTCOME_TOOL_ID = "mcp__cc-appserver__report_outcome";
export interface OutcomeHolder { outcome?: Outcome }

const DESC = "Report the TERMINAL outcome of your work on THIS ticket. Call it exactly once, only when work truly ends: " +
  "status=done when complete; status=blocked when you cannot proceed and have filed follow-up tickets (ids in spawned_ticket_ids); " +
  "status=needs_human when a product/taste decision is required. Do NOT call it to ask whether to continue.";

/** Exported for direct handler testing (mirrors buildContextTools). */
export function buildReportOutcomeTools(holder: OutcomeHolder) {
  return [
    tool("report_outcome", DESC, {
      status: z.enum(["done", "blocked", "needs_human"]),
      reason: z.string(),
      spawned_ticket_ids: z.array(z.string()).optional(),
      pr_url: z.string().optional(),
      pr_branch: z.string().optional(),
      checks_state: z.string().optional(),
      unresolved_threads: z.number().optional(),
      acceptance_verified: z.boolean().optional(),
    }, async (args: any) => {
      const evidence: Record<string, unknown> = {};
      for (const k of ["checks_state", "unresolved_threads", "acceptance_verified"]) if (args[k] !== undefined) evidence[k] = args[k];
      holder.outcome = { status: args.status, reason: args.reason, spawned_ticket_ids: args.spawned_ticket_ids ?? [], pr_url: args.pr_url, pr_branch: args.pr_branch, evidence: Object.keys(evidence).length ? evidence : undefined };
      return { content: [{ type: "text" as const, text: "outcome recorded" }] };
    }),
  ];
}

export function buildReportOutcomeServer(holder: OutcomeHolder) {
  return createSdkMcpServer({ name: "cc-appserver", version: "0.1.0", tools: buildReportOutcomeTools(holder) });
}

/** COPY of cfg with the report_outcome server + allowed tool merged (never mutates; mirrors withContextTool). */
export function withReportOutcome(cfg: any, holder: OutcomeHolder): any {
  const existing = (cfg.mcpServers as Record<string, unknown> | undefined) ?? {};
  const allowed = (cfg.allowedTools as string[] | undefined) ?? [];
  return { ...cfg, mcpServers: { ...existing, "cc-appserver": buildReportOutcomeServer(holder) }, allowedTools: [...new Set([...allowed, REPORT_OUTCOME_TOOL_ID])] };
}
