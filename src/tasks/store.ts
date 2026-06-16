import { mkdirSync, readFileSync, writeFileSync, renameSync, existsSync } from "node:fs";
import { join } from "node:path";
import type { Task, TaskStatus, TaskStoreOptions, TaskCreateInput, TaskUpdatePatch, TaskListFilter } from "./types.js";

interface StoreFile { nextId: number; tasks: Task[]; }

export class TaskError extends Error {}

export interface TaskListItem {
  id: number; subject: string; status: TaskStatus; owner?: string; blockedBy: number[];
}

export class TaskStore {
  private file: string;
  private agentName: string;
  private onOwnerChange?: TaskStoreOptions["onOwnerChange"];
  private chain: Promise<unknown> = Promise.resolve(); // async mutex tail

  constructor(opts: TaskStoreOptions = {}) {
    const cwd = opts.cwd ?? process.cwd();
    const dir = opts.dir ?? join(cwd, ".cc-harness", "tasks");
    mkdirSync(dir, { recursive: true });
    this.file = join(dir, `${opts.listId ?? "default"}.json`);
    this.agentName = opts.agentName ?? "main";
    this.onOwnerChange = opts.onOwnerChange;
  }

  /** Serialize read-modify-write so concurrent callers cannot interleave. */
  private run<T>(fn: () => T): Promise<T> {
    const result = this.chain.then(() => fn());
    this.chain = result.catch(() => {}); // keep the mutex chain alive after a rejection
    return result;
  }

  private load(): StoreFile {
    if (!existsSync(this.file)) return { nextId: 1, tasks: [] };
    return JSON.parse(readFileSync(this.file, "utf8")) as StoreFile;
  }

  private save(data: StoreFile): void {
    const tmp = `${this.file}.tmp`;
    writeFileSync(tmp, JSON.stringify(data, null, 2));
    renameSync(tmp, this.file); // atomic replace
  }

  create(input: TaskCreateInput): Promise<Task> {
    return this.run(() => {
      const data = this.load();
      const blockedBy = input.blockedBy ?? [];
      for (const b of blockedBy) {
        if (!data.tasks.some((t) => t.id === b)) throw new TaskError(`unknown blocker id ${b}`);
      }
      const now = new Date().toISOString();
      const task: Task = {
        id: data.nextId,
        subject: input.subject,
        description: input.description,
        activeForm: input.activeForm,
        status: "pending",
        blocks: [],
        blockedBy: [...blockedBy],
        metadata: input.metadata,
        createdAt: now,
        updatedAt: now,
      };
      data.tasks.push(task);
      for (const b of blockedBy) {
        const bt = data.tasks.find((t) => t.id === b)!;
        if (!bt.blocks.includes(task.id)) bt.blocks.push(task.id);
      }
      data.nextId += 1;
      this.save(data);
      return task;
    });
  }

  get(id: number): Promise<Task | undefined> {
    return this.run(() => this.load().tasks.find((t) => t.id === id));
  }

  private static readonly LIVE_ORDER: TaskStatus[] = ["pending", "in_progress", "completed"];

  private canTransition(from: TaskStatus, to: TaskStatus): boolean {
    if (from === to) return true;
    if (from === "deleted") return false;
    if (to === "deleted") return true;
    return TaskStore.LIVE_ORDER.indexOf(to) > TaskStore.LIVE_ORDER.indexOf(from); // forward only
  }

  /** Replace task.blockedBy with `blockedBy`, keeping reverse `blocks` edges in sync and rejecting cycles. */
  private setBlockedBy(data: StoreFile, task: Task, blockedBy: number[]): void {
    for (const b of blockedBy) {
      if (!data.tasks.some((t) => t.id === b)) throw new TaskError(`unknown blocker id ${b}`);
    }
    // A cycle forms if any new blocker `b` already depends (transitively) on `task`.
    const reaches = (start: number, target: number): boolean => {
      const seen = new Set<number>();
      const stack = [start];
      while (stack.length) {
        const cur = stack.pop()!;
        if (cur === target) return true;
        if (seen.has(cur)) continue;
        seen.add(cur);
        const t = data.tasks.find((x) => x.id === cur);
        if (t) stack.push(...t.blockedBy);
      }
      return false;
    };
    for (const b of blockedBy) {
      if (b === task.id || reaches(b, task.id)) throw new TaskError(`dependency cycle via task ${b}`);
    }
    // Apply: drop task from old blockers no longer present, set new list, add reverse edges.
    for (const t of data.tasks) {
      const i = t.blocks.indexOf(task.id);
      if (i >= 0 && !blockedBy.includes(t.id)) t.blocks.splice(i, 1);
    }
    task.blockedBy = [...blockedBy];
    for (const b of blockedBy) {
      const bt = data.tasks.find((t) => t.id === b)!;
      if (!bt.blocks.includes(task.id)) bt.blocks.push(task.id);
    }
  }

  update(id: number, patch: TaskUpdatePatch): Promise<Task> {
    return this.run(() => {
      const data = this.load();
      const task = data.tasks.find((t) => t.id === id);
      if (!task) throw new TaskError(`unknown task id ${id}`);
      if (task.status === "deleted") throw new TaskError(`task ${id} is deleted`);
      const prevOwner = task.owner;

      // Ownership CAS: a different agent cannot claim or hold an owned task as in_progress
      // (fires even when the status is unchanged, so re-asserting in_progress is also gated).
      if (patch.status === "in_progress" && task.owner && task.owner !== this.agentName) {
        throw new TaskError(`already owned by ${task.owner}`);
      }

      if (patch.status !== undefined && patch.status !== task.status) {
        if (!this.canTransition(task.status, patch.status)) {
          throw new TaskError(`illegal transition ${task.status}->${patch.status}`);
        }
        if (patch.status === "in_progress") {
          const unresolved = task.blockedBy.filter((b) => {
            const bt = data.tasks.find((t) => t.id === b);
            return !bt || bt.status !== "completed";
          });
          if (unresolved.length) throw new TaskError(`blocked by unresolved tasks: ${unresolved.join(",")}`);
          task.owner = this.agentName; // claim
        }
        task.status = patch.status;
      }
      if (patch.subject !== undefined) task.subject = patch.subject;
      if (patch.description !== undefined) task.description = patch.description;
      if (patch.activeForm !== undefined) task.activeForm = patch.activeForm;
      if (patch.metadata !== undefined) task.metadata = patch.metadata;
      if (patch.owner !== undefined) task.owner = patch.owner; // explicit reassignment
      if (patch.blockedBy !== undefined) this.setBlockedBy(data, task, patch.blockedBy);

      task.updatedAt = new Date().toISOString();
      this.save(data);
      if (task.owner !== prevOwner) this.onOwnerChange?.(task, prevOwner);
      return task;
    });
  }

  list(filter: TaskListFilter = {}): Promise<TaskListItem[]> {
    return this.run(() => {
      const data = this.load();
      return data.tasks
        .filter((t) => t.status !== "deleted")
        .filter((t) => !filter.status || t.status === filter.status)
        .filter((t) => !filter.owner || t.owner === filter.owner)
        .map((t) => ({
          id: t.id,
          subject: t.subject,
          status: t.status,
          owner: t.owner,
          blockedBy: t.blockedBy.filter((b) => {
            const bt = data.tasks.find((x) => x.id === b);
            return !!bt && bt.status !== "completed";
          }),
        }));
    });
  }
}
