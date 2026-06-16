import type { PermissionResult } from "@anthropic-ai/claude-agent-sdk";
import { RequestRegistry } from "./requests.js";
import type { PlanDecision } from "./types.js";

export interface PlanApprovalBrokerOptions {
  onRequest?: (teammate: string, req: { plan: string }) => void;
  onEscalate?: (teammate: string, plan: string, requestId: string) => void;
  onApprove?: (teammate: string) => void | Promise<void>;
}

/** Worker→leader plan-approval RPC: every plan-mode teammate's ExitPlanMode escalates here and parks
 * until the coordinator answers via respond(). Shares the bus-RPC RequestRegistry with PermissionBroker. */
export class PlanApprovalBroker {
  private onRequest?: PlanApprovalBrokerOptions["onRequest"];
  private onEscalate?: PlanApprovalBrokerOptions["onEscalate"];
  private onApprove?: PlanApprovalBrokerOptions["onApprove"];
  private requests = new RequestRegistry<PlanDecision>();
  private owners = new Map<string, string>(); // requestId → teammate (for onApprove on respond)

  constructor(opts: PlanApprovalBrokerOptions = {}) {
    this.onRequest = opts.onRequest;
    this.onEscalate = opts.onEscalate;
    this.onApprove = opts.onApprove;
  }

  /** `input` is the full ExitPlanMode tool input (keys: plan, planFilePath); echoed whole on approve. */
  requestApproval(teammate: string, input: Record<string, unknown>): Promise<PermissionResult> {
    const plan = String(input.plan ?? "");
    this.onRequest?.(teammate, { plan });
    const { id, promise } = this.requests.create();
    this.owners.set(id, teammate);
    this.onEscalate?.(teammate, plan, id);
    return promise.then((d) =>
      d.decision === "approve"
        ? { behavior: "allow", updatedInput: input }      // SDK requires updatedInput on allow
        : { behavior: "deny", message: d.feedback ?? "plan rejected" },
    );
  }

  /** Resolve a parked plan request. On approve, fire (and await) onApprove BEFORE resolving so the
   * teammate's mode transition lands before ExitPlanMode is allowed. Unknown id → false. If onApprove
   * throws (e.g. setPermissionMode rejects), deny instead of leaving the teammate parked forever. */
  async respond(requestId: string, decision: "approve" | "reject", feedback?: string): Promise<boolean> {
    const teammate = this.owners.get(requestId);
    if (teammate === undefined) return false;
    this.owners.delete(requestId); // committed to handling this id; never leave the owner behind
    if (decision === "approve") {
      try {
        await this.onApprove?.(teammate);
      } catch (e) {
        return this.requests.resolve(requestId, { decision: "reject", feedback: `approval failed: ${(e as Error).message}` });
      }
    }
    return this.requests.resolve(requestId, { decision, feedback });
  }

  /** Resolve (as deny) every plan parked for a teammate and forget them — called on teardown so a
   * disposed teammate's parked ExitPlanMode promise can't leak in the registry. Returns the count. */
  cancelFor(teammate: string, reason = "teammate stopped"): number {
    let n = 0;
    for (const [id, owner] of this.owners) {
      if (owner !== teammate) continue;
      this.requests.resolve(id, { decision: "reject", feedback: reason });
      this.owners.delete(id);
      n++;
    }
    return n;
  }
}
