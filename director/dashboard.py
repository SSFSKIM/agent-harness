"""Director observability dashboard — a live read-only web view of a run.

The orchestrator persists a rich atomic snapshot (`director/status.py`) and the
queue persists the pending Director requests (`director/queue/__init__.py`); today
the only consumers are code (the inline Director, `director.watch`). This module
adds the human-facing surface the spec asks for: a local browser view a person
glances at to watch "what are the workers doing right now" — read-only, ambient,
distinct from the taste decisions the Director steers (D-2/D-5).

Design owner: docs/product-specs/2026-06-16-director-observability-dashboard.md
(the "구체 계약" note paragraph is the authoritative Symphony-§13.7 contract:
`GET /api/v1/state`, `404`/`405`, `{"error":{code,message}}` envelope,
`counts`+`generated_at`, and pass-through telemetry). Built per
docs/exec-plans/active/2026-06-16-director-observability-dashboard.md.

Layering (Approach B — JSON endpoint + thin client render):
  - build_view() : the WHOLE logic surface — pure, socket-free, unit-tested directly.
  - HTTP shim    : a ~2-route http.server handler over build_view (M2).
  - inline page  : one HTML string whose vanilla JS polls /api/v1/state (M3).

stdlib-only by grain (no third-party deps anywhere under director/): http.server,
urllib, json, threading. Read-only: no mutation of status/queue, no new exec
surface — a localhost (127.0.0.1) instrument, never a gate on a run.
"""
from __future__ import annotations

import argparse
import datetime
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import director.queue as dq
from director import board_snapshot
from director import director_min as dm
from director import history
from director import status
from director import ticket_events

# The single versioned, read-only data route (Symphony §13.7 alignment).
_STATE_PATH = "/api/v1/state"
# The server-push variant of _STATE_PATH: an SSE stream of build_view, pushed on change.
_STREAM_PATH = "/api/v1/stream"
# Cross-run history: the last N completed-run summaries (Phase B), read-only.
_HISTORY_PATH = "/api/v1/history"
# The single write route — answer a pending Director-queue request (operator console).
_ANSWER_PATH = "/api/v1/answer"
# Per-ticket session-event drill-down: GET /api/v1/ticket/<id>/events (history+telemetry)
# and /stream (live SSE tail). The <id> segment is sanitized before any path join (R5).
_TICKET_PREFIX = "/api/v1/ticket/"
# Whole-board layered-DAG view (project graph): the derived board_snapshot view.
_BOARD_PATH = "/api/v1/board"
# The graph page (M2 spike): a SECOND page that renders /api/v1/board as a layered DAG
# via the vendored library. The flat-list `/` page is untouched; M4 promotes this to `/`.
_GRAPH_PATH = "/graph"
# Fixed vendored-asset map (R6): the ONLY servable asset paths. A request can name only
# one of these constant keys — the value is a fixed filename under director/assets/, so
# there is ZERO request-derived path (ARCHITECTURE invariant 3: zero traversal). Offline:
# served from the local checked-in file, never a CDN. `text/javascript` per WHATWG.
_JS = "text/javascript; charset=utf-8"
_ASSETS = {
    "/assets/cytoscape.min.js": ("cytoscape.min.js", _JS),
    "/assets/dagre.min.js": ("dagre.min.js", _JS),
    "/assets/cytoscape-dagre.js": ("cytoscape-dagre.js", _JS),
}
_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
_DEFAULT_PORT = 8787

# SSE cadence: re-read the (file-backed) snapshot this often server-side and push only a
# CHANGED view; a heartbeat keeps the connection alive / detects a dead peer between changes.
_STREAM_POLL_S = 0.5
_STREAM_HEARTBEAT_S = 15.0

# Queue kinds a human/console answers. Excludes `mergeRequest` (the serialized
# merger's worklist — answering it would silently consume a merge) and `runReport`
# (informational). Shared with `director.notify` (the park-notify filter).
HUMAN_BOUND_KINDS = ("turnReview", "commandApproval", "fileChange",
                     "userInput", "elicitation", "mergeReview")
# Localhost hostnames accepted on a write (Origin/Host fence).
_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# Pending-request summary cap: glance-able, not a full payload dump (plan Decision log).
_SUMMARY_LIMIT = 140


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _clip(value) -> str:
    """A best-effort one-line summary string, clipped. None/anything → safe str."""
    return str(value or "")[:_SUMMARY_LIMIT]


def _summary_for(kind, payload) -> str:
    """Glance-able summary for a pending request, keyed by kind (tolerant).

    Pulls the most human-meaningful field per kind from the request payload; a
    missing/garbage payload yields "" (never raises) — the queue's verified shapes:
    turnReview→final_message; mergeReview/mergeRequest→result/reason/pr/branch;
    commandApproval→command (or reason); fileChange→reason; userInput/elicitation→
    questions; anything else→the kind name itself.
    """
    p = payload if isinstance(payload, dict) else {}
    if kind == "turnReview":
        return _clip(p.get("final_message"))
    if kind in ("mergeReview", "mergeRequest"):
        primary = [str(p[k]) for k in ("result", "reason") if p.get(k)]  # mergeReview
        if primary:
            return _clip(" ".join(primary))
        fallback = [str(p[k]) for k in ("pr", "branch") if p.get(k)]  # mergeRequest
        return _clip(" ".join(fallback))
    if kind == "commandApproval":
        cmd = p.get("command")
        if isinstance(cmd, list):
            return _clip(" ".join(str(x) for x in cmd))
        return _clip(cmd or p.get("reason"))
    if kind == "fileChange":
        return _clip(p.get("reason"))
    if kind in ("userInput", "elicitation"):
        return _clip(p.get("questions"))
    return _clip(kind)


def _summarize_request(req: dict) -> dict:
    return {"request_id": req.get("request_id"),
            "ticket_id": req.get("ticket_id"),
            "kind": req.get("kind"),
            "summary": _summary_for(req.get("kind"), req.get("payload"))}


