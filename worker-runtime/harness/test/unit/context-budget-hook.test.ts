import { describe, it, expect } from "vitest";
import { buildContextBudgetHooks, withContextBudgetHooks } from "../../src/context/budgetHook.js";
import { resolveContextBudget } from "../../src/context/budget.js";
import type { QueryHolder, RawContextUsage } from "../../src/context/server.js";

const CFG = resolveContextBudget(); // 275k/500k/600k/650k
const MAX = 1_000_000;

/** A holder whose getContextUsage returns whatever `usage` currently points at (mutate between calls). */
function holderAt(box: { raw: RawContextUsage | (() => Promise<RawContextUsage>) }): QueryHolder {
  return { query: { getContextUsage: async () => (typeof box.raw === "function" ? box.raw() : box.raw) } };
}
function usage(tokensUsed: number): RawContextUsage { return { totalTokens: tokensUsed, maxTokens: MAX }; }

/** Pull the single PostToolUse / UserPromptSubmit callbacks out of a built HooksMap. */
function callbacks(hooks: any) {
  return {
    postToolUse: hooks.PostToolUse[0].hooks[0],
    userPromptSubmit: hooks.UserPromptSubmit[0].hooks[0],
    matcher: hooks.PostToolUse[0].matcher,
  };
}
const commit = { tool_name: "Bash", tool_input: { command: "git commit -m 'x'" } } as any;
const ups = { hook_event_name: "UserPromptSubmit", prompt: "next" } as any;
function injected(out: any): string | undefined { return out?.hookSpecificOutput?.additionalContext; }

describe("buildContextBudgetHooks — PostToolUse commit detection", () => {
  it("matches only Bash tools", () => {
    const { matcher } = callbacks(buildContextBudgetHooks(holderAt({ raw: usage(0) }), CFG));
    expect(matcher).toBe("Bash");
  });
  it("a non-git Bash command does NOT arm a checkpoint, so no checkpoint push", async () => {
    const cb = callbacks(buildContextBudgetHooks(holderAt({ raw: usage(CFG.target) }), CFG));
    await cb.postToolUse({ tool_name: "Bash", tool_input: { command: "ls -la" } } as any);
    // target (500k) is below net (600k), and no commit was armed → nothing fires
    expect(injected(await cb.userPromptSubmit(ups))).toBeUndefined();
  });
  it("does not treat `git commit-tree`/`commit-graph` plumbing as a checkpoint", async () => {
    const cb = callbacks(buildContextBudgetHooks(holderAt({ raw: usage(CFG.target) }), CFG));
    await cb.postToolUse({ tool_name: "Bash", tool_input: { command: "git commit-tree HEAD^{tree}" } } as any);
    expect(injected(await cb.userPromptSubmit(ups))).toBeUndefined();
  });
});

describe("buildContextBudgetHooks — checkpoint push", () => {
  it("commit + usage below soft → flag consumed, NO injection (too early)", async () => {
    const cb = callbacks(buildContextBudgetHooks(holderAt({ raw: usage(CFG.soft - 50_000) }), CFG));
    await cb.postToolUse(commit);
    expect(injected(await cb.userPromptSubmit(ups))).toBeUndefined();
  });
  it("commit + usage past target → checkpoint injection naming the token count + RequestCompaction", async () => {
    const cb = callbacks(buildContextBudgetHooks(holderAt({ raw: usage(CFG.target) }), CFG));
    await cb.postToolUse(commit);
    const text = injected(await cb.userPromptSubmit(ups));
    expect(text).toBeTruthy();
    expect(text).toContain("500k");
    expect(text).toContain("RequestCompaction");
  });
  it("checkpoint in the soft–target band reports actual usage + target, never falsely asserts 'past target'", async () => {
    const cb = callbacks(buildContextBudgetHooks(holderAt({ raw: usage(350_000) }), CFG)); // ≥soft(275k), <target(500k)
    await cb.postToolUse(commit);
    const text = injected(await cb.userPromptSubmit(ups))!;
    expect(text).toContain("350k");           // the REAL number, not an overstated threshold
    expect(text).toContain("500k");           // the target, for the model to compare against
    expect(text).toContain("RequestCompaction");
    expect(text).not.toContain("past your");  // must not claim it's already past target when it isn't
  });
  it("a FAILED git commit (nothing to commit) does not arm a checkpoint", async () => {
    const cb = callbacks(buildContextBudgetHooks(holderAt({ raw: usage(CFG.target) }), CFG));
    await cb.postToolUse({ tool_name: "Bash", tool_input: { command: "git commit -m x" },
      tool_response: { stdout: "nothing to commit, working tree clean" } } as any);
    expect(injected(await cb.userPromptSubmit(ups))).toBeUndefined(); // not a real checkpoint, and 500k < net → quiet
  });
  it("the checkpoint flag is one-shot: a second turn without a new commit does not re-fire", async () => {
    const cb = callbacks(buildContextBudgetHooks(holderAt({ raw: usage(CFG.target) }), CFG));
    await cb.postToolUse(commit);
    expect(injected(await cb.userPromptSubmit(ups))).toBeTruthy();
    expect(injected(await cb.userPromptSubmit(ups))).toBeUndefined(); // flag already consumed
  });
});

