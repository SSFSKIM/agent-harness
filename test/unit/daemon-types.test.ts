import { describe, it, expect } from "vitest";
import { daemonOp, DaemonError } from "../../src/daemon/types.js";

describe("daemon protocol", () => {
  it("parses each op and rejects unknown/invalid ops", () => {
    const spawn = daemonOp.parse({ op: "spawn", model: "claude-haiku-4-5-20251001" });
    expect(spawn.op).toBe("spawn");
    if (spawn.op === "spawn") expect(spawn.model).toBe("claude-haiku-4-5-20251001");
    const submit = daemonOp.parse({ op: "submit", id: "sess-1", prompt: "hi" });
    if (submit.op === "submit") expect(submit.prompt).toBe("hi");
    const stop = daemonOp.parse({ op: "stop", id: "sess-1" });
    if (stop.op === "stop") expect(stop.id).toBe("sess-1");
    expect(daemonOp.parse({ op: "list" }).op).toBe("list");
    expect(daemonOp.parse({ op: "shutdown" }).op).toBe("shutdown");
    expect(() => daemonOp.parse({ op: "bogus" })).toThrow();
    expect(() => daemonOp.parse({ op: "submit", id: "sess-1" })).toThrow(); // missing prompt
  });
  it("DaemonError is an Error subclass", () => {
    expect(new DaemonError("x")).toBeInstanceOf(Error);
  });
});
