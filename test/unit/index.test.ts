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
  it("does NOT export internal plumbing from the package root (boundary curation)", () => {
    for (const name of ["SessionRegistry", "MessageBus", "parseCompactOutcome"]) // value exports (type-only QueryHolder/CompactHolder are erased)
      expect(api).not.toHaveProperty(name);
  });
});
