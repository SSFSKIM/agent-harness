import { collect, type MonitorClient, type DashboardSnapshot } from "./snapshot.js";
import { render } from "./render.js";

const ESC = String.fromCharCode(27); // the ASCII escape byte; kept out of the source as a literal
const ALT_ENTER = ESC + "[?1049h", CURSOR_HIDE = ESC + "[?25l", HOME_CLEAR = ESC + "[H" + ESC + "[2J";
const CURSOR_SHOW = ESC + "[?25h", ALT_LEAVE = ESC + "[?1049l";
const CTRL_C = String.fromCharCode(3);

export interface MonitorInput {
  setRawMode?(b: boolean): void;
  resume(): void; pause(): void;
  on(ev: "data", h: (d: Buffer | string) => void): void;
  off(ev: "data", h: (d: Buffer | string) => void): void;
}
export interface MonitorOut { write(s: string): void; isTTY?: boolean; }

export interface MonitorOpts {
  client: MonitorClient;
  socketPath?: string;
  intervalMs?: number;
  once?: boolean;
  out?: MonitorOut;
  input?: MonitorInput;
  now?: () => number;
  schedule?: (fn: () => void, ms: number) => () => void;
  onSignal?: (handler: () => void) => () => void; // register a quit handler (e.g. SIGTERM); returns an unregister
}

/** Run the dashboard loop. Resolves when the user quits (q / Ctrl-C / signal), or after one frame for once/non-TTY. */
export async function runMonitor(opts: MonitorOpts): Promise<void> {
  const out = opts.out ?? process.stdout;
  const now = opts.now ?? Date.now;
  const intervalMs = opts.intervalMs ?? 1000;
  const view = { intervalMs, paused: false };

  // One-shot path: a single frame, no alt screen, no input wiring. !out.isTTY catches piped stdout (isTTY undefined).
  if (opts.once || !out.isTTY) {
    out.write(render(await collect(opts.client, { now, socketPath: opts.socketPath }), view) + "\n");
    return;
  }

  const input = opts.input ?? (process.stdin as unknown as MonitorInput);
  const schedule = opts.schedule ?? ((fn, ms) => { const t = setInterval(fn, ms); return () => clearInterval(t); });
  out.write(ALT_ENTER + CURSOR_HIDE);

  // No await before this Promise on the live path -> input is wired before runMonitor yields control.
  return new Promise<void>((resolve) => {
    let tornDown = false, inFlight = false;
    let lastSnap: DashboardSnapshot | undefined;
    let cancel: () => void = () => {};
    let unregisterSignal: (() => void) | undefined;
    const draw = (frame: string) => out.write(HOME_CLEAR + frame);
    const tick = async () => {
      if (inFlight) return;            // in-flight guard: never stack ticks over a slow collect
      inFlight = true;
      try { lastSnap = await collect(opts.client, { now, socketPath: opts.socketPath }); if (!tornDown) draw(render(lastSnap, view)); }
      finally { inFlight = false; }
    };
    const teardown = () => {
      if (tornDown) return;            // idempotent: q + signal + double-q all collapse to one teardown
      tornDown = true;
      cancel();
      input.off("data", onKey);
      input.setRawMode?.(false); input.pause();
      unregisterSignal?.();
      out.write(CURSOR_SHOW + ALT_LEAVE);
      resolve();
    };
    const onKey = (d: Buffer | string) => {
      const s = d.toString();
      if (s === "q" || s === CTRL_C) { teardown(); return; }   // q or Ctrl-C (raw mode delivers ETX as data)
      if (s === "p") {
        view.paused = !view.paused;
        if (view.paused) cancel(); else cancel = schedule(tick, intervalMs);
        if (lastSnap) draw(render(lastSnap, view));   // refresh the footer PAUSED marker without a new poll
      }
    };
    input.setRawMode?.(true); input.resume(); input.on("data", onKey);
    unregisterSignal = opts.onSignal?.(teardown);
    void tick();                              // immediate first paint (fire-and-forget; input already wired)
    cancel = schedule(tick, intervalMs);      // schedule synchronously so overlap exercises the in-flight guard
  });
}
