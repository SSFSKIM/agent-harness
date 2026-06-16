"""Director orchestration status surface (Phase 4 slice 2).

The orchestrator (`director/orchestrator.py`) computes rich run state — which
tickets are in flight, their attempt/wave, what is stuck and why, recent terminal
outcomes — but Phase 2/3 only printed it to stdout and forgot it. This module
PERSISTS that state as a single ATOMIC snapshot the Director (the main Claude
session) reads to judge a queued request *in context*: the judge is the inline
Director, not a headless process (D-5/D-30). What separates a mechanical answer
from a taste escalation is exactly this picture — which wave/attempt a ticket is
on, what else is running, whether the run is stuck.

Design owner: docs/product-specs/2026-06-15-director-orchestration-visibility.md
(R1-R5, D-32/D-34). Read-only local files: no network, no human key, no new live
exec surface (R9). Mirrors the queue's atomic-write grain (temp + os.replace,
RELIABILITY R9) so a reader NEVER sees a torn snapshot.

Snapshot schema (.claude/harness/director-status/status.json):
  {
    "run":       {"started_at", "pass", "stopped_reason",
                  "codex_totals": {"input", "output", "total", "seconds_running"},
                  "rate_limits"},                          # Symphony-grade telemetry
    "in_flight": [{"ticket_id", "identifier", "phase", "attempt", "wave", "started_at"}],
    "recent":    [{"ticket_id", "ticket", "status", "final_state", "attempts", "turns",
                   "tokens": {"input","output","total"}|None, "session_id", "last_message"}],  # bounded
    "stuck":     [{"ticket", "blocked_by": [{"id", "state_type"}]}],
    "updated_at"
  }
"""
from __future__ import annotations

import datetime
import json
import os
import tempfile
from pathlib import Path
from typing import Callable

# Bound on the recent-outcomes tail: enough for oversee/reporting, not a history
# store (cross-run analytics is a non-goal). Override per StatusWriter.
RECENT_MAX = 20


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _elapsed(start_iso, now_iso) -> float:
    """Seconds between two ISO-8601 timestamps, clamped at 0; 0.0 if either is
    unparseable. Best-effort by contract — runtime accounting is instrumentation,
    so a malformed timestamp yields 0, never an exception (telemetry never a gate)."""
    try:
        delta = (datetime.datetime.fromisoformat(now_iso)
                 - datetime.datetime.fromisoformat(start_iso)).total_seconds()
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, delta)


def _root(base: Path | str | None = None) -> Path:
    """Status root. Explicit `base` wins (tests); else $DIRECTOR_STATUS_DIR; else a
    sibling of the queue under .claude/harness/ (already gitignored). Kept separate
    from the queue dir so the Phase-1 queue contract stays untouched (D-34)."""
    if base is not None:
        return Path(base)
    env = os.environ.get("DIRECTOR_STATUS_DIR")
    if env:
        return Path(env)
    return Path(".claude/harness/director-status")


def _status_path(root: Path) -> Path:
    return root / "status.json"


def _ticket_key(ticket: dict) -> str:
    return str(ticket["id"])


def _ticket_label(ticket: dict) -> str:
    return str(ticket.get("identifier") or ticket["id"])


