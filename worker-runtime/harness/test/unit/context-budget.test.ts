import { describe, it, expect } from "vitest";
import {
  resolveContextBudget, DEFAULT_CONTEXT_BUDGET, contextBudgetSection, applyContextBudgetPersona,
} from "../../src/context/budget.js";

describe("resolveContextBudget", () => {
  it("defaults to the human-specified band (275k/500k/600k/650k)", () => {
    expect(resolveContextBudget()).toEqual({ soft: 275_000, target: 500_000, net: 600_000, hard: 650_000 });
    expect(resolveContextBudget(true)).toEqual(DEFAULT_CONTEXT_BUDGET);
  });
  it("merges a partial override field-by-field", () => {
    expect(resolveContextBudget({ net: 700_000 })).toEqual({ soft: 275_000, target: 500_000, net: 700_000, hard: 650_000 });
  });
});

describe("contextBudgetSection", () => {
  const s = contextBudgetSection(resolveContextBudget());
  it("states the thresholds taken from config", () => {
    for (const n of ["275k", "500k", "600k", "650k"]) expect(s).toContain(n);
  });
  it("states the architectural anti-anxiety fact: compaction runs AFTER the turn", () => {
    expect(s.toLowerCase()).toContain("after you finish");
  });
  it("carries the explicit anxiety guard", () => {
    expect(s.toLowerCase()).toContain("never end, shorten, or rush");
  });
  it("text tracks the config numbers (override flows into prose)", () => {
    expect(contextBudgetSection(resolveContextBudget({ hard: 900_000 }))).toContain("900k");
  });
});

describe("applyContextBudgetPersona", () => {
  const cfg = resolveContextBudget();
  it("appends onto a preset systemPrompt object, preserving an existing append", () => {
    const opts: Record<string, unknown> = { systemPrompt: { type: "preset", preset: "claude_code", append: "EXISTING" } };
    applyContextBudgetPersona(opts, cfg);
    const sp = opts.systemPrompt as any;
    expect(sp.preset).toBe("claude_code");
    expect(sp.append).toContain("EXISTING");
    expect(sp.append).toContain("Context-budget policy");
  });
  it("creates a preset+append when systemPrompt is absent", () => {
    const opts: Record<string, unknown> = {};
    applyContextBudgetPersona(opts, cfg);
    expect(opts.systemPrompt).toEqual({ type: "preset", preset: "claude_code", append: contextBudgetSection(cfg) });
  });
});
