import { describe, it, expect } from "vitest";
import { z } from "zod/v4";
import {
  SwarmError,
  teamCreateShape, teamDeleteShape, spawnTeammateShape, sendMessageShape, checkMessagesShape,
  respondPermissionShape, shutdownTeammateShape, approvePlanShape,
} from "../../src/swarm/types.js";

describe("swarm types", () => {
  it("SwarmError is an Error subclass", () => {
    expect(new SwarmError("x")).toBeInstanceOf(Error);
  });
  it("spawnTeammateShape requires teamId, name, prompt and accepts optional agent", () => {
    const ok = z.object(spawnTeammateShape).parse({ teamId: "team-1", name: "w1", prompt: "go", agent: "Plan" });
    expect(ok.name).toBe("w1");
    expect(() => z.object(spawnTeammateShape).parse({ name: "w1" })).toThrow();
  });
  it("sendMessageShape constrains kind to the message kinds", () => {
    expect(() => z.object(sendMessageShape).parse({ to: "w1", body: "hi", kind: "bogus" })).toThrow();
    expect(z.object(sendMessageShape).parse({ to: "w1", body: "hi" }).kind).toBeUndefined();
  });
  it("the simple shapes parse minimal input", () => {
    expect(z.object(teamCreateShape).parse({ name: "a" }).name).toBe("a");
    expect(z.object(teamDeleteShape).parse({ teamId: "team-1" }).teamId).toBe("team-1");
    expect(z.object(checkMessagesShape).parse({})).toEqual({});
  });
  it("respondPermissionShape requires requestId + a decision enum", () => {
    const ok = z.object(respondPermissionShape).parse({ requestId: "req-1", decision: "allow", message: "ok" });
    expect(ok.decision).toBe("allow");
    expect(() => z.object(respondPermissionShape).parse({ requestId: "req-1", decision: "maybe" })).toThrow();
  });
  it("shutdownTeammateShape requires a name", () => {
    expect(z.object(shutdownTeammateShape).parse({ name: "w1" }).name).toBe("w1");
    expect(() => z.object(shutdownTeammateShape).parse({})).toThrow();
  });
  it("spawnTeammateShape accepts an optional plan flag", () => {
    const ok = z.object(spawnTeammateShape).parse({ teamId: "team-1", name: "w1", prompt: "go", plan: true });
    expect(ok.plan).toBe(true);
    expect(z.object(spawnTeammateShape).parse({ teamId: "team-1", name: "w1", prompt: "go" }).plan).toBeUndefined();
    expect(() => z.object(spawnTeammateShape).parse({ teamId: "team-1", name: "w1", prompt: "go", plan: "yes" })).toThrow();
  });
  it("approvePlanShape requires requestId + an approve/reject decision", () => {
    const ok = z.object(approvePlanShape).parse({ requestId: "req-1", decision: "approve", feedback: "lgtm" });
    expect(ok.decision).toBe("approve");
    expect(() => z.object(approvePlanShape).parse({ requestId: "req-1", decision: "allow" })).toThrow();
  });
});
