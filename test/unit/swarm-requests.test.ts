import { describe, it, expect } from "vitest";
import { RequestRegistry } from "../../src/swarm/requests.js";

describe("RequestRegistry", () => {
  it("create() returns an id + a promise that resolve() settles", async () => {
    const r = new RequestRegistry<{ decision: string }>();
    const { id, promise } = r.create();
    expect(typeof id).toBe("string");
    expect(r.resolve(id, { decision: "allow" })).toBe(true);
    expect(await promise).toEqual({ decision: "allow" });
  });
  it("resolve() on an unknown id returns false", () => {
    expect(new RequestRegistry().resolve("nope", {})).toBe(false);
  });
  it("resolve() twice on the same id returns false the second time", () => {
    const r = new RequestRegistry();
    const { id } = r.create();
    expect(r.resolve(id, {})).toBe(true);
    expect(r.resolve(id, {})).toBe(false);
  });
  it("ids are unique", () => {
    const r = new RequestRegistry();
    expect(r.create().id).not.toBe(r.create().id);
  });
});
