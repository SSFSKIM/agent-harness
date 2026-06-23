// harness/test/unit/auto-model.test.ts
import { describe, it, expect } from "vitest";
import { DEFAULT_AUTO_MODEL, isAutoSupportedModel, resolveAutoModel } from "../../src/config/autoModel.js";

describe("auto-mode model gating", () => {
  it("recognizes supported models (Opus 4.6+/Sonnet 4.6), rejects others", () => {
    expect(isAutoSupportedModel("claude-sonnet-4-6")).toBe(true);
    expect(isAutoSupportedModel("claude-opus-4-8")).toBe(true);
    expect(isAutoSupportedModel("claude-haiku-4-5-20251001")).toBe(false);
    expect(isAutoSupportedModel("claude-sonnet-4-5")).toBe(false);
    expect(isAutoSupportedModel(undefined)).toBe(false);
  });
  it("resolveAutoModel forces DEFAULT for unsupported/absent, preserves supported", () => {
    expect(DEFAULT_AUTO_MODEL).toBe("claude-sonnet-4-6");
    expect(resolveAutoModel("claude-haiku-4-5-20251001")).toBe("claude-sonnet-4-6");
    expect(resolveAutoModel(undefined)).toBe("claude-sonnet-4-6");
    expect(resolveAutoModel("claude-opus-4-6")).toBe("claude-opus-4-6");
  });
});