class StatusWriter:
    """Accumulates orchestration transitions into an in-memory model and rewrites
    the snapshot atomically on each one. The orchestrator drives it from its MAIN
    thread (workers run in a ThreadPool, but claim/reconcile callbacks execute in
    the `wait(... FIRST_COMPLETED)` loop), so the model needs no lock.

    Best-effort: a write failure is swallowed (recorded via `last_error`) so a
    flaky disk can never block dispatch — visibility is read-only instrumentation,
    never a gate (R3)."""

    def __init__(self, base: Path | str | None = None, *,
                 recent_max: int = RECENT_MAX, now: Callable[[], str] = _utcnow):
        self._root = _root(base)
        self._recent_max = recent_max
        self._now = now
        self._run: dict = {"started_at": None, "pass": 0, "stopped_reason": None}
        self._in_flight: dict[str, dict] = {}
        self._recent: list[dict] = []
        self._stuck: list[dict] = []
        # Run-level telemetry aggregate (Symphony §4.1.8/§13.5): cumulative tokens
        # across terminated tickets, the wall-clock seconds of ENDED tickets (active
        # tickets' elapsed is added live at snapshot), and the latest rate-limit
        # payload seen. Each ticket contributes its absolute total once at terminal,
        # so the sum never double-counts (drive already kept the per-ticket latest).
        self._codex_totals: dict = {"input": 0, "output": 0, "total": 0}
        self._seconds_ended: float = 0.0
        self._rate_limits = None
        self.last_error: str | None = None

    # -- transitions (called by the orchestrator) ----------------------------
    def claimed(self, ticket: dict, *, wave: int, attempt: int) -> None:
        if self._run["started_at"] is None:
            self._run["started_at"] = self._now()
        key = _ticket_key(ticket)
        self._in_flight[key] = {"ticket_id": key, "identifier": _ticket_label(ticket),
                                "phase": "claimed", "attempt": attempt, "wave": wave,
                                "started_at": self._now()}
        self._flush()

    def dispatched(self, ticket: dict) -> None:
        # "running" = submitted to the worker pool; under pool saturation the worker
        # may still be queued (benign — the Director treats it as in-flight either way).
        self._set_phase(_ticket_key(ticket), "running")

    def retrying(self, ticket: dict, *, attempt: int) -> None:
        key = _ticket_key(ticket)
        entry = self._in_flight.get(key)
        if entry is not None:
            entry["attempt"] = attempt
            entry["phase"] = "retrying"
        self._flush()

    def terminal(self, ticket: dict, summary: dict) -> None:
        key = _ticket_key(ticket)
        entry = self._in_flight.pop(key, None)
        # Per-ticket telemetry (plan M3), folded into the summary by reconcile. The
        # recent row carries the ticket's final tokens/session/last_message; the run
        # aggregate accumulates tokens (summed once per ticket — no double-count),
        # the latest rate-limit payload, and this ticket's wall-clock seconds.
        tel = summary.get("telemetry") or {}
        tokens = tel.get("tokens")
        if isinstance(tokens, dict):
            for k in ("input", "output", "total"):
                v = tokens.get(k)
                if isinstance(v, int) and not isinstance(v, bool):
                    self._codex_totals[k] += v
        if tel.get("rate_limits") is not None:
            self._rate_limits = tel["rate_limits"]
        if entry is not None:
            self._seconds_ended += _elapsed(entry.get("started_at"), self._now())
        self._recent.append({"ticket_id": key, "ticket": summary.get("ticket"),
                             "status": summary.get("status"),
                             "final_state": summary.get("final_state"),
                             "attempts": summary.get("attempts"),
                             "turns": summary.get("turns"),  # R8: multi-turn visibility
                             "tokens": tokens,
                             "session_id": tel.get("session_id"),
                             "last_message": tel.get("last_message")})
        if len(self._recent) > self._recent_max:
            self._recent = self._recent[-self._recent_max:]
        self._flush()

    def wave(self, pass_no: int) -> None:
        # Run start = first wave (every run_once/run_until_drained calls wave() before any
        # claim), so even a no-claim run (e.g. stuck-from-start, all blockers unmet) gets a
        # non-None `started_at` — a stable run identity. Without it, two distinct no-claim
        # runs share (None, stopped_reason) and a downstream dedupe (director.watch runReport)
        # would swallow the second — losing a real "human needed to unblock" pull (review fix).
        if self._run["started_at"] is None:
            self._run["started_at"] = self._now()
        self._run["pass"] = pass_no
        self._flush()

    def stuck(self, items: list[dict]) -> None:
        self._stuck = list(items)
        self._flush()

    def finished(self, stopped_reason: str | None) -> None:
        self._run["stopped_reason"] = stopped_reason
        self._flush()

    # -- internals -----------------------------------------------------------
    def _set_phase(self, key: str, phase: str) -> None:
        entry = self._in_flight.get(key)
        if entry is not None:
            entry["phase"] = phase
        self._flush()

    def snapshot(self) -> dict:
        now = self._now()
        # seconds_running is a LIVE aggregate at snapshot time (Symphony §13.5): the
        # cumulative seconds of ended tickets plus each in-flight ticket's elapsed —
        # no background ticking needed.
        active = sum(_elapsed(e.get("started_at"), now)
                     for e in self._in_flight.values())
        run = dict(self._run)
        run["codex_totals"] = {**self._codex_totals,
                               "seconds_running": round(self._seconds_ended + active, 3)}
        run["rate_limits"] = self._rate_limits
        return {"run": run,
                "in_flight": list(self._in_flight.values()),
                "recent": list(self._recent),
                "stuck": list(self._stuck),
                "updated_at": now}

    def _flush(self) -> None:
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(self._root), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.snapshot(), f, ensure_ascii=False, sort_keys=True)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, _status_path(self._root))
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
        except Exception as exc:  # best-effort: visibility NEVER blocks dispatch (R3).
            # Broad on purpose — a disk hiccup (OSError) OR an unexpected serialize
            # failure (json.dump TypeError/ValueError) is recorded, never raised, so
            # no status write can sink a run. The hard boundary is the guardrail, not
            # this read-only instrument.
            self.last_error = str(exc)


