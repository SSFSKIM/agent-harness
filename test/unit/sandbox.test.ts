// test/unit/sandbox.test.ts
import { describe, it, expect } from "vitest";
import { resolveSandbox, DEFAULT_SANDBOX_DOMAINS, CREDENTIAL_DENY_RULES } from "../../src/sandbox.js";

describe("resolveSandbox (codex posture -> SDK SandboxSettings)", () => {
  it("danger-full-access -> no sandbox, no deny rules (explicit opt-out)", () => {
    expect(resolveSandbox({ mode: "danger-full-access", autoReview: true, network: true })).toEqual({});
  });

  it("undefined mode -> no sandbox (back-compat opt-out)", () => {
    expect(resolveSandbox({ autoReview: true, network: true })).toEqual({});
  });

  it("workspace-write -> enabled sandbox + gh/docker excluded + network allowlist + cred deny", () => {
    const p = resolveSandbox({ mode: "workspace-write", autoReview: true, network: true });
    expect(p.sandbox).toMatchObject({
      enabled: true,
      autoAllowBashIfSandboxed: true,
      excludedCommands: ["gh *", "docker *"],
      failIfUnavailable: false,
      network: { allowedDomains: DEFAULT_SANDBOX_DOMAINS },
    });
    expect(p.settings).toEqual({ permissions: { deny: CREDENTIAL_DENY_RULES } });
  });

  it("autoReview false -> sandboxed Bash still requires approval (no auto-allow)", () => {
    const p = resolveSandbox({ mode: "workspace-write", autoReview: false, network: true });
    expect((p.sandbox as any)?.autoAllowBashIfSandboxed).toBe(false);
  });

  it("network off -> empty allowlist (block sandboxed outbound)", () => {
    const p = resolveSandbox({ mode: "workspace-write", autoReview: true, network: false });
    expect((p.sandbox as any)?.network).toEqual({ allowedDomains: [] });
  });

  it("strict -> hard gate: failIfUnavailable + allowUnsandboxedCommands:false", () => {
    const p = resolveSandbox({ mode: "workspace-write", autoReview: true, network: true, strict: true });
    expect(p.sandbox).toMatchObject({ failIfUnavailable: true, allowUnsandboxedCommands: false });
  });

  it("custom allowedDomains override the default", () => {
    const p = resolveSandbox({ mode: "workspace-write", autoReview: true, network: true, allowedDomains: ["example.com"] });
    expect((p.sandbox as any)?.network).toEqual({ allowedDomains: ["example.com"] });
  });
});
