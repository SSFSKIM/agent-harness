import { describe, it, expect } from "vitest";
import { parseArgs, composePrompt } from "../../src/cliArgs.js";

describe("cli args", () => {
  it("parses prompt and flags", () => {
    const a = parseArgs(["hello world", "--model", "claude-opus-4-8", "--output-style", "explanatory"]);
    expect(a.prompt).toBe("hello world");
    expect(a.config.model).toBe("claude-opus-4-8");
    expect(a.config.outputStyle).toBe("explanatory");
  });
  it("composePrompt appends piped stdin to the arg prompt", () => {
    expect(composePrompt("question", "FILE CONTENT")).toBe("question\n\nFILE CONTENT");
  });
  it("composePrompt uses stdin alone when no arg prompt", () => {
    expect(composePrompt(undefined, "just stdin")).toBe("just stdin");
  });
});
