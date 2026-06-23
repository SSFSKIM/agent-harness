import { describe, it, expect } from "vitest";
import { renameSession, tagSession, deleteSession } from "../../src/sessions/mutate.js";

describe("session-store mutation wrappers (cwd→dir glue)", () => {
  it("renameSession maps cwd→dir and passes id + title through", async () => {
    const calls: any[] = [];
    const deps = { renameSession: async (id: string, title: string, o: any) => { calls.push([id, title, o]); } };
    await renameSession("s1", "New Title", { cwd: "/proj" }, deps as any);
    expect(calls[0]).toEqual(["s1", "New Title", { dir: "/proj" }]);
    expect(calls[0][2]).not.toHaveProperty("cwd");
  });
  it("tagSession passes a null tag through and omits dir without cwd", async () => {
    const calls: any[] = [];
    const deps = { tagSession: async (id: string, tag: string | null, o: any) => { calls.push([id, tag, o]); } };
    await tagSession("s1", null, {}, deps as any);
    expect(calls[0]).toEqual(["s1", null, {}]);
    expect(calls[0][2]).not.toHaveProperty("dir");
  });
  it("deleteSession maps cwd→dir and passes the id", async () => {
    const calls: any[] = [];
    const deps = { deleteSession: async (id: string, o: any) => { calls.push([id, o]); } };
    await deleteSession("s1", { cwd: "/proj" }, deps as any);
    expect(calls[0]).toEqual(["s1", { dir: "/proj" }]);
  });
});
