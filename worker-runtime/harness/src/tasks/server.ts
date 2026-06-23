import { createSdkMcpServer, tool } from "@anthropic-ai/claude-agent-sdk";
import type { TaskStore } from "./store.js";
import { taskCreateShape, taskUpdateShape, taskGetShape, taskListShape } from "./types.js";

const ok = (data: unknown) => ({ content: [{ type: "text" as const, text: JSON.stringify(data) }] });
const fail = (message: string) => ({ content: [{ type: "text" as const, text: message }], isError: true });

/** Build the four Task* SDK tool definitions over a TaskStore (exported for direct handler testing). */
export function buildTaskTools(store: TaskStore) {
  return [
    tool("TaskCreate", "Create a durable task (starts pending). Optionally blockedBy other task ids.", taskCreateShape, async (args) => {
      try { return ok(await store.create(args)); } catch (e) { return fail((e as Error).message); }
    }),
    tool("TaskUpdate", "Update a task's fields, status, owner, or dependencies by id.", taskUpdateShape, async (args) => {
      const { id, ...patch } = args;
      try { return ok(await store.update(id, patch)); } catch (e) { return fail((e as Error).message); }
    }),
    tool("TaskGet", "Get a single task by id.", taskGetShape, async (args) => {
      const t = await store.get(args.id);
      return t ? ok(t) : fail(`unknown task id ${args.id}`);
    }),
    tool("TaskList", "List non-deleted tasks (showing only unresolved blockers). Filter by status/owner.", taskListShape, async (args) => {
      return ok(await store.list(args));
    }),
  ];
}

/** Wrap a TaskStore as an in-process SDK MCP server exposing the four Task* tools. */
export function createTaskMcpServer(store: TaskStore) {
  return createSdkMcpServer({ name: "cc-tasks", version: "0.1.0", tools: buildTaskTools(store) });
}
