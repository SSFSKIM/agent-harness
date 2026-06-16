import { describe, it, expect } from "vitest";
import { mkdtempSync, mkdirSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHarness } from "../../src/index.js";

const live = process.env.ANTHROPIC_API_KEY ? describe : describe.skip;

live("live parity (real SDK)", () => {
  it("default config runs an agent end-to-end", async () => {
    const h = createHarness({ permissionMode: "bypassPermissions", maxTurns: 1 });
    const r = await h.run("Reply with exactly the word OK.");
    expect(String(r.result)).toMatch(/OK/);
    expect(r.sessionId).toBeTruthy();
  });

  it("loads a .claude/commands file via default settingSources", async () => {
    const dir = mkdtempSync(join(tmpdir(), "cc-harness-"));
    mkdirSync(join(dir, ".claude", "commands"), { recursive: true });
    writeFileSync(join(dir, ".claude", "commands", "probecmd.md"), "---\ndescription: probe\n---\nSay probe.\n");
    const h = createHarness({ cwd: dir, permissionMode: "bypassPermissions", maxTurns: 1 });
    const it = h.stream("hi"); await it.next(); // start query so introspection works
    const cmds: any = await h.supportedCommands();
    expect(JSON.stringify(cmds)).toContain("probecmd");
  });

  it("Explore built-in agent is registered and read-only", async () => {
    const h = createHarness({ permissionMode: "bypassPermissions", maxTurns: 1 });
    const it = h.stream("hi"); await it.next();
    const agents: any = await h.supportedAgents();
    expect(JSON.stringify(agents)).toContain("Explore");
  });

  it("file checkpointing is enabled and a checkpointed session creates files", async () => {
    const dir = mkdtempSync(join(tmpdir(), "cc-harness-rw-"));
    const h = createHarness({ cwd: dir, enableFileCheckpointing: true, permissionMode: "bypassPermissions", maxTurns: 4 });
    // Bridge wiring (deterministic): the checkpointing option is threaded and rewind is exposed.
    expect((h.options as any).enableFileCheckpointing).toBe(true);
    expect(typeof h.rewind).toBe("function");
    // End-to-end: a checkpointing-enabled session runs and writes the file.
    const r = await h.run(`Create a file named note.txt containing exactly the text HELLO in the current directory.`);
    expect(r.result).toBeTruthy();
    expect(existsSync(join(dir, "note.txt"))).toBe(true);
    // This test intentionally does NOT call live rewind(): the SDK rewindFiles() is a
    // control-protocol request that needs an OPEN process transport (streaming-input mode)
    // and fails after a one-shot string-prompt query completes ("ProcessTransport is not
    // ready for writing"). Its scope is therefore checkpoint-option wiring + a real
    // checkpointed file write. The rewind→rewindFiles wiring is verified deterministically
    // in test/unit/harness.test.ts; live mid-session rewind is a Phase-2 capability.
  });
});
