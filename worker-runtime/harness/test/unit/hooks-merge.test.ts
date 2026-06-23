import { describe, it, expect } from "vitest";
import { mergeHooks } from "../../src/hooks/merge.js";

const m1 = async () => ({});
const m2 = async () => ({});

describe("mergeHooks", () => {
  it("concatenates matcher arrays for the same event, preserving order", () => {
    const a = { PreToolUse: [{ matcher: "Bash", hooks: [m1] }] };
    const b = { PreToolUse: [{ matcher: "Write", hooks: [m2] }] };
    const out = mergeHooks(a, b);
    expect(out.PreToolUse).toHaveLength(2);
    expect(out.PreToolUse![0].matcher).toBe("Bash");
    expect(out.PreToolUse![1].matcher).toBe("Write");
  });
  it("merges distinct events into one map", () => {
    const out = mergeHooks(
      { UserPromptSubmit: [{ hooks: [m1] }] },
      { PostToolUse: [{ hooks: [m2] }] },
    );
    expect(Object.keys(out).sort()).toEqual(["PostToolUse", "UserPromptSubmit"]);
  });
  it("ignores empty/absent matcher arrays and returns {} for no fragments", () => {
    expect(mergeHooks()).toEqual({});
    expect(mergeHooks({ Stop: [] }, {})).toEqual({});
  });
});
