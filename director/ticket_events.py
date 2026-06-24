"""Per-ticket session-event stream (Phase 5 observability).

`director/status.py` answers "what is the run doing in aggregate, and how did each
ticket end?"; this module answers the missing question — "what is *this* ticket's
worker doing right now, step by step?". Every worker turn (codex AND the claude
adapter) streams JSON-RPC notifications through `AppServerClient.on_event`
(`director/worker/app_server.py`); today the orchestrator taps that firehose ONLY
to siphon off token usage (`_enqueue_usage`) and drops the rest. This module
NORMALIZES the play-by-play (turn lifecycle, agent messages, tool calls, token
accrual) into a per-ticket append-only JSONL the dashboard tails — exactly as
`status.json`/`runs.jsonl` already bridge the orchestrator and the (separate)
dashboard process.

Design owner: docs/product-specs/2026-06-24-per-ticket-session-event-stream.md
(R1-R7). Built per docs/exec-plans/active/2026-06-24-per-ticket-session-event-stream.md.

Key property (R2): each `<ticket_id>.jsonl` is SINGLE-WRITER — `on_event` for a
given ticket only ever fires on that ticket's own dispatch thread, and a retry runs
only after the prior attempt's future reaped — so the writer appends DIRECTLY from
the worker-pool thread with no main-thread marshal (contrast `StatusWriter`, which
must marshal because all tickets share one model). Best-effort by contract (R3): a
write failure is swallowed (`last_error`), a torn/absent read degrades to `[]` — a
session-event write NEVER gates dispatch (the `history.py`/`StatusWriter._flush`
posture).

Store: <root>/<ticket_id>.jsonl, one normalized record per line:
  {seq, ts, kind, ...kind-specific}, kind ∈
    turn_started   {turn_id}
    agent_message  {phase, text}              # phase ∈ commentary|final_answer
    tool_call      {tool, summary}            # name + CLIPPED summary, never full I/O
    token_usage    {tokens:{input,output,total}}
    turn_ended     {turn_id, status}          # status ∈ completed|failed|cancelled
    item           {item_type, summary}       # forward-compat fallback (unknown item)
    truncated      {note}                     # one-time soft-cap sentinel
"""
from __future__ import annotations

import datetime
import json
import os
import re
from pathlib import Path

from director.worker import app_server

# Bound on the read tail (glance-able, not an analytics store — rotation is a non-goal,
# mirroring history.RECENT_RUNS_MAX) and a soft cap on per-file growth (a pathological
# multi-hour ticket can't grow unbounded; beyond it one sentinel is written, then nothing).
READ_MAX = 500
WRITE_SOFT_CAP = 5000
# Clip lengths: agent-message text is the play-by-play a human READS (generous); a tool
# summary is a glance at WHAT was called, never full output/I/O (spec non-goal — tight).
TEXT_CLIP = 2000
SUMMARY_CLIP = 200

# Filesystem-safe ticket-id charset. A request-derived id is matched against this BEFORE
# any path join, so it can never carry a separator / `..` and escape the events dir (R5).
_SAFE_ID = re.compile(r"\A[A-Za-z0-9._-]+\Z")

# Notifications we deliberately DROP (R1 curated taxonomy): streaming deltas (the
# completed item carries the full text) and `item/started` placeholders.
_DROP_METHODS = ("item/agentMessage/delta", "item/started")

# Non-agentMessage item types we treat as a tool call. `dynamicToolCall` = the claude
# adapter's broker shape (worker-runtime app-server); the rest = codex exec items. An
# UNKNOWN type still surfaces (as kind="item") — forward-compatible, the version-pinning
# discipline of `agent_message_text`/`extract_usage`.
_KNOWN_TOOL_TYPES = ("dynamicToolCall", "commandExecution", "fileChange",
                     "command_execution", "file_change", "mcpToolCall", "toolCall")


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _clip(value, limit: int = TEXT_CLIP) -> str:
    """A safe, clipped string from anything (None → "")."""
    return str(value if value is not None else "")[:limit]


def sanitize_id(ticket_id) -> str | None:
    """A filesystem-safe ticket-id segment, or None if it cannot be one. Rejects
    empty, `.`, `..` (which the charset alone would admit), and anything with a path
    separator or a char outside `[A-Za-z0-9._-]` — so a request-derived id can never
    escape the events dir (R5: the dashboard's zero-traversal posture)."""
    s = str(ticket_id) if ticket_id is not None else ""
    if s in ("", ".", "..") or _SAFE_ID.match(s) is None:
        return None
    return s


def _turn_id(params: dict):
    turn = params.get("turn")
    return turn.get("id") if isinstance(turn, dict) else None


