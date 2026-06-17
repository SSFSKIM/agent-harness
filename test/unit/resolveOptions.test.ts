import { describe, it, expect } from "vitest";
import { resolveOptions } from "../../src/config/resolveOptions.js";

describe("resolveOptions", () => {
  it("produces CC-faithful defaults", () => {
    const o: any = resolveOptions({});
    expect(o.settingSources).toEqual(["user", "project", "local"]);
    expect(o.systemPrompt).toEqual({ type: "preset", preset: "claude_code" });
    expect(o.tools).toEqual({ type: "preset", preset: "claude_code" });
    expect(o.enableFileCheckpointing).toBe(true);
    expect(o.agents["Explore"].disallowedTools).toContain("Write");
  });
  it("wires outputStyle into systemPrompt.append and never leaks it into Options", () => {
    const o: any = resolveOptions({ outputStyle: "explanatory" });
    expect(o.systemPrompt.append).toContain("educational");
    expect(o).not.toHaveProperty("outputStyle"); // phantom option must not reach the SDK
  });
  it("sets allowDangerouslySkipPermissions when bypassPermissions is used", () => {
    const o: any = resolveOptions({ permissionMode: "bypassPermissions" });
    expect(o.permissionMode).toBe("bypassPermissions");
    expect(o.allowDangerouslySkipPermissions).toBe(true);
  });
  it("does not set allowDangerouslySkipPermissions for other permission modes", () => {
    const o: any = resolveOptions({ permissionMode: "default" });
    expect(o).not.toHaveProperty("allowDangerouslySkipPermissions");
  });
  it("threads provider env, sandbox, model, mcp, plugins, cwd, maxTurns", () => {
    const o: any = resolveOptions({
      provider: "bedrock", sandbox: true, model: "claude-opus-4-8",
      mcpServers: { x: { type: "stdio", command: "echo" } }, cwd: "/tmp", maxTurns: 5,
    });
    expect(o.env.CLAUDE_CODE_USE_BEDROCK).toBe("1");
    expect(o.sandbox).toEqual({ enabled: true });
    expect(o.model).toBe("claude-opus-4-8");
    expect(o.mcpServers).toBeTruthy();
    expect(o.cwd).toBe("/tmp");
    expect(o.maxTurns).toBe(5);
  });
  it("disableProjectContext clears sources and excludes dynamic sections", () => {
    const o: any = resolveOptions({ disableProjectContext: true });
    expect(o.settingSources).toEqual([]);
    expect(o.systemPrompt.excludeDynamicSections).toBe(true);
  });
  it("merges env over process.env so PATH/HOME/auth are not erased", () => {
    // SDK `env` replaces the whole subprocess environment; resolveOptions must
    // spread process.env so a single provider flag does not wipe inherited vars.
    const o: any = resolveOptions({ provider: "bedrock" });
    expect(o.env.CLAUDE_CODE_USE_BEDROCK).toBe("1");
    expect(o.env.PATH).toBe(process.env.PATH);
  });
  it("does not set env (inherits process.env) when there are no overrides", () => {
    const o: any = resolveOptions({});
    expect(o.env).toBeUndefined();
  });
  it("threads resume and sessionStore when set, omits them otherwise", () => {
    const store = { append: async () => {}, load: async () => null } as any;
    const o: any = resolveOptions({ resume: "sess-abc", sessionStore: store });
    expect(o.resume).toBe("sess-abc");
    expect(o.sessionStore).toBe(store);
    const bare: any = resolveOptions({});
    expect(bare).not.toHaveProperty("resume");
    expect(bare).not.toHaveProperty("sessionStore");
  });
  it("emits persistSession for true and false, omits when undefined", () => {
    expect((resolveOptions({ persistSession: false }) as any).persistSession).toBe(false);
    expect((resolveOptions({ persistSession: true }) as any).persistSession).toBe(true);
    expect(resolveOptions({})).not.toHaveProperty("persistSession");
  });
  it("passes config.hooks through to options.hooks, omits when absent", () => {
    const hooks = { PostToolUse: [{ hooks: [async () => ({})] }] };
    const o: any = resolveOptions({ hooks });
    expect(o.hooks).toBe(hooks);
    expect(resolveOptions({})).not.toHaveProperty("hooks");
  });
});
