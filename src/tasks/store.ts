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
}
