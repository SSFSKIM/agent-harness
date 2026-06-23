import { describe, it, expect } from "vitest";
import { AsyncQueue } from "../../src/swarm/asyncQueue.js";

describe("AsyncQueue", () => {
  it("delivers buffered values in order, then ends on close()", async () => {
    const q = new AsyncQueue<number>();
    q.push(1); q.push(2);
    const out: number[] = [];
    const consume = (async () => { for await (const v of q) out.push(v); })();
    q.push(3);
    q.close();
    await consume;
    expect(out).toEqual([1, 2, 3]);
  });
  it("resolves a waiting consumer when a value arrives later", async () => {
    const q = new AsyncQueue<string>();
    const it = q[Symbol.asyncIterator]();
    const pending = it.next();
    q.push("a");
    expect(await pending).toEqual({ value: "a", done: false });
  });
  it("reports pending buffered count and ignores push after close", () => {
    const q = new AsyncQueue<number>();
    q.push(1); q.push(2);
    expect(q.pending).toBe(2);
    q.close();
    q.push(3);
    expect(q.pending).toBe(2);
  });
});