def _read_pending(queue_dir) -> list[dict]:
    """read_pending, but tolerant at the dashboard boundary. The queue is appended
    line-by-line (NOT temp+os.replace like status.json) and is shared across parallel
    processes, so a live reader CAN catch a half-written final line — `read_requests`
    would then raise on json.loads. R5 forbids changing the queue module, so the
    tolerance lives here: a torn/absent queue degrades to "no pending" rather than
    500-ing the view (R3 — visibility is a read-only instrument, never a gate)."""
    try:
        return dq.read_pending(base=queue_dir)
    except (OSError, ValueError, KeyError):
        # ValueError: json.JSONDecodeError on a torn line. KeyError: read_pending does
        # r["request_id"] per row, so a parseable line missing that key raises. Either
        # way a malformed/concurrent queue degrades to "no pending", never a 500.
        return []


def _host_is_local(value) -> bool:
    """A Host (`127.0.0.1:8787`) or Origin (`http://127.0.0.1:8787`) header whose
    hostname is loopback. Empty/foreign → False (the write fence, R5)."""
    if not value:
        return False
    # urlparse needs a scheme/netloc marker; a bare Host ("127.0.0.1:8787" / "[::1]:8787")
    # is parsed by prefixing "//" so IPv6 + ports resolve (vs a naive ":" split).
    host = urlparse(value if "//" in value else "//" + value).hostname
    return host in _LOCAL_HOSTS


def _validate_disposition(disp) -> str | None:
    """None if `disp` is a turn-review disposition the orchestrator will execute,
    else a human-readable reason. Mirrors `decider.disposition_from_answer`'s contract
    (kind ∈ terminal|reply|escalate, non-empty reply) and additionally requires a
    terminal to carry `outcome.status ∈ done|blocked` — so the console never writes an
    answer that reconcile would treat as `terminal_unknown`."""
    if not isinstance(disp, dict):
        return "disposition must be an object"
    kind = disp.get("kind")
    if kind not in ("terminal", "reply", "escalate"):
        return "disposition.kind must be terminal|reply|escalate"
    if kind == "reply" and not (disp.get("reply") or "").strip():
        return "a reply disposition needs a non-empty reply"
    if kind == "terminal":
        outcome = disp.get("outcome")
        if not isinstance(outcome, dict) or outcome.get("status") not in ("done", "blocked"):
            return "a terminal disposition needs outcome.status in done|blocked"
    return None


def build_view(status_dir=None, queue_dir=None, *, now=_utcnow) -> dict:
    """Normalize the run snapshot + pending queue into one read-only view dict.

    Pure (no socket, no mutation) — the entire logic surface, so it is unit-tested
    directly without HTTP. `run`/`in_flight`/`stuck`/`recent` are pass-through: the
    telemetry the producer now ships rides INSIDE them (run.codex_totals/rate_limits,
    recent[].tokens/session_id/last_message), so the renderer computes nothing — it
    only shapes `pending`, `counts`, and `generated_at`. Tolerant by contract: a
    missing or torn status.json makes `read_status` return None → `run: None` here
    (the page reads that as "no active run"), never an exception (spec R3/R6).
    """
    # read_status guarantees dict|None|malformed: None when missing/unparseable, but ANY
    # other valid JSON (a list/string/int from a producer bug or hand-edit) comes back
    # as-is. Coerce a non-dict to "no run" so .get below can never raise (R3/R6: the view
    # tolerates a garbage-but-valid status.json the same as a torn one — never a gate).
    snap = status.read_status(base=status_dir)
    snap = snap if isinstance(snap, dict) else {}
    in_flight = snap.get("in_flight", [])
    stuck = snap.get("stuck", [])
    recent = snap.get("recent", [])
    pending = [_summarize_request(r) for r in _read_pending(queue_dir)]
    return {
        "run": snap.get("run"),  # None when no run / unreadable (telemetry rides inside)
        "in_flight": in_flight,
        "stuck": stuck,
        "recent": recent,
        "pending": pending,
        "counts": {"in_flight": len(in_flight), "stuck": len(stuck),
                   "recent": len(recent), "pending": len(pending)},
        "generated_at": now(),
    }


def _stream_loop(write, view_fn, *, sleep, now, should_run, heartbeat_s, poll_s) -> None:
    """Push the view as Server-Sent Events until the peer disconnects.

    Emits a `data: <json>\\n\\n` frame ONLY when the view's CONTENT changes — the
    always-fresh `generated_at` timestamp is excluded from the change key, so an idle
    run doesn't stream a frame every tick (the pushed event still carries new state —
    less client churn than the fixed poll),
    else a `: ping\\n\\n` comment heartbeat after `heartbeat_s` of no change (keeps the
    connection alive and surfaces a dead peer). A `write` raising the client-disconnect
    errno family ends the loop quietly (R14 — never a crash, never stderr).

    Pure and fully injectable (`write`/`view_fn`/`sleep`/`now`/`should_run`) so the push
    logic is unit-tested without a socket — the same testability lever as `build_view`
    (the HTTP `_stream` shim below is a ~5-line adapter over this)."""
    last = None
    last_beat = now()
    while should_run():
        view = view_fn()
        payload = json.dumps(view)
        # Change-detect on a STABLE projection: build_view() stamps a fresh `generated_at`
        # every call, so diffing the whole payload would mark every tick "changed" — a data
        # frame each poll and the heartbeat branch never reached. Exclude that one volatile
        # field from the key (the SENT frame still carries it).
        key = json.dumps({k: v for k, v in view.items() if k != "generated_at"}) \
            if isinstance(view, dict) else payload
        try:
            if key != last:
                write(("data: " + payload + "\n\n").encode("utf-8"))
                last = key
                last_beat = now()
            elif now() - last_beat >= heartbeat_s:
                write(b": ping\n\n")
                last_beat = now()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return  # peer gone mid-write — quiet drop (R14), the daemon thread ends
        sleep(poll_s)