def _tool_fields(item: dict) -> tuple[str, str]:
    """`(tool_name, clipped_summary)` from a tool/exec item, tolerant. The summary is
    a glance at WHAT ran (command / arguments / a content snippet), NEVER full output —
    clipped to SUMMARY_CLIP (spec non-goal: no full tool I/O capture)."""
    name = item.get("tool") or item.get("name") or item.get("type") or ""
    cmd = item.get("command")
    if isinstance(cmd, list):
        summary = " ".join(str(x) for x in cmd)
    elif cmd:
        summary = cmd
    elif item.get("arguments") is not None:
        summary = json.dumps(item.get("arguments"), ensure_ascii=False, default=str)
    else:
        summary = item.get("summary") or _first_content_text(item) or ""
    return _clip(name, 120), _clip(summary, SUMMARY_CLIP)


def _first_content_text(item: dict) -> str:
    items = item.get("contentItems")
    if isinstance(items, list):
        for c in items:
            if isinstance(c, dict) and isinstance(c.get("text"), str):
                return c["text"]
    return ""


def normalize_event(method, params, *, seq=None, now=_utcnow) -> dict | None:
    """Map one raw turn-stream notification to a small runtime-agnostic record, or
    None to DROP it (R1). Pure (the `now`/`seq` are injected). Reuses the producer's
    `agent_message_text`/`extract_usage` so the vocabulary stays pinned in one place.
    The SAME function normalizes a codex AND a claude notification (R7) — both adapters
    emit the identical method/item vocabulary."""
    if not isinstance(method, str):
        return None
    params = params if isinstance(params, dict) else {}
    base: dict = {"ts": now()}
    if seq is not None:
        base["seq"] = seq

    if method == "turn/started":
        return {**base, "kind": "turn_started", "turn_id": _turn_id(params)}
    if method in ("turn/completed", "turn/failed", "turn/cancelled"):
        return {**base, "kind": "turn_ended", "turn_id": _turn_id(params),
                "status": method.split("/", 1)[1]}

    usage = app_server.extract_usage(method, params)
    if usage is not None:
        return {**base, "kind": "token_usage", "tokens": usage}

    if method in _DROP_METHODS:
        return None

    if method == "item/completed":
        am = app_server.agent_message_text(params)
        if am is not None:
            text, phase = am
            if not text:                       # the item/started placeholder text — drop
                return None
            return {**base, "kind": "agent_message", "phase": phase, "text": _clip(text)}
        item = params.get("item")
        if isinstance(item, dict):
            itype = item.get("type")
            tool, summary = _tool_fields(item)
            if itype in _KNOWN_TOOL_TYPES:
                return {**base, "kind": "tool_call", "tool": tool, "summary": summary}
            return {**base, "kind": "item", "item_type": _clip(itype, 120), "summary": summary}
    return None


def _elapsed_iso(start_iso, end_iso):
    """Seconds between two ISO-8601 timestamps (clamped ≥0), or None if either is
    missing/unparseable — telemetry is best-effort, so a bad timestamp drops that one
    duration rather than raising (the `status._elapsed` posture)."""
    try:
        secs = (datetime.datetime.fromisoformat(end_iso)
                - datetime.datetime.fromisoformat(start_iso)).total_seconds()
    except (TypeError, ValueError):
        return None
    return round(max(0.0, secs), 3)


def derive_timeseries(events) -> dict:
    """Per-ticket telemetry derived from the event log (R4) — PURE, no IO. The token
    timeseries (`token_series`) is the cumulative total at each `token_usage` point;
    `tokens` is the latest cumulative; `tools` counts tool calls by name; `turns`
    counts `turn_started`; `turn_durations` is the per-turn wall-clock derived from each
    `turn_started`→`turn_ended` pair's `ts` (a duration drops to None if a timestamp is
    unparseable). Tolerant: a None/garbage list yields a well-formed zero record, never
    raises."""
    events = events if isinstance(events, list) else []
    token_series: list[dict] = []
    tools: dict[str, int] = {}
    turns = 0
    last = {"input": 0, "output": 0, "total": 0}
    turn_durations: list[dict] = []
    open_turn = None     # (turn_id, ts) of the last turn_started awaiting its turn_ended
    for e in events:
        if not isinstance(e, dict):
            continue
        kind = e.get("kind")
        if kind == "token_usage":
            t = e.get("tokens")
            if isinstance(t, dict):
                last = {k: t.get(k, last.get(k, 0)) for k in ("input", "output", "total")}
                token_series.append({"seq": e.get("seq"), "ts": e.get("ts"), **last})
        elif kind == "tool_call":
            name = e.get("tool") or "tool"
            tools[name] = tools.get(name, 0) + 1
        elif kind == "turn_started":
            turns += 1
            open_turn = (e.get("turn_id"), e.get("ts"))
        elif kind == "turn_ended":
            if open_turn is not None:
                turn_durations.append({"turn_id": open_turn[0], "status": e.get("status"),
                                       "seconds": _elapsed_iso(open_turn[1], e.get("ts"))})
                open_turn = None
    return {"turns": turns, "tool_calls": sum(tools.values()), "tools": tools,
            "tokens": last, "token_series": token_series, "turn_durations": turn_durations}


