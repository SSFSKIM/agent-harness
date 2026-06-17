import { describe, it, expect } from "vitest";
import { injectContext, guardTool, blockTool, observe } from "../../src/hooks/builders.js";

// Invoke the single produced callback with a fake input and return its output.
async function fire(map: any, event: string, input: any) {
  const cb = map[event][0].hooks[0];
  return cb(input, undefined, { signal: new AbortController().signal });
}

describe("injectContext", () => {
  it("returns UserPromptSubmit additionalContext when fn yields text", async () => {
    const map = injectContext(() => "remember: ORCHID");
    expect(map.UserPromptSubmit).toBeTruthy();
    const out: any = await fire(map, "UserPromptSubmit", { hook_event_name: "UserPromptSubmit", prompt: "hi" });
    expect(out.hookSpecificOutput).toEqual({ hookEventName: "UserPromptSubmit", additionalContext: "remember: ORCHID" });
  });
  it("returns {} when fn yields null or empty string", async () => {
    expect(await fire(injectContext(() => null), "UserPromptSubmit", {})).toEqual({});
    expect(await fire(injectContext(() => ""), "UserPromptSubmit", {})).toEqual({});
  });
});

describe("guardTool", () => {
  it("maps {block:true,reason} to a PreToolUse deny", async () => {
    const map = guardTool("Bash", () => ({ block: true, reason: "nope" }));
    expect(map.PreToolUse![0].matcher).toBe("Bash");
    const out: any = await fire(map, "PreToolUse", { hook_event_name: "PreToolUse", tool_name: "Bash" });
    expect(out.decision).toBe("block");
    expect(out.reason).toBe("nope");
    expect(out.hookSpecificOutput).toEqual({ hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: "nope" });
  });
  it("returns {} for allow and for void", async () => {
    expect(await fire(guardTool("Bash", () => ({ allow: true })), "PreToolUse", {})).toEqual({});
    expect(await fire(guardTool("Bash", () => undefined), "PreToolUse", {})).toEqual({});
  });
});

describe("blockTool", () => {
  it("blocks when the RegExp matches the serialized tool_input", async () => {
    const map = blockTool("Bash", /rm -rf/, "danger");
    const out: any = await fire(map, "PreToolUse", { tool_name: "Bash", tool_input: { command: "rm -rf /" } });
    expect(out.decision).toBe("block");
    expect(out.hookSpecificOutput.permissionDecisionReason).toBe("danger");
  });
  it("allows ({}) when the RegExp misses", async () => {
    const out: any = await fire(blockTool("Bash", /rm -rf/), "PreToolUse", { tool_name: "Bash", tool_input: { command: "ls" } });
    expect(out).toEqual({});
  });
  it("honors a predicate test", async () => {
    const map = blockTool("Write", (i: any) => i.tool_input?.path === "/etc/passwd", "blocked");
    const hit: any = await fire(map, "PreToolUse", { tool_input: { path: "/etc/passwd" } });
    expect(hit.decision).toBe("block");
    const miss: any = await fire(map, "PreToolUse", { tool_input: { path: "/tmp/x" } });
    expect(miss).toEqual({});
  });
});

describe("observe", () => {
  it("invokes fn with the input and returns {}", async () => {
    const seen: any[] = [];
    const map = observe("PostToolUse", (i) => { seen.push(i); });
    expect(map.PostToolUse).toBeTruthy();
    const out = await fire(map, "PostToolUse", { hook_event_name: "PostToolUse", tool_name: "Bash" });
    expect(out).toEqual({});
    expect(seen[0].tool_name).toBe("Bash");
  });
  it("swallows a throwing observer and still returns {}", async () => {
    const map = observe("Stop", () => { throw new Error("boom"); });
    expect(await fire(map, "Stop", {})).toEqual({});
  });
});