# The whole client: one self-contained HTML string (CSS + vanilla JS poller), no
# framework, no bundler, no external asset — offline-OK (stdlib-only grain). It polls
# GET /api/v1/state ~1s and re-renders the DOM. Every data value is written via
# textContent (never innerHTML), so producer text can never be parsed as markup.
PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>director dashboard</title>
<meta name="director-token" content="__DIRECTOR_TOKEN__">
<style>
  body { background:#0e1116; color:#d6dde6; font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; margin:1.2rem; }
  h1 { font-size:15px; font-weight:600; margin:0 0 .6rem; }
  h2 { font-size:12px; text-transform:uppercase; letter-spacing:.08em; color:#7d8896; margin:1.1rem 0 .3rem; }
  .muted { color:#7d8896; }
  .run { display:flex; flex-wrap:wrap; gap:.4rem; margin-bottom:.2rem; }
  .tag { background:#1b2230; border:1px solid #2a3343; border-radius:.4rem; padding:.05rem .45rem; }
  .badge { background:#3a1d1d; border:1px solid #6b2b2b; color:#ffb4b4; border-radius:.4rem; padding:.05rem .45rem; }
  .item { padding:.12rem .1rem; border-bottom:1px solid #161c26; white-space:pre-wrap; }
  .ok { color:#6ee7a8; } .bad { color:#ff9b9b; }
  .pitem { padding:.3rem .1rem; border-bottom:1px solid #161c26; white-space:pre-wrap; }
  .ctl { margin-top:.25rem; display:flex; gap:.3rem; align-items:center; flex-wrap:wrap; }
  .ctl textarea { background:#0b0e13; color:#d6dde6; border:1px solid #2a3343; border-radius:.3rem; font:inherit; min-width:15rem; height:1.7rem; padding:.15rem .35rem; }
  button.act { background:#1b2230; color:#d6dde6; border:1px solid #2a3343; border-radius:.3rem; padding:.12rem .55rem; cursor:pointer; font:inherit; }
  button.act:hover { background:#26304199; }
  .tk { cursor:pointer; } .tk:hover { background:#161c26; }
  .drill { border:1px solid #2a3343; border-radius:.4rem; margin:.4rem 0; padding:.3rem .5rem; background:#11161f; }
  .drillhead { display:flex; gap:.4rem; align-items:center; margin-bottom:.2rem; }
  .evt { padding:.1rem .1rem; border-bottom:1px solid #161c26; white-space:pre-wrap; }
  .evt.tool { color:#9ecbff; } .evt.msg { color:#d6dde6; } .evt.tok { color:#7d8896; } .evt.turn { color:#6ee7a8; }
</style></head><body>
<h1>director dashboard <span id="updated" class="muted"></span></h1>
<div id="run" class="run"></div>
<div id="counts" class="muted"></div>
<h2>in-flight</h2><div id="inflight"></div>
<h2>stuck</h2><div id="stuck"></div>
<h2>recent</h2><div id="recent"></div>
<h2>pending (director queue)</h2><div id="pending"></div>
<h2>ticket detail (live — click an in-flight or recent ticket)</h2><div id="drill"></div>
<h2>history (recent runs)</h2><div id="history"></div>
<script>
const $ = (id) => document.getElementById(id);
function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined && text !== null) n.textContent = String(text);
  if (cls) n.className = cls;
  return n;
}
function fmtTokens(t) {
  if (!t || t.total == null) return "—";
  return t.total + " tok (in " + t.input + " / out " + t.output + ")";
}
function fmtRateLimits(rl) {
  // Tolerant (client-side R12): render a glance-able summary from recognizable fields,
  // degrade to a compact key=value summary for an odd shape, "" for null — never a raw
  // JSON dump, never throw on a missing field. Real codex shape pinned in the E2E.
  if (!rl || typeof rl !== "object") return "";
  let pct = null;
  if (typeof rl.used_percent === "number") pct = rl.used_percent;
  else if (typeof rl.usedPercent === "number") pct = rl.usedPercent;
  else if (typeof rl.remaining === "number" && typeof rl.limit === "number" && rl.limit > 0)
    pct = 100 * (1 - rl.remaining / rl.limit);
  let resets = null;
  if (typeof rl.resets_in_seconds === "number") resets = rl.resets_in_seconds;
  else if (typeof rl.reset_in_seconds === "number") resets = rl.reset_in_seconds;
  else if (typeof rl.window_minutes === "number") resets = rl.window_minutes * 60;
  const parts = [];
  if (pct !== null) {
    const f = Math.max(0, Math.min(10, Math.round(pct / 10)));
    parts.push("rate " + "▮".repeat(f) + "▯".repeat(10 - f) + " " + Math.round(pct) + "%");
  }
  if (resets !== null) parts.push("resets ~" + Math.round(resets / 60) + "m");
  if (parts.length) return parts.join(" · ");
  return "rate " + Object.keys(rl).map(k => k + "=" + rl[k]).join(" ").slice(0, 60);
}
function fill(id, lines) {
  const box = $(id); box.innerHTML = "";
  if (!lines.length) { box.appendChild(el("div", "—", "muted")); return; }
  // A 3rd element (ticket id) makes the row a click-trigger for the live drill-down.
  // The row is rebuilt every frame (innerHTML reset above) — harmless, it is only a
  // trigger; the drill panel itself lives in #drill, which this render never touches.
  for (const [text, cls, tid] of lines) {
    const d = el("div", text, (cls || "item") + (tid ? " tk" : ""));
    if (tid) { d.title = "click to stream this ticket's events"; d.onclick = () => openDrill(tid); }
    box.appendChild(d);
  }
}
function render(v) {
  const run = v.run, h = $("run"); h.innerHTML = "";
  if (!run) { h.appendChild(el("span", "no active run", "muted")); }
  else {
    h.appendChild(el("span", "pass #" + run.pass, "tag"));
    h.appendChild(el("span", "started " + (run.started_at || "—"), "tag"));
    if (run.stopped_reason) h.appendChild(el("span", "stopped: " + run.stopped_reason, "badge"));
    const ct = run.codex_totals || {};
    h.appendChild(el("span", fmtTokens(ct), "tag"));
    h.appendChild(el("span", "runtime " + Math.round(ct.seconds_running || 0) + "s", "tag"));
    const rl = fmtRateLimits(run.rate_limits); if (rl) h.appendChild(el("span", rl, "tag"));
  }
  const c = v.counts || {};
  $("counts").textContent = "in-flight " + (c.in_flight||0) + " · stuck " + (c.stuck||0)
    + " · recent " + (c.recent||0) + " · pending " + (c.pending||0);
  fill("inflight", (v.in_flight||[]).map(e =>
    [(e.identifier||e.ticket_id) + " · " + e.phase + " · a" + e.attempt + "/w" + e.wave
      + (e.tokens ? " · " + fmtTokens(e.tokens) : ""),  // Layer-2: live mid-turn tokens
     "item", e.ticket_id]));                            // 3rd: drill-down trigger
  fill("stuck", (v.stuck||[]).map(s =>
    [s.ticket + " ← " + (s.blocked_by||[]).map(b => b.id).join(", ")]));
  fill("recent", (v.recent||[]).map(r =>
    [(r.status === "completed" ? "✓ " : "✗ ") + (r.ticket||r.ticket_id)
      + " · " + fmtTokens(r.tokens) + (r.session_id ? " · " + r.session_id : ""),
     r.status === "completed" ? "item ok" : "item bad", r.ticket_id]));
  renderPending(v.pending || []);
  $("updated").textContent = "· updated " + (v.generated_at || "");
}
function btn(label, onclick) { const b = el("button", label, "act"); b.onclick = onclick; return b; }
async function answer(payload) {
  const meta = document.querySelector('meta[name=director-token]');
  const token = meta ? meta.content : "";
  let r;
  try {
    r = await fetch("/api/v1/answer", { method: "POST",
      headers: { "Content-Type": "application/json", "X-Director-Token": token },
      body: JSON.stringify(payload) });
  } catch (e) { alert("answer failed: " + e); return; }
  if (!r.ok) {
    let msg = r.status;
    try { const j = await r.json(); if (j.error) msg = j.error.message; } catch (e) {}
    alert("answer failed: " + msg);
  }
  poll();  // refresh now; an answered item drops on the next /api/v1/state
}
function renderPending(items) {
  const box = $("pending"); box.innerHTML = "";
  if (!items.length) { box.appendChild(el("div", "—", "muted")); return; }
  for (const p of items) {
    const rid = p.request_id, kind = p.kind;
    const row = el("div", null, "pitem");
    row.appendChild(el("div", kind + " · " + (p.ticket_id || "") + (p.summary ? " · " + p.summary : "")));
    const ctl = el("div", null, "ctl");
    if (kind === "turnReview") {
      const ta = el("textarea"); ta.placeholder = "reply / escalate reason"; ctl.appendChild(ta);
      ctl.appendChild(btn("reply", () => answer({ request_id: rid, kind, disposition: { kind: "reply", reply: ta.value } })));
      ctl.appendChild(btn("done", () => answer({ request_id: rid, kind, disposition: { kind: "terminal", outcome: { status: "done" } } })));
      ctl.appendChild(btn("blocked", () => answer({ request_id: rid, kind, disposition: { kind: "terminal", outcome: { status: "blocked" } } })));
      ctl.appendChild(btn("escalate", () => answer({ request_id: rid, kind, disposition: { kind: "escalate", reason: ta.value } })));
    } else if (kind === "commandApproval" || kind === "fileChange") {
      ctl.appendChild(btn("accept", () => answer({ request_id: rid, kind, decision: "accept" })));
      ctl.appendChild(btn("decline", () => answer({ request_id: rid, kind, decision: "decline" })));
    } else if (kind === "userInput" || kind === "elicitation") {
      const ta = el("textarea"); ta.placeholder = "answer"; ctl.appendChild(ta);
      ctl.appendChild(btn("send", () => answer({ request_id: rid, kind, answers: { response: ta.value } })));
    } else if (kind === "mergeReview") {
      const ta = el("textarea"); ta.placeholder = "note (for requeue)"; ctl.appendChild(ta);
      ctl.appendChild(btn("requeue", () => answer({ request_id: rid, kind, action: "requeue", note: ta.value })));
      ctl.appendChild(btn("abandon", () => answer({ request_id: rid, kind, action: "abandon", note: ta.value })));
    } else {
      ctl.appendChild(el("span", "(read-only)", "muted"));
    }
    row.appendChild(ctl);
    box.appendChild(row);
  }
}
async function poll() {
  try { const r = await fetch("/api/v1/state"); render(await r.json()); }
  catch (e) { $("updated").textContent = "· fetch error: " + e; }
}
function fmtRun(r) {  // one history row: when · cost · runtime · outcomes · why-it-ended
  const ct = r.codex_totals || {};
  const started = (r.started_at || "").slice(0, 19).replace("T", " ");
  const outs = Object.keys(r.outcomes || {}).map(k => (k === "completed" ? "✓" : "✗") + r.outcomes[k]).join(" ");
  return started + " · " + (ct.total != null ? ct.total + " tok" : "—")
    + " · " + Math.round(ct.seconds_running || 0) + "s"
    + (outs ? " · " + outs : "") + (r.stopped_reason ? " · " + r.stopped_reason : "");
}
function renderHistory(runs) { fill("history", (runs || []).slice().reverse().map(r => [fmtRun(r)])); }  // newest first
async function loadHistory() {  // history changes only at run end → a slow, independent poll
  try { const r = await fetch("/api/v1/history"); renderHistory(await r.json()); }
  catch (e) {}
}
function fallbackPoll() {                  // the ~1s degradation path — idempotent (never double-loops)
  if (fallbackPoll.armed) return;
  fallbackPoll.armed = true;
  setInterval(poll, 1000); poll();
}
// ---- per-ticket live drill-down -------------------------------------------------
// Each open ticket gets its OWN EventSource to /api/v1/ticket/<id>/stream and its own
// panel in #drill (a container the main render never rebuilds — so the panel survives
// the ~0.5s run-view re-renders). Every value is written via textContent (el()), so a
// tool summary / agent message can never be parsed as markup.
const drills = {};   // ticket_id -> { es, panel }
function fmtTel(t) {
  if (!t) return "";
  const tools = Object.keys(t.tools||{}).map(k => k + "×" + t.tools[k]).join(" ");
  return "turns " + (t.turns||0) + " · tool calls " + (t.tool_calls||0)
    + (tools ? " (" + tools + ")" : "") + " · " + fmtTokens(t.tokens);
}
function evtLine(e) {                       // [text, cssClass] for one event, kind-tagged
  const k = e.kind;
  if (k === "agent_message") return ["💬 " + (e.phase||"") + ": " + (e.text||""), "evt msg"];
  if (k === "tool_call") return ["🔧 " + (e.tool||"") + (e.summary ? " " + e.summary : ""), "evt tool"];
  if (k === "token_usage") return ["📊 " + fmtTokens(e.tokens), "evt tok"];
  if (k === "turn_started") return ["▶ turn started", "evt turn"];
  if (k === "turn_ended") return ["⏹ turn " + (e.status||""), "evt turn"];
  if (k === "truncated") return ["… " + (e.note||"truncated"), "evt tok"];
  return [k + (e.item_type ? " " + e.item_type : ""), "evt"];
}
function openDrill(tid) {
  if (!tid) return;
  if (drills[tid]) { drills[tid].panel.scrollIntoView({ block: "nearest" }); return; }
  const panel = el("div", null, "drill");
  const head = el("div", null, "drillhead");
  head.appendChild(el("span", "▾ " + tid, "tag"));
  head.appendChild(btn("close", () => closeDrill(tid)));
  const tel = el("div", "", "muted");
  const list = el("div", null, "");
  panel.appendChild(head); panel.appendChild(tel); panel.appendChild(list);
  $("drill").appendChild(panel);
  const render = (view) => {
    tel.textContent = fmtTel(view.telemetry);
    list.innerHTML = "";
    for (const e of (view.events||[])) {
      const [text, cls] = evtLine(e);
      list.appendChild(el("div", "[" + (e.seq != null ? e.seq : "") + "] " + text, cls));
    }
  };
  let es = null;
  const u = "/api/v1/ticket/" + encodeURIComponent(tid);
  if (window.EventSource) {
    es = new EventSource(u + "/stream");
    es.onmessage = (ev) => { try { render(JSON.parse(ev.data)); } catch (x) {} };
    es.onerror = () => {};   // EventSource auto-reconnects; the live detail is best-effort
  } else {
    fetch(u + "/events").then(r => r.json()).then(render).catch(() => {});  // no-SSE fallback
  }
  drills[tid] = { es, panel };
}
function closeDrill(tid) {
  const d = drills[tid]; if (!d) return;
  if (d.es) d.es.close();
  d.panel.remove();
  delete drills[tid];
}
function startStream() {
  // Prefer server-push (SSE): render each pushed view. Fall back to polling when the
  // stream can't deliver — BEFORE the first event, or after a sustained post-delivery
  // outage — so the surface never regresses to blank nor freezes on stale data (R4).
  if (!window.EventSource) { fallbackPoll(); return; }
  let delivered = false, outage = null;
  const es = new EventSource("/api/v1/stream");
  es.onmessage = (e) => {
    // mark delivered only AFTER a successful render — a malformed-only stream must not
    // suppress the fallback by looking healthy.
    try { render(JSON.parse(e.data)); delivered = true; if (outage) { clearTimeout(outage); outage = null; } }
    catch (x) {}                           // malformed frame → keep last view
  };
  es.onerror = () => {
    // never delivered → the stream can't hold: poll now (no blank surface).
    if (!delivered) { es.close(); fallbackPoll(); return; }
    // a drop after delivery: EventSource auto-reconnects, so flag staleness — but if it
    // can't recover within ~2 heartbeat windows, stop trusting it and poll (the safety net).
    $("updated").textContent = "· stream reconnecting…";
    if (!outage) outage = setTimeout(() => { es.close(); fallbackPoll(); }, 30000);
  };
}
startStream();
loadHistory(); setInterval(loadHistory, 10000);  // cross-run history (slow, independent of the live view)
</script></body></html>"""


def PAGE_html(token: str) -> str:
    """The served page with the per-server CSRF token injected into its
    `<meta name="director-token">`. The token is url-safe (`secrets.token_urlsafe`),
    so it is safe inside the attribute value (no quote/markup escaping needed)."""
    return PAGE.replace("__DIRECTOR_TOKEN__", token)


# The project-graph page (M2 spike). A SECOND, self-contained page (the flat-list `/`
# is untouched; M4 promotes this to `/`). It loads the vendored libs from the local
# /assets/* routes (offline — no CDN), fetches GET /api/v1/board, and renders the
# whole board as a layered DAG (dagre, rankDir LR — crossing-minimized; the server
# already computed the semantic layer=wave, this is the visual layout). A node tap
# opens a session overlay over the existing /api/v1/ticket/<id>/events route; a
# double-tap toggles a manual descendant-hide (DAG subtree collapse — cytoscape-
# expand-collapse is compound-only, the wrong tool, so collapse is hand-rolled).
# Every overlay value is written via textContent (producer text never parsed as markup).
GRAPH_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>director · project graph</title>
<style>
  html,body { margin:0; height:100%; background:#0e1116; color:#d6dde6; font:13px ui-monospace,Menlo,monospace; }
  #bar { position:absolute; top:0; left:0; right:0; height:2rem; padding:.3rem .8rem; box-sizing:border-box;
         border-bottom:1px solid #1b2230; display:flex; gap:.9rem; align-items:center; }
  #bar a { color:#9ecbff; text-decoration:none; }
  #status, .muted { color:#7d8896; }
  .legend span { margin-right:.5rem; }
  #cy { position:absolute; top:2.6rem; left:0; right:0; bottom:0; }
  #ov { position:absolute; right:1rem; top:3rem; width:24rem; max-height:72%; overflow:auto;
        background:#11161f; border:1px solid #2a3343; border-radius:.5rem; padding:.5rem .7rem; display:none; z-index:5; }
  #ov h3 { margin:.1rem 0 .4rem; font-size:13px; }
  #ov .evt { padding:.12rem 0; border-bottom:1px solid #161c26; white-space:pre-wrap; }
  #ov .x { float:right; cursor:pointer; color:#7d8896; }
</style></head><body>
<div id="bar">
  <strong>director · project graph</strong>
  <span id="status">loading…</span>
  <span class="legend"><span style="color:#6ee7a8">●done</span><span style="color:#9ecbff">●in&nbsp;progress</span><span style="color:#7d8896">●other</span><span style="color:#ff9b9b">●cycle</span></span>
  <a href="/">← flat view</a>
  <span class="muted">tap node = session · dbl-tap = collapse subtree</span>
</div>
<div id="cy"></div>
<div id="ov"><span class="x" onclick="document.getElementById('ov').style.display='none'">✕ close</span><h3 id="ovh"></h3><div id="ovb"></div></div>
<script src="/assets/cytoscape.min.js"></script>
<script src="/assets/dagre.min.js"></script>
<script src="/assets/cytoscape-dagre.js"></script>
<script>
try { if (window.cytoscapeDagre) cytoscape.use(window.cytoscapeDagre); } catch (e) {}
const $ = (id) => document.getElementById(id);
function nodeClass(n) {
  if (n.in_cycle) return 'cycle';
  const s = (n.state || '').toLowerCase();
  if (s.includes('done') || s.includes('complete')) return 'done';
  if (s.includes('progress') || s.includes('flight')) return 'prog';
  return 'other';
}
async function load() {
  let view;
  try { view = await (await fetch('/api/v1/board')).json(); }
  catch (e) { $('status').textContent = 'board fetch error: ' + e; return; }
  const nodes = view.nodes || [], edges = view.edges || [];
  if (!nodes.length) { $('status').textContent = 'no board snapshot yet'; return; }
  const els = [];
  for (const n of nodes) els.push({ data: { id: n.id, label: n.identifier || n.id,
      layer: n.layer, state: n.state }, classes: nodeClass(n) });
  for (const e of edges) els.push({ data: { id: e.from + '__' + e.to, source: e.from, target: e.to } });
  const cy = cytoscape({
    container: $('cy'), elements: els, wheelSensitivity: 0.2,
    style: [
      { selector: 'node', style: { 'label': 'data(label)', 'color': '#d6dde6', 'font-size': 10,
        'background-color': '#39414f', 'shape': 'round-rectangle', 'width': 'label', 'height': 16,
        'padding': '6px', 'text-valign': 'center', 'text-halign': 'center' } },
      { selector: 'node.done', style: { 'background-color': '#1f3d2c', 'border-color': '#6ee7a8', 'border-width': 1 } },
      { selector: 'node.prog', style: { 'background-color': '#16314d', 'border-color': '#9ecbff', 'border-width': 2 } },
      { selector: 'node.cycle', style: { 'border-color': '#ff9b9b', 'border-width': 2 } },
      { selector: 'node.collapsed', style: { 'border-style': 'dashed', 'border-color': '#e3b341', 'border-width': 2 } },
      { selector: 'edge', style: { 'width': 1, 'line-color': '#2a3343', 'target-arrow-color': '#2a3343',
        'target-arrow-shape': 'triangle', 'arrow-scale': .7, 'curve-style': 'bezier' } },
    ],
    layout: { name: 'dagre', rankDir: 'LR', nodeSep: 18, rankSep: 60 },
  });
  $('status').textContent = nodes.length + ' tickets · ' + edges.length + ' deps · '
    + (view.layers ? view.layers.length : 0) + ' waves';
  cy.on('tap', 'node', (ev) => openOverlay(ev.target));
  cy.on('dbltap', 'node', (ev) => toggleCollapse(ev.target));
  window.cy = cy;   // introspection hook (debug + behavioral test): window.cy.nodes(), emit('tap')
}
function toggleCollapse(node) {                       // manual DAG-subtree collapse (descendant-hide)
  const collapsed = node.hasClass('collapsed');
  node.successors('node').style('display', collapsed ? 'element' : 'none');
  node[collapsed ? 'removeClass' : 'addClass']('collapsed');
}
async function openOverlay(node) {
  const id = node.data('id');
  $('ov').style.display = 'block';
  $('ovh').textContent = node.data('label') + ' — ' + (node.data('state') || '');
  $('ovb').textContent = 'loading…';
  let v;
  try { v = await (await fetch('/api/v1/ticket/' + encodeURIComponent(id) + '/events')).json(); }
  catch (e) { $('ovb').textContent = 'events fetch error: ' + e; return; }
  $('ovb').textContent = '';
  const evs = v.events || [];
  if (!evs.length) { $('ovb').textContent = 'no session events recorded for this ticket'; return; }
  for (const e of evs) {
    const d = document.createElement('div'); d.className = 'evt';
    d.textContent = '[' + (e.seq != null ? e.seq : '') + '] ' + (e.kind || '')
      + (e.text ? ': ' + e.text : '') + (e.tool ? ' ' + e.tool : '');
    $('ovb').appendChild(d);
  }
}
load();
</script></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    """Thin shim over build_view. Two defined GET routes; everything else is an
    error envelope. status_dir/queue_dir come from the SERVER (set in serve), never
    from the request, so there is no request-derived filesystem path — zero traversal
    surface (spec R3/D-5)."""

    # HTTP/1.0: each request closes its connection — no keep-alive read-ahead to
    # mismanage; Content-Length is still sent. Simplicity over throughput (a human
    # polling ~1s does not need pipelining).
    protocol_version = "HTTP/1.0"

    def __getattr__(self, name):
        # Funnel EVERY do_<VERB> (GET/POST/PUT/…) into one dispatcher so an un-listed
        # method can't slip through as a 501 — _dispatch decides 404/405/serve.
        if name.startswith("do_"):
            return self._dispatch
        raise AttributeError(name)

    def log_message(self, format, *args):  # silence the default stderr access log
        pass

    def _dispatch(self):
        # Fail-soft boundary: a read-only observability surface must NEVER drop the
        # connection or dump a traceback to stderr (the silenced-log "quiet instrument"
        # posture). A polling tab that closes mid-write → drop quietly; any other handler
        # bug → a structured 500 the client JS already handles (catch → "fetch error").
        try:
            self._route()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return  # the polling browser went away mid-write — don't attempt a 2nd response
        except Exception:
            # Any other handler bug → a structured 500. The 500-send itself may hit a dead
            # socket (any OSError errno, not just EPIPE/ECONNRESET): swallow it — there is
            # no peer left to tell, and nothing may reach socketserver.handle_error (stderr).
            try:
                self._error(500, "internal error")
            except OSError:
                pass

    # route → allowed verbs. GET reads (unfenced); the one POST write is token-fenced.
    _ROUTES = {"/": {"GET"}, _STATE_PATH: {"GET"}, _STREAM_PATH: {"GET"},
               _HISTORY_PATH: {"GET"}, _BOARD_PATH: {"GET"}, _GRAPH_PATH: {"GET"},
               _ANSWER_PATH: {"POST"}}

    def _route(self):
        path = self.path.split("?", 1)[0]
        if path.startswith(_TICKET_PREFIX):       # dynamic per-ticket routes (sanitized below)
            return self._ticket_route(path)
        if path in _ASSETS:                        # fixed vendored-asset map (zero traversal)
            return self._asset(path)
        allowed = self._ROUTES.get(path)
        if allowed is None:
            return self._error(404, f"no such route: {path}")          # undefined → 404
        if self.command not in allowed:
            return self._error(405, f"method not allowed: {self.command}")  # wrong verb → 405
        if path == "/":
            return self._send(200, PAGE_html(self.server.token).encode("utf-8"),
                              "text/html; charset=utf-8")
        if path == _GRAPH_PATH:
            return self._send(200, GRAPH_PAGE.encode("utf-8"), "text/html; charset=utf-8")
        if path == _STATE_PATH:
            view = build_view(self.server.status_dir, self.server.queue_dir)
            return self._send(200, json.dumps(view).encode("utf-8"), "application/json")
        if path == _BOARD_PATH:
            snap = board_snapshot.read_board(base=self.server.board_dir) or {}
            nodes = snap.get("nodes", []) if isinstance(snap, dict) else []
            view = board_snapshot.build_board_view(nodes)
            return self._send(200, json.dumps(view).encode("utf-8"), "application/json")
        if path == _STREAM_PATH:
            return self._stream()
        if path == _HISTORY_PATH:
            runs = history.read_history(base=self.server.history_dir)
            return self._send(200, json.dumps(runs).encode("utf-8"), "application/json")
        return self._answer()  # _ANSWER_PATH + POST

    def _asset(self, path: str) -> None:
        """Serve one vendored, checked-in JS asset (R6). `path` is a key of the FIXED
        `_ASSETS` map (matched in `_route`), so the filename is a constant, never
        request-derived — zero traversal (invariant 3). GET-only; a missing file (a
        broken vendor checkout) is a 404, never a traceback (fail-soft)."""
        if self.command != "GET":
            return self._error(405, f"method not allowed: {self.command}")
        filename, ctype = _ASSETS[path]
        try:
            body = (_ASSETS_DIR / filename).read_bytes()
        except OSError:
            return self._error(404, f"asset not vendored: {filename}")
        return self._send(200, body, ctype)

    def _stream(self) -> None:
        """Server-push the view as SSE (R4): hold the connection open and emit a frame
        on each snapshot change (server-side change-detect over the same `build_view`),
        plus a heartbeat. NOT via `_send` — an event-stream sends no `Content-Length`;
        the connection stays open and the body is flushed frame-by-frame. Fail-soft per
        R14: `_stream_loop` swallows the client-disconnect errno family, so a closed tab
        just ends this (daemon) thread — never a crash, never stderr."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def write(chunk: bytes) -> None:
            self.wfile.write(chunk)
            self.wfile.flush()

        _stream_loop(write,
                     lambda: build_view(self.server.status_dir, self.server.queue_dir),
                     sleep=time.sleep, now=time.monotonic,
                     should_run=self.server.serving.is_set,  # ends promptly on shutdown()
                     heartbeat_s=_STREAM_HEARTBEAT_S, poll_s=_STREAM_POLL_S)

    def _ticket_route(self, path: str) -> None:
        """Dispatch GET /api/v1/ticket/<id>/(events|stream). The <id> is the ONLY
        request-derived component and is sanitized to `[A-Za-z0-9._-]+` before any path
        join (R5: no separator / `..` can escape `events_dir`); `events_dir` itself comes
        from the SERVER. Reads only — no fence (like the other GET routes)."""
        if self.command != "GET":
            return self._error(405, f"method not allowed: {self.command}")
        parts = path[len(_TICKET_PREFIX):].split("/")    # ["<id>", "events"|"stream"] — exactly 2
        if len(parts) != 2 or parts[1] not in ("events", "stream"):
            return self._error(404, f"no such route: {path}")
        sid = ticket_events.sanitize_id(parts[0])
        if sid is None:
            return self._error(404, "invalid ticket id")
        return self._ticket_events(sid) if parts[1] == "events" else self._ticket_stream(sid)

    def _ticket_view(self, sid: str) -> dict:
        """The per-ticket drill-down view: the bounded event log + its derived telemetry
        (R3/R4). Pure read over `events_dir`; tolerant (read_events never raises)."""
        events = ticket_events.read_events(sid, base=self.server.events_dir)
        return {"ticket_id": sid, "events": events,
                "telemetry": ticket_events.derive_timeseries(events), "count": len(events)}

    def _ticket_events(self, sid: str) -> None:
        return self._send(200, json.dumps(self._ticket_view(sid)).encode("utf-8"), "application/json")

    def _ticket_stream(self, sid: str) -> None:
        """SSE tail of one ticket's event view — pushes a frame whenever the log grows
        (the same `_stream_loop` change-detect + heartbeat + fail-soft as the run stream)."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def write(chunk: bytes) -> None:
            self.wfile.write(chunk)
            self.wfile.flush()

        _stream_loop(write, lambda: self._ticket_view(sid),
                     sleep=time.sleep, now=time.monotonic,
                     should_run=self.server.serving.is_set,
                     heartbeat_s=_STREAM_HEARTBEAT_S, poll_s=_STREAM_POLL_S)

    def _answer(self) -> None:
        """Resolve one pending Director-queue request from the browser (R1/R2). Fenced
        (R5), idempotent (R6), and validated against the downstream writer's contract
        before any write — a bad body is a 400, never a queued-but-unconsumable answer."""
        if not self._authorized():
            return self._error(403, "forbidden: missing/invalid token or non-local origin")
        body = self._read_json_body()
        if body is None:
            return self._error(400, "malformed or missing JSON body")
        request_id, kind = body.get("request_id"), body.get("kind")
        if not isinstance(request_id, str) or not isinstance(kind, str):
            return self._error(400, "request_id and kind are required strings")
        qbase = self.server.queue_dir
        # Locate the still-pending request (R6): read_pending excludes answered ones, so
        # "not pending" means either already-answered (409) or unknown (404).
        try:
            pending = dq.read_pending(base=qbase)
        except (OSError, ValueError, KeyError):
            pending = []
        req = next((r for r in pending if r.get("request_id") == request_id), None)
        if req is None:
            if dq.read_answer(request_id, base=qbase) is not None:
                return self._error(409, "already answered")
            return self._error(404, f"no pending request: {request_id}")
        if req.get("kind") != kind:
            return self._error(400, f"kind mismatch: queued {req.get('kind')!r}")
        if kind not in HUMAN_BOUND_KINDS:
            return self._error(409, f"kind not answerable from console: {kind!r}")
        ok, detail = self._dispatch_answer(kind, request_id, body, req, qbase)
        if not ok:
            return self._error(400, detail)
        return self._send(200, json.dumps({"written": True, "request_id": request_id,
                                           "kind": kind, "detail": detail}).encode("utf-8"),
                          "application/json")

    def _dispatch_answer(self, kind, request_id, body, req, qbase):
        """Route one validated answer to its canonical director_min writer; returns
        (ok, detail). `answered_by="console"` records the operator-surface in the audit."""
        if kind == "turnReview":
            disp = body.get("disposition")
            err = _validate_disposition(disp)
            if err:
                return False, err
            dm.answer_turn(request_id, disp, base=qbase, answered_by="console")
            return True, f"disposition {disp.get('kind')}"
        if kind in ("commandApproval", "fileChange"):
            decision = body.get("decision")
            if decision not in dq.APPROVAL_DECISIONS:
                return False, f"decision must be one of {list(dq.APPROVAL_DECISIONS)}"
            dm.answer(request_id, decision, base=qbase, answered_by="console")
            return True, f"decision {decision}"
        if kind in ("userInput", "elicitation"):
            answers = body.get("answers")
            if not isinstance(answers, dict):
                return False, "answers must be an object"
            dm.answer(request_id, answers=answers, base=qbase, answered_by="console")
            return True, "answers recorded"
        if kind == "mergeReview":
            action, note = body.get("action"), body.get("note") or ""
            if action == "requeue":
                res = dm.requeue_merge(req, note=note, base=qbase, answered_by="console")
                # requeue_merge REFUSES at max_attempts / already_queued and leaves the
                # review OPEN — never report that no-op as a written success (review fix).
                if not res.get("requeued"):
                    return False, (f"requeue refused: {res.get('reason')} "
                                   f"(attempt {res.get('attempt')}) — review left open")
                return True, f"requeued at attempt {res.get('attempt')}"
            if action in ("abandon", "human"):
                dm.answer_merge_review(request_id, {"action": action, "note": note},
                                       base=qbase, answered_by="console")
                return True, f"merge {action}"
            return False, "action must be requeue|abandon|human"
        return False, f"unsupported kind: {kind!r}"  # defensive; HUMAN_BOUND_KINDS gates above

    def _authorized(self) -> bool:
        """Write fence (R5): the per-server CSRF token (constant-time compare) AND a
        loopback Host (and Origin, when the browser sends one). GET routes never call
        this — reads are unfenced."""
        tok = self.headers.get("X-Director-Token")
        if not tok or not secrets.compare_digest(tok, self.server.token):
            return False
        if not _host_is_local(self.headers.get("Host")):
            return False
        origin = self.headers.get("Origin")
        return origin is None or _host_is_local(origin)

    def _read_json_body(self):
        """The POST body as a dict, or None for any malformed/absent/over-typed body."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            return None
        if length <= 0:
            return None
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, code: int, message: str) -> None:
        body = json.dumps({"error": {"code": code, "message": message}}).encode("utf-8")
        self._send(code, body, "application/json")


class _DashboardServer(ThreadingHTTPServer):
    """Carries the status/queue dirs the handler reads from (set once at construction,
    never per-request) — an explicit field instead of a monkey-attribute."""

    def __init__(self, addr, handler, *, status_dir=None, queue_dir=None,
                 history_dir=None, events_dir=None, board_dir=None, token=None):
        super().__init__(addr, handler)
        self.status_dir = status_dir
        self.queue_dir = queue_dir
        self.history_dir = history_dir   # the cross-run history store the /api/v1/history route reads
        self.events_dir = events_dir     # the per-ticket session-event store the /api/v1/ticket/* routes read
        self.board_dir = board_dir       # the whole-board snapshot store the /api/v1/board route reads
        # Per-server CSRF token: minted once, embedded in the served page, required on
        # every write (POST). A foreign page in the browser cannot read it (same-origin)
        # so cannot forge a write to localhost. `token=` is injectable for tests.
        self.token = token or secrets.token_urlsafe(32)
        # Server-liveness flag the SSE stream loop polls (`should_run`): an in-process
        # `shutdown()` clears it so quiet/idle streams end at their next tick (≤ poll_s)
        # instead of lingering until the next failed write — clean teardown (review P2).
        self.serving = threading.Event()
        self.serving.set()

    def shutdown(self) -> None:
        self.serving.clear()   # signal open SSE streams to stop, then stop the accept loop
        super().shutdown()


def serve(port: int = _DEFAULT_PORT, status_dir=None, queue_dir=None,
          history_dir=None, events_dir=None, board_dir=None) -> _DashboardServer:
    """Bind a read-only dashboard server on 127.0.0.1 (LAN never exposed, D-5). A bind
    failure (e.g. port in use) propagates immediately — no retry loop. Caller runs
    serve_forever(); tests bind port 0 and drive it over urllib."""
    return _DashboardServer(("127.0.0.1", port), _Handler, status_dir=status_dir,
                            queue_dir=queue_dir, history_dir=history_dir, events_dir=events_dir,
                            board_dir=board_dir)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="director.dashboard",
        description="Live read-only web view of a Director run (127.0.0.1).")
    ap.add_argument("--port", type=int, default=_DEFAULT_PORT, help="bind port (default 8787)")
    ap.add_argument("--status-dir", default=None, help="status dir override")
    ap.add_argument("--queue-dir", default=None, help="queue dir override")
    ap.add_argument("--history-dir", default=None, help="cross-run history dir override")
    ap.add_argument("--events-dir", default=None, help="per-ticket session-event dir override")
    ap.add_argument("--board-dir", default=None, help="whole-board snapshot dir override")
    args = ap.parse_args(argv)
    httpd = serve(args.port, args.status_dir, args.queue_dir, args.history_dir, args.events_dir,
                  args.board_dir)
    host, port = httpd.server_address[0], httpd.server_address[1]
    print(f"director.dashboard: http://{host}:{port}/  (read-only; Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
