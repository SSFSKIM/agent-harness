import type { PermissionBroker, PermissionDecision, PermissionRequest } from "cc-harness";
import { Peer } from "./peer.js";

const FILE_TOOLS = new Set(["Edit", "Write", "MultiEdit", "NotebookEdit"]);

function mapDecision(decision: string | undefined): PermissionDecision {
  if (decision === "accept") return { kind: "allow_once" };
  if (decision === "acceptForSession") return { kind: "allow_always" };
  return { kind: "deny" };
}

export class AppServerBroker implements PermissionBroker {
  constructor(private peer: Peer, private ctx: { threadId: string; turnId: () => string }) {}
  async request(req: PermissionRequest): Promise<PermissionDecision> {
    const base = { itemId: req.toolUseID, threadId: this.ctx.threadId, turnId: this.ctx.turnId(), availableDecisions: ["accept", "acceptForSession", "decline"] };
    let method: string, params: any;
    if (FILE_TOOLS.has(req.toolName)) {
      method = "item/fileChange/requestApproval";
      params = { ...base, changes: [{ path: req.input.file_path ?? req.input.path, kind: req.toolName }], reason: req.description };
    } else {
      method = "item/commandExecution/requestApproval";
      params = { ...base, command: req.input.command ?? req.toolName, cwd: req.input.cwd, reason: req.description };
    }
    const resp = await this.peer.request(method, params);
    return mapDecision((resp.result as any)?.decision);
  }
}
