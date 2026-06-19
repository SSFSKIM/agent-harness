import { describe, it, expect } from "vitest";
import * as api from "../../src/index.js";

describe("public API", () => {
  it("exports createHarness, resolveOptions, BUILTIN_AGENTS, BUILTIN_OUTPUT_STYLES", () => {
    expect(typeof api.createHarness).toBe("function");
    expect(typeof api.resolveOptions).toBe("function");
    expect(api.BUILTIN_AGENTS).toBeTruthy();
    expect(api.BUILTIN_OUTPUT_STYLES).toBeTruthy();
    expect(typeof api.resumeHarness).toBe("function");
    expect(typeof api.listSessions).toBe("function");
    expect(typeof api.getSessionMessages).toBe("function");
    expect(typeof api.getSessionInfo).toBe("function");
    expect(typeof api.createContextMcpServer).toBe("function");
    expect(typeof api.summarizeUsage).toBe("function");
    expect(typeof api.createCompactMcpServer).toBe("function");
    expect(typeof api.openSession).toBe("function");
    expect(typeof api.resumeSession).toBe("function");
    expect(typeof api.Session).toBe("function");
    expect(typeof api.forkSession).toBe("function");
  });
  it("exports the session-store mutation wrappers", () => {
    expect(typeof api.renameSession).toBe("function");
    expect(typeof api.tagSession).toBe("function");
    expect(typeof api.deleteSession).toBe("function");
  });
  it("exports the hook builders and mergeHooks", () => {
    expect(typeof api.injectContext).toBe("function");
    expect(typeof api.guardTool).toBe("function");
    expect(typeof api.blockTool).toBe("function");
    expect(typeof api.observe).toBe("function");
    expect(typeof api.mergeHooks).toBe("function");
  });
  it("exports the daemon client + dashboard snapshot (advanced-seam, increment 2)", () => {
    expect(typeof api.connectDaemon).toBe("function");
    expect(typeof api.collect).toBe("function");
  });
  it("exports the permission seam (advanced-seam, increment 3)", () => {
    expect(typeof api.createPermissionGate).toBe("function");
  });
  it("exports the PendingEntry wire type (advanced-seam, increment 4)", () => {
    const _pe: api.PendingEntry = { sessionId: "s", toolUseID: "t", toolName: "Edit", input: {}, createdAt: 0 };
    expect(_pe.toolUseID).toBe("t");
  });
  it("exports the daemon permission client methods on connectDaemon's return (advanced-seam, increment 4)", () => {
    const c = api.connectDaemon("/x", (async () => []) as any);
    expect(typeof c.pendingPermissions).toBe("function");
    expect(typeof c.respondPermission).toBe("function");
  });
  it("does NOT export internal plumbing from the package root (boundary curation)", () => {
    for (const name of ["SessionRegistry", "MessageBus", "parseCompactOutcome"]) // value exports (type-only QueryHolder/CompactHolder are erased)
      expect(api).not.toHaveProperty(name);
  });
  it("exports the config validator + error (api-hardening)", () => {
    expect(typeof api.validateHarnessConfig).toBe("function");
    expect(typeof api.HarnessConfigError).toBe("function");
  });
  it("freezes the full public value-export surface (deliberate-update gate)", () => {
    const EXPECTED: string[] = [
      "BUILTIN_AGENTS",
      "BUILTIN_OUTPUT_STYLES",
      "COMPACT_TOOL",
      "CONTEXT_TOOL",
      "DEFAULTS",
      "DaemonError",
      "DaemonServer",
      "DaemonSupervisor",
      "HarnessConfigError",
      "KairosAssistant",
      "Session",
      "SwarmError",
      "SwarmRuntime",
      "TaskError",
      "TaskStore",
      "applyAssistantPersona",
      "blockTool",
      "collect",
      "connectDaemon",
      "createBriefMcpServer",
      "createCompactMcpServer",
      "createContextMcpServer",
      "createHarness",
      "createPermissionGate",
      "createSwarmMcpServer",
      "createTaskMcpServer",
      "daemonRequest",
      "daemonSocketPath",
      "deleteSession",
      "forkSession",
      "getSessionInfo",
      "getSessionMessages",
      "guardTool",
      "injectContext",
      "listSessions",
      "mergeHooks",
      "observe",
      "openSession",
      "renameSession",
      "resolveAssistantPosture",
      "resolveOptions",
      "resumeHarness",
      "resumeSession",
      "stdoutBriefSink",
      "summarizeUsage",
      "tagSession",
      "validateHarnessConfig",
    ];
    expect(Object.keys(api).sort()).toEqual(EXPECTED);
  });
});
