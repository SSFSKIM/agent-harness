import { describe, it, expect } from "vitest";
import { KairosAssistant } from "../../src/kairos/assistant.js";

/** Fake query: capture the FIRST spawned session's options; consume its input queue so dispose() ends. */
function fakeQueryCapturing() {
  const captured: { options?: any } = {};
  const query = ((arg: any) => {
    if (!captured.options) captured.options = arg.options;
    return (async function* () { for await (const _ of arg.prompt) { /* swallow turns; emit no result */ } })();
  }) as any;
  return { query, captured };
}

describe("KairosAssistant orchestration", () => {
  it("spawns a session in assistant posture (auto + cc-brief + persona + allowlist)", async () => {
    const { query, captured } = fakeQueryCapturing();
    const k = new KairosAssistant({ query }, { cwd: "/tmp/kairos-x", proactive: { intervalMs: 999_999 } });
    await k.start();
    const o = captured.options;
    expect(o.permissionMode).toBe("auto");
    expect(o.cwd).toBe("/tmp/kairos-x");
    expect(o.mcpServers["cc-brief"]).toBeTruthy();
    expect(o.allowedTools).toContain("mcp__cc-brief__SendUserMessage");
    expect(JSON.stringify(o.systemPrompt)).toMatch(/SendUserMessage/);
    expect(JSON.stringify(o.systemPrompt)).toMatch(/IDLE/);
    await k.stop();
  });

  it("reports a running heartbeat after start; stop() is idempotent", async () => {
    const { query } = fakeQueryCapturing();
    const k = new KairosAssistant({ query }, { proactive: { intervalMs: 999_999 } });
    await k.start();
    expect(k.status().proactive?.state).toBe("running");
    await k.stop();
    await k.stop(); // idempotent — must not throw
    expect(k.status().sessionId).toBeTruthy();
  });

  it("rejects a second start()", async () => {
    const { query } = fakeQueryCapturing();
    const k = new KairosAssistant({ query }, { proactive: { intervalMs: 999_999 } });
    await k.start();
    await expect(k.start()).rejects.toThrow(/already started/);
    await k.stop();
  });

  it("stop() before start() is a no-op and does not suppress a later teardown", async () => {
    let disposed = false;
    const query = ((arg: any) => (async function* () { for await (const _ of arg.prompt) { /* swallow */ } disposed = true; })()) as any;
    const k = new KairosAssistant({ query }, { proactive: { intervalMs: 999_999 } });
    await k.stop();                                  // before start: clean no-op, must not latch
    await k.start();
    expect(k.status().proactive?.state).toBe("running");
    await k.stop();                                  // must actually tear the session down now
    expect(disposed).toBe(true);                     // session was disposed (no leak)
  });
});
