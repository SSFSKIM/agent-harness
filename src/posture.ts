export interface Posture { permissionMode: "auto" | "default"; roundTripApprovals: boolean }

export function resolvePosture(args: { approvalPolicy?: string; autoReview: boolean }): Posture {
  if (args.autoReview || args.approvalPolicy === "never") return { permissionMode: "auto", roundTripApprovals: false };
  return { permissionMode: "default", roundTripApprovals: true };
}

/** Best-effort read of the `-c key=value` overrides the Director appends (autonomy.py). */
export function parseConfigFlags(argv: string[]): { autoReview: boolean } {
  let autoReview = false;
  for (let i = 0; i < argv.length; i++) if (argv[i] === "-c" && /^approvals_reviewer\s*=\s*auto_review$/.test(argv[i + 1] ?? "")) autoReview = true;
  return { autoReview };
}
