"""Director request/answer queue (Phase 1, M1).

A worker that hits a Codex app-server approval/input request writes one *request*
here and blocks for an *answer*; the Director (the main Claude session) writes the
answer; the worker resumes the SAME turn. Idempotent + atomic, mirroring the
harness reliability rules (docs/RELIABILITY.md): requests dedupe by request_id
(R1/R4 at-least-once), answers are written temp-then-rename (R9 atomic
mark-before-act). Self-contained — no import of plugin/ machinery, so the host app
stays decoupled from the portable harness (core-belief: internalize dependencies).

Schemas (see the product-spec Design section):
  request : {request_id, ticket_id, session_id "<thread>-<turn>", kind, payload,
             workspace_path, created_at}
  answer  : {request_id, decision | answers, answered_by, answered_at}
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path

# Serializes append_request's read-dedupe + write so N concurrent workers
# (orchestrator threads) can't interleave a JSON line or both win the dedupe race.
# Single-process scope — cross-process hardening (O_APPEND/flock) is Phase 4.
_APPEND_LOCK = threading.Lock()

# Normalized request kinds (Codex method -> kind mapping lives in the worker seam).
REQUEST_KINDS = ("commandApproval", "fileChange", "userInput", "elicitation")

# Decisions the Director may return for an approval-style request.
APPROVAL_DECISIONS = ("accept", "decline", "acceptForSession", "cancel")


def _root(base: Path | str | None = None) -> Path:
    """Queue root. Explicit `base` wins (tests); else $DIRECTOR_QUEUE_DIR; else the
    already-gitignored default under .claude/harness/."""
    if base is not None:
        return Path(base)
    env = os.environ.get("DIRECTOR_QUEUE_DIR")
    if env:
        return Path(env)
    return Path(".claude/harness/director-queue")


def _requests_path(root: Path) -> Path:
    return root / "requests.jsonl"


def _answers_dir(root: Path) -> Path:
    return root / "answers"


def _ensure(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _answers_dir(root).mkdir(parents=True, exist_ok=True)


def read_requests(base: Path | str | None = None) -> list[dict]:
    """All requests in append order. Tolerates a missing/empty queue file."""
    p = _requests_path(_root(base))
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def append_request(req: dict, base: Path | str | None = None) -> bool:
    """Append one request as a JSON line. Idempotent by request_id.

    Returns True if newly written, False if a request with this request_id is
    already queued (at-least-once dedupe — re-delivering the same request is safe).
    """
    root = _root(base)
    _ensure(root)
    rid = req["request_id"]
    # Hold the lock across dedupe-read + append (not across wait_for_answer, which
    # is a separate call) so concurrent appends neither interleave a line nor both
    # pass the dedupe check for the same request_id.
    with _APPEND_LOCK:
        if any(r.get("request_id") == rid for r in read_requests(base)):
            return False
        line = json.dumps(req, ensure_ascii=False, sort_keys=True)
        with open(_requests_path(root), "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
    return True


def write_answer(answer: dict, base: Path | str | None = None) -> None:
    """Atomically write answers/<request_id>.json (temp file + os.replace = R9)."""
    root = _root(base)
    _ensure(root)
    rid = answer["request_id"]
    dst = _answers_dir(root) / f"{rid}.json"
    fd, tmp = tempfile.mkstemp(dir=str(_answers_dir(root)), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(answer, f, ensure_ascii=False, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def read_answer(request_id: str, base: Path | str | None = None) -> dict | None:
    """The answer for one request, or None if not answered yet."""
    p = _answers_dir(_root(base)) / f"{request_id}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def read_pending(base: Path | str | None = None) -> list[dict]:
    """Requests that have no answer yet (what the Director must act on)."""
    return [r for r in read_requests(base)
            if read_answer(r["request_id"], base) is None]


def wait_for_answer(request_id: str, base: Path | str | None = None,
                    timeout_s: float = 300.0, poll_s: float = 0.2) -> dict | None:
    """Block until answers/<request_id>.json appears, or return None at timeout.

    The worker calls this after queueing a request; on None it applies the safe
    default (decline) so a turn never hangs forever (plan R7).
    """
    deadline = time.monotonic() + timeout_s
    while True:
        ans = read_answer(request_id, base)
        if ans is not None:
            return ans
        if time.monotonic() >= deadline:
            return None
        time.sleep(poll_s)
