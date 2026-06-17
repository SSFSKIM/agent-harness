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
  it("spawn op accepts a restart policy and rejects an invalid one", () => {
    const ok = daemonOp.parse({ op: "spawn", restart: "on-failure" });
    if (ok.op === "spawn") expect(ok.restart).toBe("on-failure");
    expect(daemonOp.parse({ op: "spawn" }).op).toBe("spawn"); // restart optional
    expect(() => daemonOp.parse({ op: "spawn", restart: "sometimes" })).toThrow();
  });
  it("spawn op accepts an optional resume session id", () => {
    const ok = daemonOp.parse({ op: "spawn", resume: "sess-9" });
    if (ok.op === "spawn") expect(ok.resume).toBe("sess-9");
    expect(daemonOp.parse({ op: "spawn" }).op).toBe("spawn"); // resume optional
  });
  it("sessions and messages ops parse with optional scope/pagination", () => {
    expect(daemonOp.parse({ op: "sessions" }).op).toBe("sessions");
    expect(daemonOp.parse({ op: "sessions", cwd: "/p", limit: 10, offset: 5 }).op).toBe("sessions");
    const m = daemonOp.parse({ op: "messages", id: "sess-1", cwd: "/p" });
    if (m.op === "messages") expect(m.id).toBe("sess-1");
    expect(() => daemonOp.parse({ op: "messages" })).toThrow(); // id required
  });
  it("parses a compact op", () => {
    expect(daemonOp.parse({ op: "compact", id: "sess-1" })).toEqual({ op: "compact", id: "sess-1" });
  });
});
