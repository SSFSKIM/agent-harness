import { describe, it, expect } from "vitest";
import { resolveSandbox } from "../../src/config/sandbox.js";

describe("resolveSandbox", () => {
  it("returns undefined when unset", () => {
    expect(resolveSandbox({})).toBeUndefined();
  });
  it("maps boolean true to enabled sandbox", () => {
    expect(resolveSandbox({ sandbox: true })).toEqual({ enabled: true });
  });
  it("passes object form through with defaults", () => {
    expect(resolveSandbox({ sandbox: { network: true } })).toEqual({ enabled: true, network: true });
  });
});
