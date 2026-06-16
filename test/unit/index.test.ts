import { describe, it, expect } from "vitest";
import * as api from "../../src/index.js";

describe("public API", () => {
  it("exports createHarness, resolveOptions, BUILTIN_AGENTS, BUILTIN_OUTPUT_STYLES", () => {
    expect(typeof api.createHarness).toBe("function");
    expect(typeof api.resolveOptions).toBe("function");
    expect(api.BUILTIN_AGENTS).toBeTruthy();
    expect(api.BUILTIN_OUTPUT_STYLES).toBeTruthy();
  });
});