def _root(base: Path | str | None = None) -> Path:
    """Events root. Explicit `base` wins (tests); else $DIRECTOR_EVENTS_DIR; else a
    sibling of the status/queue/history dirs under .claude/harness/ (already gitignored)."""
    if base is not None:
        return Path(base)
    env = os.environ.get("DIRECTOR_EVENTS_DIR")
    if env:
        return Path(env)
    return Path(".claude/harness/director-events")


def _events_path(root: Path, sid: str) -> Path:
    return root / f"{sid}.jsonl"


class TicketEventWriter:
    """Append normalized turn-stream events to a per-ticket JSONL (best-effort, R2/R3).

    Single-writer per file (one ticket → one dispatch thread at a time; retries are
    serialized), so it appends DIRECTLY from the worker-pool thread — no main-thread
    marshal. `seq` is monotonic per ticket, SEEDED from the existing line count so it
    survives a process restart. A write failure is swallowed (`last_error`), never
    raised — instrumentation never gates dispatch."""

    def __init__(self, base: Path | str | None = None, *,
                 soft_cap: int = WRITE_SOFT_CAP, now=_utcnow):
        self._root = _root(base)
        self._soft_cap = soft_cap
        self._now = now
        self._seq: dict[str, int] = {}      # sid -> next seq (== records written so far)
        self._truncated: set[str] = set()   # sids that already wrote the soft-cap sentinel
        self.last_error: str | None = None

    def record(self, ticket_id, method, params) -> None:
        """Normalize one raw notification and append it, if it survives the taxonomy.
        A dropped notification (normalize_event → None) consumes no `seq`. Tolerant of
        a bad `ticket_id` (sanitize → None → no-op) and any IO/serialize hiccup."""
        sid = sanitize_id(ticket_id)
        if sid is None:
            return
        try:
            if sid not in self._seq:
                self._seq[sid] = self._count_existing(sid)
            if self._seq[sid] >= self._soft_cap:
                self._maybe_truncate(sid)
                return
            ev = normalize_event(method, params, seq=self._seq[sid], now=self._now)
            if ev is None:
                return                       # dropped — do not advance seq
            self._append(sid, ev)
            self._seq[sid] += 1
        except Exception as exc:             # best-effort: a session-event write never gates dispatch
            self.last_error = str(exc)

    def _maybe_truncate(self, sid: str) -> None:
        if sid in self._truncated:
            return
        self._truncated.add(sid)
        self._append(sid, {"seq": self._seq[sid], "ts": self._now(), "kind": "truncated",
                           "note": f"soft cap {self._soft_cap} reached — further events dropped"})

    def _count_existing(self, sid: str) -> int:
        p = _events_path(self._root, sid)
        if not p.exists():
            return 0
        try:
            return sum(1 for _ in p.read_bytes().decode("utf-8", "ignore").splitlines() if _.strip())
        except OSError:
            return 0

    def _append(self, sid: str, ev: dict) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        with open(_events_path(self._root, sid), "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False, sort_keys=True) + "\n")


class NoopTicketEventWriter:
    """Records nothing — the default when the layer is off (library calls / tests), so
    orchestration is byte-identical (the `NoopStatusWriter` precedent)."""

    last_error = None

    def record(self, *a, **k) -> None:
        return None


def read_events(ticket_id, base: Path | str | None = None, limit: int = READ_MAX) -> list[dict]:
    """The last `limit` normalized records for a ticket, oldest-first (R3). Tolerant by
    contract: a bad id → `[]`; a missing file → `[]`; a torn/partial line (crash
    mid-append) is SKIPPED; an unreadable file → `[]`. Never raises."""
    sid = sanitize_id(ticket_id)
    if sid is None:
        return []
    p = _events_path(_root(base), sid)
    if not p.exists():
        return []
    try:
        lines = p.read_bytes().decode("utf-8", "ignore").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out[-limit:] if limit and limit > 0 else out


def main(argv=None) -> int:
    """Read surface: dump one ticket's events + derived telemetry as JSON (read-only)."""
    import argparse

    ap = argparse.ArgumentParser(prog="director.ticket_events",
                                 description="Read one ticket's session-event log + derived telemetry.")
    ap.add_argument("ticket_id")
    ap.add_argument("--events-dir", default=None, help="events dir override")
    ap.add_argument("--limit", type=int, default=READ_MAX)
    args = ap.parse_args(argv)
    events = read_events(args.ticket_id, base=args.events_dir, limit=args.limit)
    out = {"ticket_id": args.ticket_id, "events": events,
           "telemetry": derive_timeseries(events), "count": len(events)}
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
