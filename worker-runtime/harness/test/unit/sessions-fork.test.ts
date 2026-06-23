import { describe, it, expect } from "vitest";
import { forkSession } from "../../src/sessions/fork.js";

describe("forkSession (cwd→dir glue)", () => {
  it("maps cwd→dir and passes id + fork options through", async () => {
    const calls: any[] = [];
    const deps = { forkSession: async (id: string, o: any) => { calls.push([id, o]); return { sessionId: "fork-1" }; } };
    const r = await forkSession("src-9", { cwd: "/proj", upToMessageId: "u5", title: "branch" }, deps as any);
    expect(r).toEqual({ sessionId: "fork-1" });
    expect(calls[0]).toEqual(["src-9", { dir: "/proj", upToMessageId: "u5", title: "branch" }]);
    expect(calls[0][1]).not.toHaveProperty("cwd");
  });
  it("omits dir when no cwd is given", async () => {
    const calls: any[] = [];
    const deps = { forkSession: async (id: string, o: any) => { calls.push([id, o]); return { sessionId: "fork-2" }; } };
    await forkSession("src-9", {}, deps as any);
    expect(calls[0]).toEqual(["src-9", {}]);
    expect(calls[0][1]).not.toHaveProperty("dir");
  });
});
