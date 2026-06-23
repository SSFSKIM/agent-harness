import { describe, it, expect } from "vitest";
import { listSessions, getSessionMessages, getSessionInfo } from "../../src/sessions/reader.js";

describe("sessions reader (cwd→dir glue)", () => {
  it("maps cwd to dir and passes through list options", async () => {
    const calls: any[] = [];
    const deps = { listSessions: async (o: any) => { calls.push(o); return [{ sessionId: "s1" }]; } };
    const r = await listSessions({ cwd: "/proj", limit: 5, offset: 2, includeWorktrees: false }, deps as any);
    expect(r).toEqual([{ sessionId: "s1" }]);
    expect(calls[0]).toEqual({ dir: "/proj", limit: 5, offset: 2, includeWorktrees: false });
    expect(calls[0]).not.toHaveProperty("cwd");
  });
  it("omits dir when no cwd is given", async () => {
    const calls: any[] = [];
    const deps = { listSessions: async (o: any) => { calls.push(o); return []; } };
    await listSessions({ limit: 1 }, deps as any);
    expect(calls[0]).toEqual({ limit: 1 });
    expect(calls[0]).not.toHaveProperty("dir");
  });
  it("getSessionMessages maps cwd→dir and passes id + options", async () => {
    const calls: any[] = [];
    const deps = { getSessionMessages: async (id: string, o: any) => { calls.push([id, o]); return [{ uuid: "u1" }]; } };
    const r = await getSessionMessages("sess-9", { cwd: "/p", includeSystemMessages: true }, deps as any);
    expect(r).toEqual([{ uuid: "u1" }]);
    expect(calls[0]).toEqual(["sess-9", { dir: "/p", includeSystemMessages: true }]);
  });
  it("getSessionInfo maps cwd→dir and passes id", async () => {
    const calls: any[] = [];
    const deps = { getSessionInfo: async (id: string, o: any) => { calls.push([id, o]); return { sessionId: id }; } };
    const r = await getSessionInfo("sess-9", { cwd: "/p" }, deps as any);
    expect(r).toEqual({ sessionId: "sess-9" });
    expect(calls[0]).toEqual(["sess-9", { dir: "/p" }]);
  });
});
