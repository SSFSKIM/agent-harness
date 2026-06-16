import { MessageBus } from "./bus.js";
import { TeamRegistry } from "./team.js";
import type { Team } from "./team.js";
import { TeammateSession } from "./teammate.js";
import { TaskStore } from "../tasks/store.js";
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

  constructor(private deps: SwarmDeps, opts: SwarmOptions = {}) {
    this.tasks = new TaskStore({
      cwd: opts.cwd,
      dir: opts.taskOptions?.dir,
      listId: opts.taskOptions?.listId,
      agentName: opts.taskOptions?.agentName,
      onOwnerChange: (task, prev) => {
        this.bus.send("coordinator", {
          from: task.owner ?? "system",
          to: "coordinator",
          kind: "task",
          body: `task ${task.id} owner ${prev ?? "none"} -> ${task.owner ?? "none"}`,
          ts: new Date().toISOString(),
        });
      },
    });
  }

  createTeam(name: string, members?: string[]): Team { return this.teams.create(name, members); }

  deleteTeam(id: string): Team {
    const team = this.teams.delete(id); // throws on unknown id
    for (const name of team.members) {
      const s = this.sessions.get(name);
      if (s) { void s.dispose(); this.sessions.delete(name); }
      this.bus.unregister(name);
    }
    return team;
  }

  spawnTeammate(spec: TeammateSpec): TeammateSession {
    if (this.sessions.has(spec.name)) throw new SwarmError(`duplicate teammate ${spec.name}`);
    if (!this.teams.get(spec.teamId)) throw new SwarmError(`unknown team ${spec.teamId}`);
    this.teams.addMember(spec.teamId, spec.name); // also guards disbanded teams
    const options = spec.agent ? { model: spec.agent } : undefined; // per-teammate model (30.9)
    const session = new TeammateSession(spec, this.bus, { query: this.deps.query }, options); // subscribes itself
    this.sessions.set(spec.name, session);
    return session;
  }

  sendMessage(to: string, body: string, kind: MessageKind = "text"): Message {
    const msg: Message = { from: "coordinator", to, kind, body, ts: new Date().toISOString() };
    this.bus.send(to, msg); // teammate subscriber delivers into its query; coordinator buffers; unknown → throws
    return msg;
  }

  checkMessages(): Message[] { return this.bus.drain("coordinator"); }

  async disposeAll(): Promise<void> {
    await Promise.all([...this.sessions.values()].map((s) => s.dispose()));
    this.sessions.clear();
  }
}
