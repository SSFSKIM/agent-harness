import { MessageBus } from "./bus.js";
import { TeamRegistry } from "./team.js";
import type { Team } from "./team.js";
import { TeammateSession } from "./teammate.js";
import { NATIVE_TASK_TOOLS } from "./coordinator.js";
import { PermissionBroker } from "./permissions.js";
import { TaskStore } from "../tasks/store.js";
import { createTaskMcpServer } from "../tasks/server.js";
import type { Task } from "../tasks/types.js";
import { SwarmError } from "./types.js";
import type { Message, MessageKind, QueryFn, SwarmOptions, TeammateSpec } from "./types.js";

export interface SwarmDeps { query: QueryFn; }

export class SwarmRuntime {
  readonly bus = new MessageBus();
  readonly teams = new TeamRegistry();
  readonly tasks: TaskStore;
  /** A2b seams (no-op by default). */
  onPermissionRequest?: (teammate: string, request: unknown) => void;
  onHandshake?: (kind: string, payload: unknown) => void;
  private sessions = new Map<string, TeammateSession>();
  private broker: PermissionBroker;
  private taskCwd?: string;
  private taskDir?: string;
  private taskListId?: string;

  constructor(private deps: SwarmDeps, opts: SwarmOptions = {}) {
    this.taskCwd = opts.cwd;
    this.taskDir = opts.taskOptions?.dir;
    this.taskListId = opts.taskOptions?.listId;
    this.tasks = new TaskStore({
      cwd: this.taskCwd,
      dir: this.taskDir,
      listId: this.taskListId,
      agentName: opts.taskOptions?.agentName,
      onOwnerChange: this.notifyOwner,
    });
    this.broker = new PermissionBroker({
      allow: opts.permissions?.allow,
      escalate: opts.permissions?.escalateToCoordinator,
      onRequest: (teammate, req) => this.onPermissionRequest?.(teammate, req),
      onEscalate: (teammate, tool, input, requestId) => {
        this.bus.send("coordinator", {
          from: teammate, to: "coordinator", kind: "permission",
          body: `${teammate} requests ${tool}`,
          data: { requestId, teammate, tool, input },
          ts: new Date().toISOString(),
        });
      },
    });
  }

  /** Push a task-ownership change onto the coordinator inbox (closes A1's deferred 15.10). */
  private notifyOwner = (task: Task, prev: string | undefined): void => {
    this.bus.send("coordinator", {
      from: task.owner ?? "system",
      to: "coordinator",
      kind: "task",
      body: `task ${task.id} owner ${prev ?? "none"} -> ${task.owner ?? "none"}`,
      ts: new Date().toISOString(),
    });
  };

  createTeam(name: string, members?: string[]): Team { return this.teams.create(name, members); }

  async deleteTeam(id: string): Promise<Team> {
    const team = this.teams.delete(id); // throws on unknown id
    await Promise.all(
      team.members.map(async (name) => {
        const s = this.sessions.get(name);
        if (s) { await s.dispose(); this.sessions.delete(name); }
        this.bus.unregister(name);
      }),
    );
    return team;
  }

  spawnTeammate(spec: TeammateSpec): TeammateSession {
    if (this.sessions.has(spec.name)) throw new SwarmError(`duplicate teammate ${spec.name}`);
    if (!this.teams.get(spec.teamId)) throw new SwarmError(`unknown team ${spec.teamId}`);

    // Each teammate gets the shared task list (same file/list) under its OWN agentName,
    // so it can claim work via the A1 CAS primitive; its claims also notify the coordinator.
    const teammateStore = new TaskStore({
      cwd: this.taskCwd, dir: this.taskDir, listId: this.taskListId,
      agentName: spec.name, onOwnerChange: this.notifyOwner,
    });
    const options: Record<string, unknown> = {
      mcpServers: { "cc-tasks": createTaskMcpServer(teammateStore) },
      disallowedTools: [...NATIVE_TASK_TOOLS], // shared cc-tasks store is authoritative, not native per-session tasks
      canUseTool: (tool: string, input: Record<string, unknown>) => this.broker.decide(spec.name, tool, input),
    };
    if (spec.agent) options.model = spec.agent; // per-teammate model (30.9)

    // Construct first (side-effect-free); only commit registry/bus state if it succeeds.
    const session = new TeammateSession(spec, this.bus, { query: this.deps.query }, options);
    try {
      this.teams.addMember(spec.teamId, spec.name); // throws on duplicate roster / disbanded
    } catch (e) {
      void session.dispose(); // roll back the started query
      throw e;
    }
    this.bus.subscribe(spec.name, (msg) => session.send(msg.body)); // inbound bus message → new turn
    this.sessions.set(spec.name, session);
    return session;
  }

  sendMessage(to: string, body: string, kind: MessageKind = "text"): Message {
    const msg: Message = { from: "coordinator", to, kind, body, ts: new Date().toISOString() };
    this.bus.send(to, msg); // teammate subscriber delivers into its query; coordinator buffers; unknown → throws
    return msg;
  }

  checkMessages(): Message[] { return this.bus.drain("coordinator"); }

  respondPermission(requestId: string, decision: "allow" | "deny", message?: string): boolean {
    return this.broker.respond(requestId, decision, message);
  }

  async requestShutdown(name: string): Promise<void> {
    const s = this.sessions.get(name);
    if (!s) throw new SwarmError(`unknown teammate ${name}`);
    this.onHandshake?.("shutdown", { name });
    await s.shutdown();
    this.sessions.delete(name);
    this.bus.unregister(name);
  }

  async disposeAll(): Promise<void> {
    await Promise.all(
      [...this.sessions].map(async ([name, s]) => { await s.dispose(); this.bus.unregister(name); }),
    );
    this.sessions.clear();
  }
}
