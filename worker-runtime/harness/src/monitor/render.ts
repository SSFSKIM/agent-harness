import type { DashboardSnapshot, SessionRow } from "./snapshot.js";
import type { ProactiveState } from "../proactive/types.js";

export interface ViewState { intervalMs: number; paused: boolean; }

const STATUS_GLYPH: Record<SessionRow["status"], string> = { busy: "●", idle: "○", errored: "⚠", restarting: "↻" };
const STATUS_WORD: Record<SessionRow["status"], string> = { busy: "busy", idle: "idle", errored: "err", restarting: "restarting" };
const PROACTIVE_GLYPH: Record<ProactiveState, string> = { running: "●", paused: "‖", stopped: "■", idle: "○" };

function humanTokens(n?: number): string { if (n === undefined) return "—"; return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n); }
function humanAge(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60); if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60); return `${h}h`;
}
function pct(p?: number): string { return p === undefined ? "—" : `${p}%`; }
function pad(s: string, w: number): string { return s.length >= w ? s : s + " ".repeat(w - s.length); }

/** Render the full-screen frame as a string. Pure — no I/O, no escape codes (the loop owns cursor/clear). */
export function render(snap: DashboardSnapshot, view: ViewState): string {
  const lines: string[] = [];
  lines.push(`cc-harness top — ${snap.socketPath ?? ""}`.trimEnd());
  lines.push("─".repeat(56));
  if (!snap.daemonUp) {
    lines.push(`daemon: ○ down — waiting for daemon at ${snap.socketPath ?? "?"}…`);
    lines.push("");
    lines.push(footer(view));
    return lines.join("\n");
  }
  const heartbeat = snap.proactive ? `proactive ${PROACTIVE_GLYPH[snap.proactive]} ${snap.proactive}` : "proactive — none";
  lines.push(`daemon: ● up   sessions ${snap.sessions.length}   ${heartbeat}`);
  lines.push("");
  if (!snap.sessions.length) {
    lines.push("(no sessions)");
  } else {
    lines.push(` ${pad("ID", 9)}${pad("STATUS", 9)}${pad("MODEL", 13)}${pad("CTX%", 7)}${pad("USAGE", 9)}AGE`);
    for (const r of snap.sessions) {
      const status = `${STATUS_GLYPH[r.status]} ${STATUS_WORD[r.status]}`;
      lines.push(` ${pad(r.id, 9)}${pad(status, 9)}${pad(r.model ?? "—", 13)}${pad(pct(r.ctxPercent), 7)}${pad(humanTokens(r.tokens), 9)}${humanAge(snap.at - r.createdAt)}`);
    }
  }
  lines.push("");
  lines.push(footer(view));
  return lines.join("\n");
}

function footer(view: ViewState): string {
  return `refresh ${Math.round(view.intervalMs / 1000)}s · [p]ause [q]uit${view.paused ? "  · PAUSED" : ""}`;
}
