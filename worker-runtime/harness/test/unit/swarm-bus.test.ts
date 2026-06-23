import { describe, it, expect } from "vitest";
import { MessageBus } from "../../src/swarm/bus.js";
import type { Message } from "../../src/swarm/types.js";

const msg = (to: string, body: string): Message => ({ from: "x", to, kind: "text", body, ts: "t" });

describe("MessageBus", () => {
  it("buffers for the coordinator and drain() returns then clears", () => {
    const bus = new MessageBus();
    bus.send("coordinator", msg("coordinator", "hi"));
    expect(bus.drain("coordinator").map((m) => m.body)).toEqual(["hi"]);
    expect(bus.drain("coordinator")).toEqual([]);
  });
  it("throws on an unknown recipient", () => {
    const bus = new MessageBus();
    expect(() => bus.send("ghost", msg("ghost", "x"))).toThrow(/unknown recipient/);
  });
  it("delivers to a subscriber instead of buffering", () => {
    const bus = new MessageBus();
    const got: string[] = [];
    bus.subscribe("w1", (m) => got.push(m.body));
    bus.send("w1", msg("w1", "yo"));
    expect(got).toEqual(["yo"]);
    expect(bus.drain("w1")).toEqual([]);
  });
  it("unregister removes the recipient so sends error again", () => {
    const bus = new MessageBus();
    bus.subscribe("w1", () => {});
    bus.unregister("w1");
    expect(() => bus.send("w1", msg("w1", "x"))).toThrow(/unknown recipient/);
  });
});
