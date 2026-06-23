// harness/src/permissions/gate.ts
import type { PermissionBroker, PermissionDecision, PermissionRequest } from "./types.js";

// The SDK CanUseTool shape (sdk.d.ts): (toolName, input, options) => Promise<PermissionResult>.
type CanUseToolOptions = { signal: AbortSignal; toolUseID: string; title?: string; displayName?: string; description?: string; [k: string]: unknown };
type PermissionResult = { behavior: "allow"; updatedInput: Record<string, unknown> } | { behavior: "deny"; message: string; interrupt?: boolean };
export type CanUseTool = (toolName: string, input: Record<string, unknown>, options: CanUseToolOptions) => Promise<PermissionResult>;

// Resolve the broker, but lose the race to an abort (turn interrupted) → deny. Pre-aborted → deny immediately.
function requestOrAbort(broker: PermissionBroker, req: PermissionRequest, signal: AbortSignal): Promise<PermissionDecision> {
  if (signal?.aborted) return Promise.resolve({ kind: "deny" });
  return new Promise((resolve) => {
    signal?.addEventListener("abort", () => resolve({ kind: "deny" }), { once: true });
    broker.request(req).then((d) => resolve(d), () => resolve({ kind: "deny" }));
  });
}

/** Build the SDK canUseTool from an interactive broker. Owns the per-session "always" allowlist:
 *  a tool in the set is allowed immediately, never re-consulting the broker. */
export function createPermissionGate(broker: PermissionBroker): CanUseTool {
  const allowed = new Set<string>();
  return async (toolName, input, options) => {
    if (allowed.has(toolName)) return { behavior: "allow", updatedInput: input };
    const req: PermissionRequest = { toolName, input, toolUseID: options.toolUseID, title: options.title, displayName: options.displayName, description: options.description, signal: options.signal };
    const decision = await requestOrAbort(broker, req, options.signal);
    if (decision.kind === "deny") return { behavior: "deny", message: `User denied ${toolName}`, interrupt: options.signal?.aborted || undefined };
    if (decision.kind === "allow_always") allowed.add(toolName);
    return { behavior: "allow", updatedInput: input };
  };
}
