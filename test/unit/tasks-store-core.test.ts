import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { TaskStore } from "../../src/tasks/store.js";

const newStore = () => new TaskStore({ dir: mkdtempSync(join(tmpdir(), "tasks-")) });

describe("TaskStore core", () => {
  it("create returns an auto-incrementing pending task", async () => {
    const s = newStore();
    const a = await s.create({ subject: "first" });
    const b = await s.create({ subject: "second" });
    expect(a.id).toBe(1);
    expect(a.status).toBe("pending");
    expect(a.blocks).toEqual([]);
    expect(a.blockedBy).toEqual([]);
    expect(b.id).toBe(2);
  });
  it("get returns a task by id, undefined for unknown", async () => {
    const s = newStore();
    const a = await s.create({ subject: "x", description: "d", metadata: { k: 1 } });
    expect((await s.get(1))?.subject).toBe("x");
    expect((await s.get(1))?.description).toBe("d");
    expect(await s.get(99)).toBeUndefined();
  });
  it("create rejects unknown blocker ids", async () => {
    const s = newStore();
    await expect(s.create({ subject: "x", blockedBy: [42] })).rejects.toThrow(/unknown blocker/);
  });
  it("persists atomically: a fresh store on the same dir sees prior tasks", async () => {
    const dir = mkdtempSync(join(tmpdir(), "tasks-"));
    const s1 = new TaskStore({ dir });
    await s1.create({ subject: "persisted" });
    const s2 = new TaskStore({ dir });
    expect((await s2.get(1))?.subject).toBe("persisted");
    expect((await s2.create({ subject: "next" })).id).toBe(2); // nextId survived reload
  });
});
