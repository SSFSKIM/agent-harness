import { SwarmError } from "./types.js";

export interface Team {
  id: string;
  name: string;
  members: string[];
  state: "active" | "disbanded";
}

export class TeamRegistry {
  private teams = new Map<string, Team>();
  private nextId = 1;

  create(name: string, members: string[] = []): Team {
    const id = `team-${this.nextId++}`;
    const team: Team = { id, name, members: [...members], state: "active" };
    this.teams.set(id, team);
    return team;
  }

  get(id: string): Team | undefined { return this.teams.get(id); }
  list(): Team[] { return [...this.teams.values()]; }

  addMember(id: string, name: string): void {
    const team = this.teams.get(id);
    if (!team) throw new SwarmError(`unknown team ${id}`);
    if (team.state !== "active") throw new SwarmError(`team ${id} is disbanded`);
    if (team.members.includes(name)) throw new SwarmError(`duplicate teammate ${name}`);
    team.members.push(name);
  }

  delete(id: string): Team {
    const team = this.teams.get(id);
    if (!team) throw new SwarmError(`unknown team ${id}`);
    team.state = "disbanded";
    return team;
  }
}
