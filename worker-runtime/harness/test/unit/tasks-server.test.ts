import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { TaskStore } from "../../src/tasks/store.js";
import { buildTaskTools, createTaskMcpServer } from "../../src/tasks/server.js";

function tools(store: TaskStore) {
  const map: Record<string, any> = {};
  for (const t of buildTaskTools(store)) map[t.name] = t;
  return map;
}
const text = (r: any) => r.content[0].text;
const newStore = () => new TaskStore({ dir: mkdtempSync(join(tmpdir(), "tasks-")) });

describe("task MCP server", () => {
  it("exposes the four Task tools", () => {
    const t = tools(newStore());
    expect(Object.keys(t).sort()).toEqual(["TaskCreate", "TaskGet", "TaskList", "TaskUpdate"]);
  });
  it("createTaskMcpServer returns an sdk server config named cc-tasks", () => {
    const srv: any = createTaskMcpServer(newStore());
    expect(srv.type).toBe("sdk");
    expect(srv.name).toBe("cc-tasks");
  });
  it("TaskCreate then TaskGet round-trips through the store", async () => {
    const t = tools(newStore());
    const created = await t.TaskCreate.handler({ subject: "hello" }, {});
    expect(JSON.parse(text(created)).id).toBe(1);
    const got = await t.TaskGet.handler({ id: 1 }, {});
    expect(JSON.parse(text(got)).subject).toBe("hello");
  });
  it("domain errors come back as isError results, not throws", async () => {
    const t = tools(newStore());
    const bad = await t.TaskUpdate.handler({ id: 99, subject: "x" }, {});
    expect(bad.isError).toBe(true);
    expect(text(bad)).toMatch(/unknown task/);
    const missing = await t.TaskGet.handler({ id: 5 }, {});
    expect(missing.isError).toBe(true);
  });
});
