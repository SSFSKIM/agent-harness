"""Director cross-run history — a durable, append-only log of completed runs.

`director/status.py` persists the CURRENT run as a single atomic snapshot (overwritten
each run); the moment a run ends, that picture is gone. This module remembers a compact
SUMMARY of each completed run (its token totals, duration, stopped-reason, and outcome
counts) so the dashboard can show trends ACROSS runs — cost/throughput over time — not
only the run in flight (Phase B of the observability-polish spec, R7-R8).

Design owner: docs/product-specs/2026-06-18-observability-polish.md (R7-R8 + Design §D).
A metrics log, not an atomic snapshot — so APPEND-only JSONL (a torn final line from a
crash mid-append is tolerated on read), not temp+os.replace. Best-effort by contract
(R12 / D-6): a write failure is swallowed and a torn/absent read degrades to `[]` —
history is instrumentation, NEVER a gate on a run (the same posture as `StatusWriter._flush`).

stdlib-only, explicit `base=` override (the `director/` host-runtime invariants).

Store: <root>/runs.jsonl, one JSON record per line:
  {started_at, ended_at, stopped_reason, passes,
   codex_totals:{input,output,total,seconds_running}, ticket_count, outcomes:{<status>:count}}
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# Bound on the history tail a reader returns — enough for a trend glance, not an analytics
# store (rotation/retention is a non-goal; a record is tiny and the read is bounded).
RECENT_RUNS_MAX = 50


def _root(base: Path | str | None = None) -> Path:
    """History root. Explicit `base` wins (tests); else $DIRECTOR_HISTORY_DIR; else a
    sibling of the status/queue dirs under .claude/harness/ (already gitignored)."""
    if base is not None:
        return Path(base)
    env = os.environ.get("DIRECTOR_HISTORY_DIR")
    if env:
        return Path(env)
    return Path(".claude/harness/director-history")


def _runs_path(root: Path) -> Path:
    return root / "runs.jsonl"


def summarize(snapshot, *, ended_at=None) -> dict:
    """A compact run-summary record from a final status snapshot — PURE (no IO).

    The run-level aggregate (`codex_totals`, `seconds_running`, `stopped_reason`,
    `passes`, `started_at`) is exact. Outcome COUNTS are tallied from the snapshot's
    `recent` tail, so for a run with more than `status.RECENT_MAX` terminal tickets the
    per-status counts under-count (the cost/duration headline stays exact) — a known,
    documented limit acceptable for a metrics log. Tolerant: a None/empty/garbage
    snapshot yields a well-formed record with zeros/None, never raises (R12)."""
    snap = snapshot if isinstance(snapshot, dict) else {}
    run = snap.get("run")
    run = run if isinstance(run, dict) else {}
    recent = snap.get("recent")
    recent = recent if isinstance(recent, list) else []
    outcomes: dict = {}
    for r in recent:
        status = r.get("status") if isinstance(r, dict) else None
        if status:
            outcomes[status] = outcomes.get(status, 0) + 1
    ct = run.get("codex_totals")
    ct = ct if isinstance(ct, dict) else {}
    return {
        "started_at": run.get("started_at"),
        "ended_at": ended_at if ended_at is not None else snap.get("updated_at"),
        "stopped_reason": run.get("stopped_reason"),
        "passes": run.get("pass"),
        "codex_totals": {k: ct.get(k) for k in ("input", "output", "total", "seconds_running")},
        "ticket_count": len(recent),
        "outcomes": outcomes,
    }


def append_run(record: dict, base: Path | str | None = None) -> None:
    """Append one run-summary record to the history log. Best-effort (D-6): any failure
    (un-writable dir, non-serializable record) is swallowed — a history write must NEVER
    sink a run. Append (open "a") is crash-safe enough for a metrics log; a torn final
    line is tolerated by `read_history`, so no temp+replace is needed."""
    try:
        root = _root(base)
        root.mkdir(parents=True, exist_ok=True)
        with open(_runs_path(root), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass  # instrumentation, never a gate (mirrors StatusWriter._flush)


def read_history(base: Path | str | None = None, limit: int = RECENT_RUNS_MAX) -> list[dict]:
    """The last `limit` run records, oldest-first. Tolerant by contract (R12): a missing
    file (no runs yet) → `[]`; a torn/partial line (crash mid-append) is SKIPPED rather
    than raising; an unreadable file → `[]`. The dashboard reads this as part of the
    picture, never a gate."""
    p = _runs_path(_root(base))
    if not p.exists():
        return []
    out: list[dict] = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue  # torn/partial line — skip, never raise
        if isinstance(rec, dict):
            out.append(rec)
    return out[-limit:] if limit and limit > 0 else out


def main(argv=None) -> int:
    """Read surface: dump the recent run history as JSON (read-only)."""
    import argparse

    ap = argparse.ArgumentParser(prog="director.history",
                                 description="Read the cross-run history (recent run summaries).")
    ap.add_argument("--history-dir", default=None, help="history dir override")
    ap.add_argument("--limit", type=int, default=RECENT_RUNS_MAX, help="how many recent runs")
    args = ap.parse_args(argv)
    print(json.dumps(read_history(base=args.history_dir, limit=args.limit),
                     ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
