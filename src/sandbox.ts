// Translate the Director's codex-style sandbox posture (a SandboxMode enum + network flag)
// into the Claude Agent SDK's OS-level sandbox (`sandbox: SandboxSettings`) plus L3 permission
// deny rules. The SDK sandbox (Seatbelt on macOS, bubblewrap on Linux) OS-confines Bash
// subprocesses and their children — including subagents' Bash. Native Read/Edit/Write tools
// are NOT OS-sandboxed (only Bash is), so credential reads are blocked separately via
// permission deny rules. See docs/dev: code.claude.com/docs/en/sandboxing + agent-sdk/secure-deployment.

export interface SandboxPlan {
  sandbox?: Record<string, unknown>;   // -> SDK options.sandbox (SandboxSettings)
  settings?: Record<string, unknown>;  // -> SDK options.settings (permission deny rules)
}

// Outbound domains a sandboxed worker's Bash genuinely needs: git over HTTPS, package
// installs, and the Anthropic API. `gh`/`docker` run OUTSIDE the sandbox (excludedCommands)
// because they fail TLS under Seatbelt / are sandbox-incompatible.
export const DEFAULT_SANDBOX_DOMAINS = [
  "github.com", "*.github.com", "codeload.github.com",
  "registry.npmjs.org", "*.npmjs.org",
  "pypi.org", "files.pythonhosted.org",
  "api.anthropic.com",
];

// L3: Bash is OS-sandboxed, but native Read/Edit/Write go through the permission layer, so
// block reads of well-known credential stores here. `//abs` = absolute-path permission rule.
export const CREDENTIAL_DENY_RULES = [
  "Read(//**/.ssh/**)",
  "Read(//**/.aws/**)",
  "Read(//**/.config/gcloud/**)",
  "Read(//**/.config/gh/**)",
  "Read(//**/.git-credentials)",
  "Read(//**/.netrc)",
  "Read(//**/.npmrc)",
  "Read(//**/.docker/config.json)",
  "Read(//**/.kube/config)",
];

export interface SandboxArgs {
  mode?: string;             // codex SandboxMode: read-only | workspace-write | danger-full-access
  autoReview: boolean;       // posture auto -> auto-allow sandboxed Bash (no round-trip approval)
  network: boolean;          // posture network on/off (Director's network_access flag)
  allowedDomains?: string[]; // override DEFAULT_SANDBOX_DOMAINS
  strict?: boolean;          // hard security gate: fail if sandbox deps missing + no escape hatch
}

export function resolveSandbox(args: SandboxArgs): SandboxPlan {
  // No mode requested, or codex's danger-full-access -> no OS sandbox and no deny rules
  // (back-compat / explicit opt-out: full host access, as before this change).
  if (!args.mode || args.mode === "danger-full-access") return {};
  const sandbox: Record<string, unknown> = {
    enabled: true,
    autoAllowBashIfSandboxed: args.autoReview,
    excludedCommands: ["gh *", "docker *"],
    failIfUnavailable: args.strict ?? false,
    network: args.network
      ? { allowedDomains: args.allowedDomains ?? DEFAULT_SANDBOX_DOMAINS }
      : { allowedDomains: [] },  // network off -> no pre-allowed domains (block outbound)
  };
  if (args.strict) sandbox.allowUnsandboxedCommands = false;
  // NB read-only is treated like workspace-write here (sandbox enabled, cwd writable). The
  // worker's posture default is workspace-write; true read-only write-denial is a follow-up.
  return { sandbox, settings: { permissions: { deny: CREDENTIAL_DENY_RULES } } };
}
