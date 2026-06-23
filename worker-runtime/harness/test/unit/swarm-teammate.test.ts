import { describe, it, expect } from "vitest";
import { MessageBus } from "../../src/swarm/bus.js";
import { TeammateSession } from "../../src/swarm/teammate.js";

// Fake query: consumes each pushed user turn and yields an assistant + result per turn.
function fakeQuery({ prompt }: any) {
  return (async function* () {
    for await (const turn of prompt) {
      const text = turn.message.content;
      yield { type: "assistant", message: { content: [{ type: "text", text: "ack:" + text }] } };
      yield { type: "result", subtype: "success", result: "did:" + text };
    }
  })();
}

describe("TeammateSession", () => {
  it("seeds the prompt and emits result + idle to the coordinator", async () => {
    const bus = new MessageBus();
    const s = new TeammateSession({ name: "w1", teamId: "team-1", prompt: "do x" }, bus, { query: fakeQuery });
    await s.settled();
    const msgs = bus.drain("coordinator");
    expect(msgs.map((m) => [m.kind, m.body])).toEqual([["result", "did:do x"], ["idle", ""]]);
    expect(msgs[0].from).toBe("w1");
    await s.dispose();
  });
  it("delivers a sent message as a new turn", async () => {
    const bus = new MessageBus();
    const s = new TeammateSession({ name: "w1", teamId: "team-1", prompt: "seed" }, bus, { query: fakeQuery });
    await s.settled();
    bus.drain("coordinator");
    const next = s.settled();
    s.send("more");
    await next;
    expect(bus.drain("coordinator").map((m) => [m.kind, m.body])).toEqual([["result", "did:more"], ["idle", ""]]);
    await s.dispose();
  });
  it("dispose() ends the underlying query", async () => {
    const bus = new MessageBus();
    let ended = false;
    const fq = ({ prompt }: any) => (async function* () {
      try { for await (const t of prompt) { void t; yield { type: "result", result: "r" }; } }
      finally { ended = true; }
    })();
    const s = new TeammateSession({ name: "w1", teamId: "team-1", prompt: "x" }, bus, { query: fq });
    await s.settled();
    await s.dispose();
    expect(ended).toBe(true);
  });
  it("forwards constructor options to the query (e.g. per-teammate model)", () => {
    const bus = new MessageBus();
    let seen: any;
    const fq = ({ prompt, options }: any) => {
      seen = options;
      return (async function* () { for await (const t of prompt) { void t; yield { type: "result", result: "r" }; } })();
    };
    new TeammateSession({ name: "w1", teamId: "t1", prompt: "x" }, bus, { query: fq }, { model: "claude-haiku-4-5-20251001" });
    expect(seen).toEqual({ model: "claude-haiku-4-5-20251001" });
  });
  it("maps a worker_shutting_down system message to a shutdown envelope", async () => {
    const bus = new MessageBus();
    const fq = ({ prompt }: any) => (async function* () {
      for await (const t of prompt) { void t; yield { type: "system", subtype: "worker_shutting_down", reason: "host_exit" }; yield { type: "result", result: "x" }; }
    })();
    const s = new TeammateSession({ name: "w1", teamId: "t1", prompt: "go" }, bus, { query: fq });
    await s.settled();
    expect(bus.drain("coordinator").map((m) => m.kind)).toContain("shutdown");
    await s.dispose();
  });
  it("setMode calls the query's setPermissionMode when present, and no-ops when absent", async () => {
    const bus = new MessageBus();
    const calls: string[] = [];
    const fqWithMode = ({ prompt }: any) => {
      const gen: any = (async function* () { for await (const t of prompt) { void t; yield { type: "result", result: "r" }; } })();
      gen.setPermissionMode = async (m: string) => { calls.push(m); };
      return gen;
    };
    const s = new TeammateSession({ name: "w1", teamId: "t1", prompt: "x" }, bus, { query: fqWithMode });
    await s.setMode("acceptEdits");
    expect(calls).toEqual(["acceptEdits"]);
    await s.dispose();

    // fake query without setPermissionMode → setMode resolves without throwing
    const plain = new TeammateSession({ name: "w2", teamId: "t1", prompt: "x" }, bus, { query: fakeQuery });
    await expect(plain.setMode("default")).resolves.toBeUndefined();
    await plain.dispose();
  });
  it("shutdown() emits a shutdown ack and ends the query", async () => {
    const bus = new MessageBus();
    let ended = false;
    const fq = ({ prompt }: any) => (async function* () {
      try { for await (const t of prompt) { void t; yield { type: "result", result: "r" }; } } finally { ended = true; }
    })();
    const s = new TeammateSession({ name: "w1", teamId: "t1", prompt: "go" }, bus, { query: fq });
    await s.settled();
    bus.drain("coordinator");
    await s.shutdown();
    expect(bus.drain("coordinator").some((m) => m.kind === "shutdown")).toBe(true);
    expect(ended).toBe(true);
  });
});
