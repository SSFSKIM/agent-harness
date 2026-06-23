import type { PermissionResult } from "@anthropic-ai/claude-agent-sdk";
import { RequestRegistry } from "./requests.js";
import type { PermissionDecision } from "./types.js";

/** Tools every teammate may use without asking: read-only inspection + the shared cc-tasks tools. */
export const DEFAULT_ALLOW = ["Read", "Grep", "Glob", "LS", "mcp__cc-tasks__*"];

export interface PermissionBrokerOptions {
  allow?: string[];
  escalate?: boolean;
  onRequest?: (teammate: string, req: { tool: string; input: Record<string, unknown> }) => void;
  onEscalate?: (teammate: string, tool: string, input: Record<string, unknown>, requestId: string) => void;
}

/** Central canUseTool policy for all teammates: allow / deny / escalate-to-coordinator. */
export class PermissionBroker {
  private allow: string[];
  private escalate: boolean;
  private onRequest?: PermissionBrokerOptions["onRequest"];
  private onEscalate?: PermissionBrokerOptions["onEscalate"];
  private requests = new RequestRegistry<PermissionDecision>();

  constructor(opts: PermissionBrokerOptions = {}) {
    this.allow = opts.allow ?? DEFAULT_ALLOW;
    this.escalate = opts.escalate ?? false;
    this.onRequest = opts.onRequest;
    this.onEscalate = opts.onEscalate;
  }

  private isAllowed(tool: string): boolean {
    return this.allow.some((p) => (p.endsWith("*") ? tool.startsWith(p.slice(0, -1)) : p === tool));
  }

  decide(teammate: string, tool: string, input: Record<string, unknown>): Promise<PermissionResult> {
    this.onRequest?.(teammate, { tool, input });
    // The SDK validates PermissionResult at runtime: an 'allow' MUST carry updatedInput (a record),
    // so echo the original input — a bare { behavior: "allow" } is rejected with a ZodError.
    if (this.isAllowed(tool)) return Promise.resolve({ behavior: "allow", updatedInput: input });
    if (!this.escalate) return Promise.resolve({ behavior: "deny", message: `not permitted: ${tool}` });
    const { id, promise } = this.requests.create();
    this.onEscalate?.(teammate, tool, input, id);
    return promise.then((d) =>
      d.decision === "allow"
        ? { behavior: "allow", updatedInput: input }
        : { behavior: "deny", message: d.message ?? `denied: ${tool}` },
    );
  }

  respond(requestId: string, decision: "allow" | "deny", message?: string): boolean {
    return this.requests.resolve(requestId, { decision, message });
  }
}
