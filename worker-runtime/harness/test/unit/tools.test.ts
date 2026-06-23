import { describe, it, expect } from "vitest";
import { resolveTools } from "../../src/config/tools.js";

describe("resolveTools", () => {
  it("defaults to claude_code preset", () => {
    expect(resolveTools({}).tools).toEqual({ type: "preset", preset: "claude_code" });
  });
  it("toolPreset none yields empty tool list", () => {
    expect(resolveTools({ toolPreset: "none" }).tools).toEqual([]);
  });
  it("derives WebFetch allow rules into allowedTools", () => {
    const out = resolveTools({ webFetchDomains: { allow: ["example.com"] } });
    expect(out.allowedTools).toContain("WebFetch(domain:example.com)");
  });
  it("derives WebFetch deny rules into disallowedTools", () => {
    const out = resolveTools({ webFetchDomains: { deny: ["evil.com"] } });
    expect(out.disallowedTools).toContain("WebFetch(domain:evil.com)");
  });
});
