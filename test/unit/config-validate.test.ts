import { describe, it, expect } from "vitest";
import { validateHarnessConfig, validateDaemonOptions, HarnessConfigError } from "../../src/config/validate.js";

describe("validateHarnessConfig", () => {
  it("accepts a valid config and passes escape-hatch fields untouched", () => {
    expect(() => validateHarnessConfig({ model: "claude-haiku-4-5", maxTurns: 3, effort: "high",
      thinking: { type: "enabled", budgetTokens: 1024 }, permissionMode: "acceptEdits",
      extraOptions: { anything: 123 }, settings: { whatever: true } })).not.toThrow();
    expect(() => validateHarnessConfig({})).not.toThrow();
  });
  it("rejects bad enums / numerics / shapes with HarnessConfigError naming the path", () => {
    expect(() => validateHarnessConfig({ permissionMode: "bogus" })).toThrow(HarnessConfigError);
    expect(() => validateHarnessConfig({ maxTurns: 0 })).toThrow(/maxTurns/);
    expect(() => validateHarnessConfig({ maxBudgetUsd: -1 })).toThrow(/maxBudgetUsd/);
    expect(() => validateHarnessConfig({ effort: "ultra" })).toThrow(/effort/);
    expect(() => validateHarnessConfig({ thinking: { type: "enabled" } })).toThrow(/thinking/); // missing budgetTokens
    expect(() => validateHarnessConfig({ maxTurns: "five" as any })).toThrow(/maxTurns/);
  });
});
describe("validateDaemonOptions", () => {
  it("accepts valid daemon options and rejects a bad restart / negative bound", () => {
    expect(() => validateDaemonOptions({ model: "m", restart: "on-failure", maxSessions: 8 })).not.toThrow();
    expect(() => validateDaemonOptions({ restart: "sometimes" })).toThrow(HarnessConfigError);
    expect(() => validateDaemonOptions({ maxSessions: -1 })).toThrow(/maxSessions/);
  });
});