class NoopStatusWriter:
    """Records nothing — the default for library calls and tests, so orchestration
    is byte-identical when visibility is off (R3). Any transition method is a no-op."""

    last_error = None

    def __getattr__(self, _name):
        return lambda *a, **k: None


def read_status(base: Path | str | None = None) -> dict | None:
    """The current snapshot, or None if there is no run yet / it is unreadable.
    Tolerant by contract (R4): a missing file (no run) and an unparseable file both
    yield None rather than raising — the Director treats "no orchestration info" as
    part of the picture."""
    p = _status_path(_root(base))
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def context_for(request: dict, base: Path | str | None = None) -> dict:
    """Join a queued request to its ticket's orchestration entry (R5) — the read
    side of the "context injector". Wraps a bare request with the situational
    picture the Director needs to judge it in context, without fattening the queue
    request schema (the snapshot is the single source of truth, D-34):

      {ticket, siblings_in_flight, recent_for_ticket, run, stuck}

    `ticket` is None when nothing matches (run not started, or the ticket already
    terminated) — a legitimate state the Director reads as-is."""
    snap = read_status(base) or {}
    in_flight = snap.get("in_flight", [])
    tid = str(request.get("ticket_id")) if request.get("ticket_id") is not None else None
    ticket = next((e for e in in_flight if e.get("ticket_id") == tid), None)
    siblings = [e for e in in_flight if e.get("ticket_id") != tid]
    recent_for_ticket = [r for r in snap.get("recent", []) if r.get("ticket_id") == tid]
    return {"ticket": ticket,
            "siblings_in_flight": siblings,
            "recent_for_ticket": recent_for_ticket,
            "run": snap.get("run") or {},  # safe default (R4): no run → {}, not None
            "stuck": snap.get("stuck", [])}


def main(argv=None) -> int:
    """Read surface for the Director (the main Claude session, per
    docs/DIRECTOR.md): with no args, dump the current snapshot; with
    --request <json>, print the orchestration context joined to that queue request
    (`context_for`). Read-only — never mutates anything (R6/R9)."""
    import argparse

    ap = argparse.ArgumentParser(
        prog="director.status",
        description="Read the orchestration status the Director judges requests against.")
    ap.add_argument("--request",
                    help="a JSON queue request to join (context_for); omit to dump the snapshot")
    ap.add_argument("--status-dir", default=None, help="status dir override")
    args = ap.parse_args(argv)
    if args.request:
        out = context_for(json.loads(args.request), base=args.status_dir)
    else:
        out = read_status(base=args.status_dir)
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
