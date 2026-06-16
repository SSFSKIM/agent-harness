import { describe, it, expect } from "vitest";
import { TeamRegistry } from "../../src/swarm/team.js";

describe("TeamRegistry", () => {
  it("creates a team with an auto id, roster, and active state", () => {
    const r = new TeamRegistry();
    const t = r.create("alpha", ["w1"]);
    expect(t.id).toBe("team-1");
    expect(t.members).toEqual(["w1"]);
    expect(t.state).toBe("active");
    expect(r.create("beta").id).toBe("team-2");
  });
  it("addMember rejects duplicates within a team and disbanded teams", () => {
    const r = new TeamRegistry();
    const t = r.create("alpha");
    r.addMember(t.id, "w1");
    expect(() => r.addMember(t.id, "w1")).toThrow(/duplicate/);
    r.delete(t.id);
    expect(() => r.addMember(t.id, "w2")).toThrow(/disbanded/);
  });
  it("delete marks disbanded and returns the roster; unknown id throws", () => {
    const r = new TeamRegistry();
    const t = r.create("alpha", ["w1"]);
    expect(r.delete(t.id).state).toBe("disbanded");
    expect(() => r.delete("team-99")).toThrow(/unknown team/);
  });
});
