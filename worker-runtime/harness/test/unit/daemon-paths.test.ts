import { describe, it, expect } from "vitest";
import { daemonSocketPath } from "../../src/daemon/paths.js";

describe("daemonSocketPath", () => {
  it("honors CC_DAEMON_SOCK override, else defaults under ~/.claude/cc-daemon", () => {
    expect(daemonSocketPath({ CC_DAEMON_SOCK: "/tmp/x.sock" })).toBe("/tmp/x.sock");
    expect(daemonSocketPath({ HOME: "/home/u" })).toBe("/home/u/.claude/cc-daemon/sock");
  });
});
