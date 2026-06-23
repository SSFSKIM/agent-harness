import { describe, it, expect } from "vitest";
import { Session } from "../../src/session/session.js";

// a well-behaved fake query: one result per turn, ends when the input (prompt) closes
const healthy = ({ prompt }: any) => (async function* () { for await (const t of prompt) yield { type: "result", result: "did:" + t.message.content }; })();
// a fake that accepts a turn but never yields a result (turn stays in-flight) until input closes
const stalled = ({ prompt }: any) => (async function* () { for await (const _t of prompt) { /* never yields a result */ } })();

describe("Session teardown liveness", () => {
  it("no-hang: dispose() resolves even with a healthy query", async () => {
    const s = new Session({ query: healthy }, {});
    await s.submit("hi");
    await expect(s.dispose()).resolves.toBeUndefined();   // completes, no hang
    expect(s.isEnded()).toBe(true);
  });
  it("no-fake-settle: a turn pending at dispose REJECTS (not a bogus resolve)", async () => {
    const s = new Session({ query: stalled }, {});
    const pending = s.submit("hi");                        // never gets a result frame
    await s.dispose();                                      // closes input → readLoop ends → waiters reject
    await expect(pending).rejects.toThrow();               // rejected, not fake-resolved
  });
  it("idempotent: a second dispose() is a safe no-op", async () => {
    const s = new Session({ query: healthy }, {});
    await s.dispose();
    await expect(s.dispose()).resolves.toBeUndefined();    // double dispose must not throw
  });
  it("post-dispose submit rejects rather than hanging", async () => {
    const s = new Session({ query: healthy }, {});
    await s.dispose();
    await expect(s.submit("x")).rejects.toThrow(/not running/);
  });
});
