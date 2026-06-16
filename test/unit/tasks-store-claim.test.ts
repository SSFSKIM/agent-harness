import { describe, it, expect, vi } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { TaskStore } from "../../src/tasks/store.js";

const dir = () => mkdtempSync(join(tmpdir(), "tasks-"));

describe("TaskStore claim + ownership + list", () => {
  it("claims for the calling agent on in_progress", async () => {
    const s = new TaskStore({ dir: dir(), agentName: "alice" });
    await s.create({ subject: "x" });
    expect((await s.update(1, { status: "in_progress" })).owner).toBe("alice");
  });
  it("refuses to claim when a blocker is unresolved", async () => {
    const s = new TaskStore({ dir: dir(), agentName: "alice" });
    await s.create({ subject: "blocker" });           // 1
    await s.create({ subject: "work", blockedBy: [1] }); // 2
    await expect(s.update(2, { status: "in_progress" })).rejects.toThrow(/blocked by/);
    await s.update(1, { status: "in_progress" });
    await s.update(1, { status: "completed" });
    expect((await s.update(2, { status: "in_progress" })).owner).toBe("alice"); // now claimable
  });
  it("refuses to claim a task owned by a different agent", async () => {
    const d = dir();
    const alice = new TaskStore({ dir: d, agentName: "alice" });
    const bob = new TaskStore({ dir: d, agentName: "bob" });
    await alice.create({ subject: "x" });
    await alice.update(1, { status: "in_progress" }); // alice owns it
    await expect(bob.update(1, { status: "in_progress" })).rejects.toThrow(/already owned/);
  });
  it("explicit owner change is a reassignment and fires onOwnerChange", async () => {
    const cb = vi.fn();
    const s = new TaskStore({ dir: dir(), agentName: "alice", onOwnerChange: cb });
    await s.create({ subject: "x" });
    const u = await s.update(1, { owner: "carol" });
    expect(u.owner).toBe("carol");
    expect(cb).toHaveBeenCalledWith(expect.objectContaining({ id: 1, owner: "carol" }), undefined);
  });
  it("list excludes deleted, filters by status/owner, shows unresolved blockers only", async () => {
    const s = new TaskStore({ dir: dir(), agentName: "alice" });
    await s.create({ subject: "a" });               // 1
    await s.create({ subject: "b", blockedBy: [1] }); // 2
    await s.create({ subject: "gone" });            // 3
    await s.update(3, { status: "deleted" });
    let l = await s.list();
    expect(l.map((t) => t.id)).toEqual([1, 2]);     // no deleted
    expect(l.find((t) => t.id === 2)?.blockedBy).toEqual([1]); // unresolved blocker shown
    await s.update(1, { status: "in_progress" });
    await s.update(1, { status: "completed" });
    l = await s.list();
    expect(l.find((t) => t.id === 2)?.blockedBy).toEqual([]); // completed blocker filtered out
    expect((await s.list({ status: "completed" })).map((t) => t.id)).toEqual([1]);
  });
  it("serializes concurrent updates (consistent final nextId)", async () => {
    const s = new TaskStore({ dir: dir(), agentName: "alice" });
    await Promise.all([1, 2, 3, 4, 5].map((n) => s.create({ subject: `t${n}` })));
    expect((await s.list()).length).toBe(5);
    expect((await s.create({ subject: "next" })).id).toBe(6); // ids never collided
  });
});
