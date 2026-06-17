import type { ProactiveConfig, ProactiveDeps, ProactiveState, ProactiveStatus } from "./types.js";

/** A pacing/gating loop over a live session: self-wakes via `schedule`, injects `tickPrompt` through
 *  `runTurn`, backs off on idle/error, and stops on a bound. Never throws out of a tick. */
export class ProactiveLoop {
  private state: ProactiveState = "idle";
  private tickCount = 0;
  private idleCount = 0;
  private errorCount = 0;
  private reason?: string;
  private pending?: () => void;          // cancel the scheduled next tick
  private inFlight?: Promise<{ result: unknown }>; // the awaiting runTurn (for clean teardown)
  private resolveDone!: () => void;
  readonly done: Promise<void>;

  constructor(private cfg: ProactiveConfig, private deps: ProactiveDeps) {
    this.done = new Promise((r) => { this.resolveDone = r; });
  }

  status(): ProactiveStatus {
    return { state: this.state, tickCount: this.tickCount, idleCount: this.idleCount, errorCount: this.errorCount, reason: this.reason };
  }

  start(): void {
    if (this.state !== "idle") return;
    this.state = "running";
    this.scheduleNext(this.cfg.intervalMs);
  }

  async pause(): Promise<void> {
    if (this.state !== "running") return;
    this.state = "paused";
    this.cancelPending();
    // Signal the in-flight tick to abort; we do NOT drain it (unlike stop()) — the tick settles on
    // its own and the `state === "running"` reschedule guard keeps it from re-arming while paused.
    if (this.inFlight) await this.deps.interrupt?.();
  }

  resume(): void {
    if (this.state !== "paused") return;
    this.state = "running";
    this.scheduleNext(this.cfg.intervalMs);
  }

  /** External terminal stop. Drains any in-flight tick before resolving `done`. Idempotent. */
  async stop(reason: string): Promise<void> {
    if (this.state === "stopped") { await this.done; return; }
    this.state = "stopped";
    this.reason = reason;
    this.cancelPending();
    const flight = this.inFlight;
    if (flight) { try { await flight; } catch { /* the runTurn outcome is irrelevant once stopped */ } }
    this.resolveDone();
  }

  private scheduleNext(delay: number): void {
    this.pending = this.deps.schedule(() => { void this.tick(); }, delay);
  }
  private cancelPending(): void { this.pending?.(); this.pending = undefined; }

  /** Internal terminal stop, called from inside a tick when a bound is hit. Synchronous (no self-await). */
  private finish(reason: string): void {
    if (this.state === "stopped") return;
    this.state = "stopped";
    this.reason = reason;
    this.cancelPending();
    this.resolveDone();
  }

  private async tick(): Promise<void> {
    this.pending = undefined;
    if (this.state !== "running") return;
    let delay = this.cfg.intervalMs;
    try {
      this.inFlight = this.deps.runTurn(this.cfg.tickPrompt); // inside try: a sync throw becomes error-backoff, not an unhandled rejection
      const { result } = await this.inFlight;
      this.tickCount++;
      if (this.deps.idleDetector(result)) {
        this.idleCount++; this.errorCount = 0;
        if (this.idleCount >= this.cfg.idleBackoff.stopAfterIdle) return this.finish("idle");
        delay = Math.min(this.cfg.intervalMs * this.cfg.idleBackoff.factor ** this.idleCount, this.cfg.idleBackoff.maxIntervalMs);
      } else {
        this.idleCount = 0; this.errorCount = 0;
      }
      if (this.cfg.maxTicks != null && this.tickCount >= this.cfg.maxTicks) return this.finish("maxTicks");
    } catch {
      this.errorCount++;
      if (this.errorCount >= this.cfg.errorBackoff.stopAfterErrors) return this.finish("error");
      delay = Math.min(this.cfg.intervalMs * this.cfg.errorBackoff.factor ** this.errorCount, this.cfg.errorBackoff.maxIntervalMs);
    } finally {
      this.inFlight = undefined;
    }
    if (this.state === "running") this.scheduleNext(delay);
  }
}
