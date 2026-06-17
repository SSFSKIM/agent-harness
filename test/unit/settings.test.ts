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
  it("folds autoCompactEnabled/autoCompactWindow into settings", () => {
    const s = resolveSettings({ autoCompactEnabled: false, autoCompactWindow: 20000 });
    expect(s.settings).toEqual({ autoCompactEnabled: false, autoCompactWindow: 20000 });
  });
  it("composes the autocompact fields with an explicit settings object", () => {
    const s = resolveSettings({ settings: { foo: 1 }, autoCompactEnabled: true });
    expect(s.settings).toEqual({ foo: 1, autoCompactEnabled: true });
  });
  it("leaves settings undefined when neither settings nor autocompact fields are set", () => {
    expect(resolveSettings({}).settings).toBeUndefined();
  });
});
