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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import director.queue as dq
from director import status

# The single versioned, read-only data route (Symphony §13.7 alignment).
_STATE_PATH = "/api/v1/state"
_DEFAULT_PORT = 8787

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
    except (OSError, ValueError):  # ValueError covers json.JSONDecodeError (torn line)
        return []


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


# The whole client: one self-contained HTML string (CSS + vanilla JS poller), no
# framework, no bundler, no external asset — offline-OK (stdlib-only grain). It polls
# GET /api/v1/state ~1s and re-renders the DOM. Every data value is written via
# textContent (never innerHTML), so producer text can never be parsed as markup.
PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>director dashboard</title>
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
</style></head><body>
<h1>director dashboard <span id="updated" class="muted"></span></h1>
<div id="run" class="run"></div>
<div id="counts" class="muted"></div>
<h2>in-flight</h2><div id="inflight"></div>
<h2>stuck</h2><div id="stuck"></div>
<h2>recent</h2><div id="recent"></div>
<h2>pending (director queue)</h2><div id="pending"></div>
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
function fill(id, lines) {
  const box = $(id); box.innerHTML = "";
  if (!lines.length) { box.appendChild(el("div", "—", "muted")); return; }
  for (const [text, cls] of lines) box.appendChild(el("div", text, cls || "item"));
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
    if (run.rate_limits) h.appendChild(el("span", "rate " + JSON.stringify(run.rate_limits), "tag"));
  }
  const c = v.counts || {};
  $("counts").textContent = "in-flight " + (c.in_flight||0) + " · stuck " + (c.stuck||0)
    + " · recent " + (c.recent||0) + " · pending " + (c.pending||0);
  fill("inflight", (v.in_flight||[]).map(e =>
    [(e.identifier||e.ticket_id) + " · " + e.phase + " · a" + e.attempt + "/w" + e.wave]));
  fill("stuck", (v.stuck||[]).map(s =>
    [s.ticket + " ← " + (s.blocked_by||[]).map(b => b.id).join(", ")]));
  fill("recent", (v.recent||[]).map(r =>
    [(r.status === "completed" ? "✓ " : "✗ ") + (r.ticket||r.ticket_id)
      + " · " + fmtTokens(r.tokens) + (r.session_id ? " · " + r.session_id : ""),
     r.status === "completed" ? "item ok" : "item bad"]));
  fill("pending", (v.pending||[]).map(p =>
    [p.kind + " · " + (p.ticket_id||"") + (p.summary ? " · " + p.summary : "")]));
  $("updated").textContent = "· updated " + (v.generated_at || "");
}
async function poll() {
  try { const r = await fetch("/api/v1/state"); render(await r.json()); }
  catch (e) { $("updated").textContent = "· fetch error: " + e; }
}
setInterval(poll, 1000); poll();
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
        except (BrokenPipeError, ConnectionResetError):
            return  # the polling browser went away mid-write — nothing to report
        except Exception:
            try:
                self._error(500, "internal error")
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _route(self):
        path = self.path.split("?", 1)[0]
        if path not in ("/", _STATE_PATH):
            return self._error(404, f"no such route: {path}")  # undefined → 404
        if self.command != "GET":
            return self._error(405, f"method not allowed: {self.command}")  # defined+wrong verb → 405
        if path == "/":
            return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        view = build_view(self.server.status_dir, self.server.queue_dir)
        return self._send(200, json.dumps(view).encode("utf-8"), "application/json")

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

    def __init__(self, addr, handler, *, status_dir=None, queue_dir=None):
        super().__init__(addr, handler)
        self.status_dir = status_dir
        self.queue_dir = queue_dir


def serve(port: int = _DEFAULT_PORT, status_dir=None, queue_dir=None) -> _DashboardServer:
    """Bind a read-only dashboard server on 127.0.0.1 (LAN never exposed, D-5). A bind
    failure (e.g. port in use) propagates immediately — no retry loop. Caller runs
    serve_forever(); tests bind port 0 and drive it over urllib."""
    return _DashboardServer(("127.0.0.1", port), _Handler,
                            status_dir=status_dir, queue_dir=queue_dir)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="director.dashboard",
        description="Live read-only web view of a Director run (127.0.0.1).")
    ap.add_argument("--port", type=int, default=_DEFAULT_PORT, help="bind port (default 8787)")
    ap.add_argument("--status-dir", default=None, help="status dir override")
    ap.add_argument("--queue-dir", default=None, help="queue dir override")
    args = ap.parse_args(argv)
    httpd = serve(args.port, args.status_dir, args.queue_dir)
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
