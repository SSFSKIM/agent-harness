import { z } from "zod/v4";

export type TaskStatus = "pending" | "in_progress" | "completed" | "deleted";

export interface Task {
  id: number;
  subject: string;
  description?: string;
  activeForm?: string;      // present-continuous label shown while in_progress (CC convention)
  status: TaskStatus;
  owner?: string;           // agent name; set on claim
  blocks: number[];         // ids this task blocks
  blockedBy: number[];      // ids blocking this task
  metadata?: Record<string, unknown>;
  createdAt: string;        // ISO
  updatedAt: string;        // ISO
}

export interface TaskStoreOptions {
  cwd?: string;
  dir?: string;             // override directory; default <cwd>/.cc-harness/tasks
  listId?: string;          // default "default"
  agentName?: string;       // default "main"
  onOwnerChange?: (task: Task, prevOwner: string | undefined) => void;
}

const STATUS = z.enum(["pending", "in_progress", "completed", "deleted"]);

// zod raw shapes (ZodRawShape = plain object of validators) for the four tools.
export const taskCreateShape = {
  subject: z.string(),
  description: z.string().optional(),
  activeForm: z.string().optional(),
  blockedBy: z.array(z.number()).optional(),
  metadata: z.record(z.string(), z.unknown()).optional(),
};
export const taskUpdateShape = {
  id: z.number(),
  subject: z.string().optional(),
  description: z.string().optional(),
  activeForm: z.string().optional(),
  status: STATUS.optional(),
  owner: z.string().optional(),
  blockedBy: z.array(z.number()).optional(),
  metadata: z.record(z.string(), z.unknown()).optional(),
};
export const taskGetShape = { id: z.number() };
export const taskListShape = {
  status: STATUS.optional(),
  owner: z.string().optional(),
};

// Input value types derived from the shapes (used by TaskStore + server).
export type TaskCreateInput = z.infer<z.ZodObject<typeof taskCreateShape>>;
export type TaskUpdateInput = z.infer<z.ZodObject<typeof taskUpdateShape>>;
export type TaskUpdatePatch = Omit<TaskUpdateInput, "id">;
export type TaskListFilter = z.infer<z.ZodObject<typeof taskListShape>>;