describe("buildContextBudgetHooks — high-water safety net (no checkpoint)", () => {
  it("usage past net with no commit → high-water injection mentioning RequestCompaction", async () => {
    const cb = callbacks(buildContextBudgetHooks(holderAt({ raw: usage(CFG.net) }), CFG));
    const text = injected(await cb.userPromptSubmit(ups));
    expect(text).toBeTruthy();
    expect(text).toContain("RequestCompaction");
  });
  it("throttles: a second over-net turn does not re-nudge", async () => {
    const cb = callbacks(buildContextBudgetHooks(holderAt({ raw: usage(CFG.net + 20_000) }), CFG));
    expect(injected(await cb.userPromptSubmit(ups))).toBeTruthy();
    expect(injected(await cb.userPromptSubmit(ups))).toBeUndefined();
  });
  it("re-arms after usage drops back under net (e.g. a compaction freed space)", async () => {
    const box: { raw: RawContextUsage } = { raw: usage(CFG.net + 20_000) };
    const cb = callbacks(buildContextBudgetHooks(holderAt(box), CFG));
    expect(injected(await cb.userPromptSubmit(ups))).toBeTruthy();   // first net nudge
    box.raw = usage(CFG.soft);                                       // compaction dropped us back down
    expect(injected(await cb.userPromptSubmit(ups))).toBeUndefined();// below net → quiet
    box.raw = usage(CFG.net + 20_000);                              // climbs again
    expect(injected(await cb.userPromptSubmit(ups))).toBeTruthy();   // re-armed → nudges again
  });
});

describe("buildContextBudgetHooks — turn safety", () => {
  it("getContextUsage throwing yields {} (never breaks the turn)", async () => {
    const holder: QueryHolder = { query: { getContextUsage: async () => { throw new Error("boom"); } } };
    const cb = callbacks(buildContextBudgetHooks(holder, CFG));
    await cb.postToolUse(commit);
    expect(await cb.userPromptSubmit(ups)).toEqual({});
  });
  it("no live query yet yields {}", async () => {
    const cb = callbacks(buildContextBudgetHooks({}, CFG));
    expect(await cb.userPromptSubmit(ups)).toEqual({});
  });
  it("flagCommit never throws on a hostile (circular) tool_response — R23 for the PostToolUse path", async () => {
    const circular: any = {}; circular.self = circular; // JSON.stringify would throw on this
    const cb = callbacks(buildContextBudgetHooks(holderAt({ raw: usage(CFG.soft) }), CFG));
    await expect(cb.postToolUse({ tool_name: "Bash", tool_input: { command: "git commit -m x" }, tool_response: circular } as any))
      .resolves.toEqual({});
  });
});

describe("withContextBudgetHooks", () => {
  it("merges the budget hooks into options.hooks without mutating the input", () => {
    const input: Record<string, unknown> = {};
    const out = withContextBudgetHooks(input, holderAt({ raw: usage(0) }), CFG);
    expect((out.hooks as any).PostToolUse).toBeTruthy();
    expect((out.hooks as any).UserPromptSubmit).toBeTruthy();
    expect(input).toEqual({}); // untouched
  });
  it("composes with pre-existing hooks (concatenates per event)", () => {
    const existing = { UserPromptSubmit: [{ hooks: [async () => ({})] }] };
    const out = withContextBudgetHooks({ hooks: existing }, holderAt({ raw: usage(0) }), CFG);
    expect((out.hooks as any).UserPromptSubmit.length).toBe(2);
  });
});
