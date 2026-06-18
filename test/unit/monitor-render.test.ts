import { describe, it, expect } from "vitest";
import { render } from "../../src/monitor/render.js";
import type { DashboardSnapshot } from "../../src/monitor/snapshot.js";

const base = (over: Partial<DashboardSnapshot>): DashboardSnapshot =>
  ({ daemonUp: true, sessions: [], proactive: undefined, at: 600_000, socketPath: "/tmp/sock", ...over });
const view = { intervalMs: 1000, paused: false };

describe("render", () => {
  it("populated pool: header counts + a row with status/model/ctx%/tokens/age", () => {
    const snap = base({
      proactive: "running",
      sessions: [
        { id: "s-1a2b", status: "busy", model: "opus-4.8", ctxPercent: 62, tokens: 12400, createdAt: 360_000, proactive: "running" },
        { id: "s-5e6f", status: "errored", model: "haiku-4.5", ctxPercent: undefined, tokens: undefined, createdAt: 540_000, proactive: undefined },
      ],
    });
    const out = render(snap, view);
    expect(out).toContain("daemon: ● up");
    expect(out).toContain("sessions 2");
    expect(out).toContain("proactive ● running");
    expect(out).toMatch(/s-1a2b.*busy.*opus-4\.8.*62%.*12\.4k.*4m/s);
    expect(out).toMatch(/s-5e6f.*err.*—.*—/s);          // errored row shows em-dashes for ctx/usage
    expect(out).toContain("[p]ause");
    expect(out).toContain("[q]uit");
  });

  it("empty pool shows (no sessions)", () => {
    expect(render(base({ sessions: [] }), view)).toContain("(no sessions)");
  });

  it("daemon down shows a waiting line with the socket path", () => {
    const out = render(base({ daemonUp: false, socketPath: "/tmp/sock" }), view);
    expect(out).toContain("daemon: ○ down");
    expect(out).toContain("waiting for daemon at /tmp/sock");
  });

  it("paused footer shows PAUSED", () => {
    expect(render(base({}), { intervalMs: 1000, paused: true })).toContain("PAUSED");
  });
});
