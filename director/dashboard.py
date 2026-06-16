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

import datetime

import director.queue as dq
from director import status

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
