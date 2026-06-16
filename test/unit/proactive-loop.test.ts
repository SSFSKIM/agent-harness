import { describe, it, expect } from "vitest";
import { ProactiveLoop } from "../../src/proactive/loop.js";
import { resolveProactiveConfig } from "../../src/proactive/types.js";
import type { ProactiveConfigInput, ProactiveDeps } from "../../src/proactive/types.js";

// A manual scheduler: records scheduled callbacks; the test fires them explicitly (no real timers).
function manualScheduler() {
  const entries: { fn: () => void; ms: number; live: boolean }[] = [];
  const schedule = (fn: () => void, ms: number) => {
    const e = { fn, ms, live: true };
    entries.push(e);
    return () => { e.live = false; };
  };
  // Fire the latest still-live scheduled tick, then let runTurn microtasks drain.
  const fire = async () => {
    const e = [...entries].reverse().find((x) => x.live);
    if (!e) throw new Error("nothing scheduled to fire");
    e.live = false;
    e.fn();
    await new Promise((r) => setTimeout(r, 0));
  };
  const lastDelay = () => entries.at(-1)?.ms;
  return { schedule, fire, lastDelay, entries };
}

function harness(
  cfg: ProactiveConfigInput,
  opts: {
    results?: unknown[];
    idle?: (r: unknown) => boolean;
    runTurn?: (p: string) => Promise<{ result: unknown }>;
    interrupt?: () => Promise<void>;
  } = {},
) {
  const ticks: string[] = [];
  const sched = manualScheduler();
  let i = 0;
  const runTurn = opts.runTurn ?? (async (p: string) => { ticks.push(p); return { result: opts.results ? opts.results[i++] : "ok" }; });
  const interruptCalls: number[] = [];
  const deps: ProactiveDeps = {
    runTurn,
    schedule: sched.schedule,
    idleDetector: opts.idle ?? (() => false),
    interrupt: opts.interrupt ?? (async () => { interruptCalls.push(1); }),
  };
  const loop = new ProactiveLoop(resolveProactiveConfig(cfg), deps);
  return { loop, ticks, sched, interruptCalls };
}

describe("ProactiveLoop — ticking & bounds", () => {
  it("start() schedules the first tick; firing injects the tickPrompt and reschedules at base interval", async () => {
    const h = harness({ tickPrompt: "T", intervalMs: 1000 });
    expect(h.loop.status().state).toBe("idle");
    h.loop.start();
    expect(h.loop.status().state).toBe("running");
    expect(h.sched.lastDelay()).toBe(1000);
    await h.sched.fire();
    expect(h.ticks).toEqual(["T"]);
    expect(h.loop.status().tickCount).toBe(1);
    expect(h.sched.lastDelay()).toBe(1000); // non-idle → base cadence
  });

  it("stops with reason 'maxTicks' exactly after N productive ticks", async () => {
    const h = harness({ intervalMs: 1000, maxTicks: 2 });
    h.loop.start();
    await h.sched.fire();                 // tick 1
    await h.sched.fire();                 // tick 2 → maxTicks reached
    expect(h.loop.status()).toMatchObject({ state: "stopped", reason: "maxTicks", tickCount: 2 });
    await expect(h.loop.done).resolves.toBeUndefined();
  });

  it("start() is idempotent (no-op when not idle)", async () => {
    const h = harness({ intervalMs: 1000 });
    h.loop.start();
    const n = h.sched.entries.length;
    h.loop.start();                       // already running
    expect(h.sched.entries.length).toBe(n);
  });
});

describe("ProactiveLoop — idle backoff", () => {
  it("consecutive idle ticks grow the interval by factor**idleCount and stop after stopAfterIdle", async () => {
    const h = harness(
      { intervalMs: 100, idleBackoff: { factor: 2, maxIntervalMs: 10_000, stopAfterIdle: 3 } },
      { idle: () => true },
    );
    h.loop.start();
    await h.sched.fire();                 // idle 1 → delay 100*2^1 = 200
    expect(h.loop.status().idleCount).toBe(1);
    expect(h.sched.lastDelay()).toBe(200);
    await h.sched.fire();                 // idle 2 → delay 100*2^2 = 400
    expect(h.sched.lastDelay()).toBe(400);
    await h.sched.fire();                 // idle 3 → stop
    expect(h.loop.status()).toMatchObject({ state: "stopped", reason: "idle", idleCount: 3 });
  });

  it("a non-idle tick resets idleCount and the interval", async () => {
    const h = harness(
      { intervalMs: 100, idleBackoff: { factor: 2, maxIntervalMs: 10_000, stopAfterIdle: 5 } },
      { results: ["IDLE", "did work"], idle: (r) => r === "IDLE" },
    );
    h.loop.start();
    await h.sched.fire();                 // idle → idleCount 1, delay 200
    expect(h.sched.lastDelay()).toBe(200);
    await h.sched.fire();                 // non-idle → reset
    expect(h.loop.status().idleCount).toBe(0);
    expect(h.sched.lastDelay()).toBe(100);
  });
});

