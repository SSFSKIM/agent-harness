import { describe, it, expect } from "vitest";
import { z } from "zod/v4";
import { taskCreateShape, taskUpdateShape, taskGetShape, taskListShape } from "../../src/tasks/types.js";

describe("task zod shapes", () => {
  it("TaskCreate requires subject and accepts optional deps/metadata", () => {
    const schema = z.object(taskCreateShape);
    expect(schema.parse({ subject: "x", blockedBy: [1], metadata: { a: 1 } }).subject).toBe("x");
    expect(() => schema.parse({})).toThrow();
  });
  it("TaskUpdate requires id, restricts status to the enum", () => {
    const schema = z.object(taskUpdateShape);
    expect(schema.parse({ id: 3, status: "in_progress" }).id).toBe(3);
    expect(() => schema.parse({ id: 1, status: "bogus" })).toThrow();
    expect(() => schema.parse({ status: "completed" })).toThrow(); // missing id
  });
  it("TaskGet/TaskList shapes parse", () => {
    expect(z.object(taskGetShape).parse({ id: 2 }).id).toBe(2);
    expect(z.object(taskListShape).parse({ status: "pending", owner: "main" }).owner).toBe("main");
    expect(z.object(taskListShape).parse({}).status).toBeUndefined();
  });
});
