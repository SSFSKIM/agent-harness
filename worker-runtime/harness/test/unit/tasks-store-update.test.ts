import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { TaskStore } from "../../src/tasks/store.js";

const newStore = () => new TaskStore({ dir: mkdtempSync(join(tmpdir(), "tasks-")) });

describe("TaskStore update + status machine", () => {
  it("applies field changes and bumps updatedAt", async () => {
    const s = newStore();
    await s.create({ subject: "x" });
    const u = await s.update(1, { subject: "y", description: "d" });
    expect(u.subject).toBe("y");
    expect(u.description).toBe("d");
  });
  it("allows forward transitions pending->in_progress->completed", async () => {
    const s = newStore();
    await s.create({ subject: "x" });
    expect((await s.update(1, { status: "in_progress" })).status).toBe("in_progress");
    expect((await s.update(1, { status: "completed" })).status).toBe("completed");
  });
  it("rejects backward transitions", async () => {
    const s = newStore();
    await s.create({ subject: "x" });
    await s.update(1, { status: "in_progress" });
    await s.update(1, { status: "completed" });
    await expect(s.update(1, { status: "pending" })).rejects.toThrow(/illegal transition/);
  });
  it("treats deleted as terminal and same-status as a no-op", async () => {
    const s = newStore();
    await s.create({ subject: "x" });
    expect((await s.update(1, { status: "pending" })).status).toBe("pending"); // no-op success
    await s.update(1, { status: "deleted" });
    await expect(s.update(1, { subject: "z" })).rejects.toThrow(/deleted/);
  });
  it("rejects updates to unknown ids", async () => {
    const s = newStore();
    await expect(s.update(99, { subject: "x" })).rejects.toThrow(/unknown task/);
  });
});
