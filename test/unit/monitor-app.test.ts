import { describe, it, expect } from "vitest";
import { EventEmitter } from "node:events";
import { runMonitor, type MonitorOpts } from "../../src/monitor/app.js";
import type { MonitorClient } from "../../src/monitor/snapshot.js";

function fakeOut() { const chunks: string[] = []; return { chunks, write: (s: string) => { chunks.push(s); }, isTTY: true }; }
class FakeInput extends EventEmitter {
  raw?: boolean; resumed = false; paused = false;
  setRawMode(b: boolean) { this.raw = b; } resume() { this.resumed = true; } pause() { this.paused = true; }
  key(s: string) { this.emit("data", s); }
}
const okClient = (over: Partial<MonitorClient> = {}): MonitorClient =>
  ({ list: async () => [], contextUsage: async () => ({}), ...over });

// a manual scheduler: captures the tick fn so the test fires ticks deterministically
function manualSchedule() { const fns: Array<() => void> = []; const cancels: number[] = []; let n = 0;
  const schedule = (fn: () => void) => { fns.push(fn); const i = n++; return () => cancels.push(i); };
  return { schedule, fire: () => fns.forEach((f) => f()), cancels };
}

describe("runMonitor", () => {
  it("once / non-TTY: writes exactly one frame, no alt-screen, resolves", async () => {
    const out = fakeOut();
    await runMonitor({ client: okClient(), out, once: true, now: () => 0 });
    const all = out.chunks.join("");
    expect(all).toContain("daemon: ● up");
    expect(all).not.toContain("[?1049h"); // never entered alt screen
  });

  it("live: enters alt screen, renders, and 'q' tears down once (idempotent) and resolves", async () => {
    const out = fakeOut(); const input = new FakeInput(); const sched = manualSchedule();
    const run = runMonitor({ client: okClient(), out, input: input as any, now: () => 0, schedule: sched.schedule });
    // initial frame + alt-screen enter happened synchronously before the first await resolves; let microtasks flush:
    await Promise.resolve();
    input.key("q");
    await run; // resolves on quit
    const all = out.chunks.join("");
    expect(all).toContain("[?1049h");  // entered alt screen
    expect(all).toContain("[?25h");    // restored cursor on teardown
    expect(all).toContain("[?1049l");  // left alt screen on teardown
    expect(input.raw).toBe(false);           // raw mode restored
    expect(sched.cancels.length).toBe(1);    // timer cancelled exactly once
    input.key("q");                          // a second quit is a no-op (no throw, already torn down)
  });

  it("skips a tick while a prior collect is still in flight", async () => {
    let calls = 0; let release!: () => void;
    const gate = new Promise<void>((r) => { release = r; });
    const client = okClient({ list: async () => { calls++; await gate; return []; } });
    const out = fakeOut(); const input = new FakeInput(); const sched = manualSchedule();
    const run = runMonitor({ client, out, input: input as any, now: () => 0, schedule: sched.schedule });
    await Promise.resolve();
    sched.fire(); sched.fire();   // two more ticks while the first collect is blocked
    expect(calls).toBe(1);        // in-flight guard: only the initial collect ran
    release();                    // unblock
    input.key("q");
    await run;
  });
});
