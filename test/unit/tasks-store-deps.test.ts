import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { TaskStore } from "../../src/tasks/store.js";

const newStore = () => new TaskStore({ dir: mkdtempSync(join(tmpdir(), "tasks-")) });

describe("TaskStore dependencies", () => {
  it("setting blockedBy syncs the reverse blocks side", async () => {
    const s = newStore();
    await s.create({ subject: "a" }); // 1
    await s.create({ subject: "b" }); // 2
    await s.update(2, { blockedBy: [1] });
    expect((await s.get(2))?.blockedBy).toEqual([1]);
    expect((await s.get(1))?.blocks).toEqual([2]);
  });
  it("clearing blockedBy removes the reverse edge", async () => {
    const s = newStore();
    await s.create({ subject: "a" }); // 1
    await s.create({ subject: "b", blockedBy: [1] }); // 2
    await s.update(2, { blockedBy: [] });
    expect((await s.get(1))?.blocks).toEqual([]);
  });
  it("rejects unknown blocker ids and self-dependency", async () => {
    const s = newStore();
    await s.create({ subject: "a" }); // 1
    await expect(s.update(1, { blockedBy: [99] })).rejects.toThrow(/unknown blocker/);
    await expect(s.update(1, { blockedBy: [1] })).rejects.toThrow(/cycle/);
  });
  it("rejects a dependency that would create a cycle", async () => {
    const s = newStore();
    await s.create({ subject: "a" }); // 1
    await s.create({ subject: "b", blockedBy: [1] }); // 2 depends on 1
    // making 1 depend on 2 closes a loop
    await expect(s.update(1, { blockedBy: [2] })).rejects.toThrow(/cycle/);
  });
});
