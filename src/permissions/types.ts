// harness/src/permissions/types.ts
export type PermissionDecision =
  | { kind: "allow_once" }
  | { kind: "allow_always" }   // remembered for the session, by tool name
  | { kind: "deny" };

/** What the broker is asked to decide. UI hints (title/displayName/description) are often ABSENT headlessly
 *  (the bridge that renders them is claude.ai-coupled) — consumers MUST render from toolName + input alone. */
export interface PermissionRequest {
  toolName: string;
  input: Record<string, unknown>;
  toolUseID: string;
  title?: string;
  displayName?: string;
  description?: string;
  signal: AbortSignal;
}

export interface PermissionBroker {
  request(req: PermissionRequest): Promise<PermissionDecision>;
}
