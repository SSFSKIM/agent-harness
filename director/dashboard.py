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
        parts = [str(p[k]) for k in ("result", "reason", "pr", "branch") if p.get(k)]
        return _clip(" ".join(parts))
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
    snap = status.read_status(base=status_dir) or {}
    in_flight = snap.get("in_flight", [])
    stuck = snap.get("stuck", [])
    recent = snap.get("recent", [])
    pending = [_summarize_request(r) for r in dq.read_pending(base=queue_dir)]
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


# Replaced by the full inline page in M3; a minimal stub keeps the GET / route honest.
PAGE = "<!doctype html><meta charset='utf-8'><title>director dashboard</title>"


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
