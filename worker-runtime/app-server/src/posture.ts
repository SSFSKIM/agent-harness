export interface Posture { permissionMode: "auto" | "default"; roundTripApprovals: boolean }

export function resolvePosture(args: { approvalPolicy?: string; autoReview: boolean }): Posture {
  if (args.autoReview || args.approvalPolicy === "never") return { permissionMode: "auto", roundTripApprovals: false };
  return { permissionMode: "default", roundTripApprovals: true };
}

/** Best-effort read of the `-c key=value` overrides the Director appends (autonomy.py):
 *  `approvals_reviewer=auto_review` (auto posture) and
 *  `sandbox_workspace_write.network_access=true` (network on). */
export function parseConfigFlags(argv: string[]): { autoReview: boolean; network: boolean } {
  let autoReview = false, network = false;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] !== "-c") continue;
    const v = argv[i + 1] ?? "";
    if (/^approvals_reviewer\s*=\s*auto_review$/.test(v)) autoReview = true;
    if (/^sandbox_workspace_write\.network_access\s*=\s*true$/.test(v)) network = true;
  }
  return { autoReview, network };
}
