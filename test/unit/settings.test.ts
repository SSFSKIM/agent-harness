import { describe, it, expect } from "vitest";
import { resolveSettings } from "../../src/config/settings.js";

describe("resolveSettings", () => {
  it("defaults to all three setting sources (CC-faithful)", () => {
    const out = resolveSettings({});
    expect(out.settingSources).toEqual(["user", "project", "local"]);
  });
  it("disableProjectContext clears sources and excludes dynamic sections", () => {
    const out = resolveSettings({ disableProjectContext: true });
    expect(out.settingSources).toEqual([]);
    expect(out.systemPromptExcludeDynamic).toBe(true);
  });
  it("passes inline settings + managedSettings through", () => {
    const out = resolveSettings({ settings: { a: 1 }, managedSettings: { b: 2 } });
    expect(out.settings).toEqual({ a: 1 });
    expect(out.managedSettings).toEqual({ b: 2 });
  });
  it("honors explicit settingSources", () => {
    expect(resolveSettings({ settingSources: ["project"] }).settingSources).toEqual(["project"]);
  });
});