describe("ProactiveLoop — error backoff", () => {
  it("a rejecting runTurn grows errorCount, backs off, and stops after stopAfterErrors", async () => {
    const h = harness(
      { intervalMs: 100, errorBackoff: { factor: 2, maxIntervalMs: 10_000, stopAfterErrors: 2 } },
      { runTurn: async () => { throw new Error("dead session"); } },
    );
    h.loop.start();
    await h.sched.fire();                 // error 1 → delay 100*2^1 = 200
    expect(h.loop.status().errorCount).toBe(1);
    expect(h.sched.lastDelay()).toBe(200);
    await h.sched.fire();                 // error 2 → stop
    expect(h.loop.status()).toMatchObject({ state: "stopped", reason: "error", errorCount: 2 });
  });
});

describe("ProactiveLoop — pause / resume", () => {
  it("pause() cancels the pending tick; resume() reschedules at base cadence", async () => {
    const h = harness({ intervalMs: 1000 });
    h.loop.start();
    await h.loop.pause();
    expect(h.loop.status().state).toBe("paused");
    await expect(h.sched.fire()).rejects.toThrow(/nothing scheduled/); // pending was cancelled
    h.loop.resume();
    expect(h.loop.status().state).toBe("running");
    await h.sched.fire();
    expect(h.loop.status().tickCount).toBe(1);
  });

  it("pause() interrupts an in-flight tick", async () => {
    let release!: (v: { result: unknown }) => void;
    const gate = new Promise<{ result: unknown }>((r) => { release = r; });
    const h = harness({ intervalMs: 1000 }, { runTurn: () => gate });
    h.loop.start();
    await h.sched.fire();                 // tick is now awaiting the gate (in flight)
    const pauseP = h.loop.pause();
    expect(h.interruptCalls.length).toBe(1); // interrupt fired for the in-flight tick
    release({ result: "ok" });
    await pauseP;
    expect(h.loop.status().state).toBe("paused");
  });
});

describe("ProactiveLoop — teardown liveness (the four)", () => {
  it("stop() while idle resolves done and prevents further ticks", async () => {
    const h = harness({ intervalMs: 1000 });
    h.loop.start();
    await h.loop.stop("manual");
    expect(h.loop.status()).toMatchObject({ state: "stopped", reason: "manual" });
    await expect(h.loop.done).resolves.toBeUndefined();
    await expect(h.sched.fire()).rejects.toThrow(/nothing scheduled/); // pending cancelled, none rescheduled
  });

  it("stop() while a tick is in flight drains cleanly and never reschedules", async () => {
    let release!: (v: { result: unknown }) => void;
    const gate = new Promise<{ result: unknown }>((r) => { release = r; });
    const h = harness({ intervalMs: 1000 }, { runTurn: () => gate });
    h.loop.start();
    await h.sched.fire();                 // tick in flight, awaiting gate
    const stopP = h.loop.stop("manual");
    release({ result: "ok" });            // let the in-flight runTurn settle
    await stopP;
    await expect(h.loop.done).resolves.toBeUndefined();
    const n = h.sched.entries.filter((e) => e.live).length;
    expect(n).toBe(0);                    // no live scheduled tick survived teardown
  });

  it("stop() is idempotent and keeps the first reason", async () => {
    const h = harness({ intervalMs: 1000 });
    h.loop.start();
    await h.loop.stop("first");
    await h.loop.stop("second");
    expect(h.loop.status().reason).toBe("first");
    await expect(h.loop.done).resolves.toBeUndefined();
  });

  it("pause() then stop() settles without a hang", async () => {
    const h = harness({ intervalMs: 1000 });
    h.loop.start();
    await h.loop.pause();
    await h.loop.stop("manual");
    expect(h.loop.status().state).toBe("stopped");
    await expect(h.loop.done).resolves.toBeUndefined();
  });
});
