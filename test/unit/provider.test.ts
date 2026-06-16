import { describe, it, expect } from "vitest";
import { resolveProviderEnv } from "../../src/config/provider.js";

describe("resolveProviderEnv", () => {
  it("empty for default anthropic provider with no overrides", () => {
    expect(resolveProviderEnv({})).toEqual({});
  });
  it("sets base url + custom headers", () => {
    expect(resolveProviderEnv({ baseUrl: "https://gw.example", customHeaders: { "X-A": "1" } }))
      .toEqual({ ANTHROPIC_BASE_URL: "https://gw.example", ANTHROPIC_CUSTOM_HEADERS: "X-A: 1" });
  });
  it("sets bedrock flag", () => {
    expect(resolveProviderEnv({ provider: "bedrock" })).toEqual({ CLAUDE_CODE_USE_BEDROCK: "1" });
  });
  it("merges explicit env last", () => {
    expect(resolveProviderEnv({ provider: "vertex", env: { FOO: "bar" } }))
      .toEqual({ CLAUDE_CODE_USE_VERTEX: "1", FOO: "bar" });
  });
});
