import { describe, it, expect } from "vitest";
import { resolveAssistantPosture } from "../../src/kairos/safety.js";

describe("assistant safety posture", () => {
  it("defaults to permissionMode auto with no denylist", () => {
    expect(resolveAssistantPosture()).toEqual({ permissionMode: "auto" });
  });
  it("maps denyTools to disallowedTools", () => {
    expect(resolveAssistantPosture({ denyTools: ["Bash(rm *)"] })).toEqual({ permissionMode: "auto", disallowedTools: ["Bash(rm *)"] });
  });
  it("ignores an empty denyTools array", () => {
    expect(resolveAssistantPosture({ denyTools: [] })).toEqual({ permissionMode: "auto" });
  });
  it("refuses bypassPermissions without allowBypass", () => {
    expect(() => resolveAssistantPosture({ permissionMode: "bypassPermissions" })).toThrow(/bypass/i);
  });
  it("permits bypass only with explicit allowBypass escalation", () => {
    expect(resolveAssistantPosture({ permissionMode: "bypassPermissions", allowBypass: true })).toEqual({ permissionMode: "bypassPermissions" });
  });
});
