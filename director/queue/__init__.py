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

import datetime
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

# Normalized request kinds. Approval/input kinds come from a Codex server request
# (mapping lives in the worker seam); `turnReview` is a turn-end the watched Director
# answers free-form (multi-turn slice — director.decider.make_queue_decider);
# `mergeRequest` is a worklist item (not a question) the serialized PR-merger drains —
# it has no blocking author; the merger writes an answer only to mark it CONSUMED.
# `mergeReview` is the merger→Director escalation surface (R6/R7): a PR that could not
# cleanly land posts one so the live Director picks it up (single human surface — the
# merger never contacts the human directly). (worker-qa-and-serialized-pr-merge.)
REQUEST_KINDS = ("commandApproval", "fileChange", "userInput", "elicitation",
                 "turnReview", "mergeRequest", "mergeReview")

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


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def append_merge_request(ticket_id: str, *, pr=None, branch=None,
                         workspace_path: str | None = None,
                         self_description: str | None = None,
                         guidance: str | None = None, attempt: int = 1,
                         evidence: dict | None = None,
                         preservation_override: bool = False,
                         created_at: str | None = None,
                         base: Path | str | None = None) -> bool:
    """Enqueue a PR-merge worklist item for the serialized merger to drain.

    A worker that finished a ticket and opened a PR posts this (attempt 1); the merger
    pops it, runs the `land` lane, and writes an answer to mark it consumed. The
    `preservation_override` (merge-preservation R1/D3) is the Director's explicit approval,
    on an approve-and-requeue, that a tripwire-flagged drop is acceptable — the merger's
    finalize stage then SKIPS the preservation tripwire for this attempt (it still runs the
    hygiene gate). False on a worker's first enqueue.

    request_id is `merge|<ticket_id>|a<attempt>` — the `attempt` discriminant lets the
    Director RE-ENQUEUE a failed merge (attempt 2+) under a fresh id without the
    one-open-per-ticket dedupe swallowing it (the re-enqueue loop), while a re-delivery
    of the SAME attempt still dedupes (at-least-once, R1/R4). `guidance` is the Director's
    directive for a guided retry (None on the first enqueue) — the merger renders it into
    the land prompt. `evidence` is the worker's optional PR-feedback-sweep result
    (merge-preservation R4) — advisory audit data the merger records and compares against
    what it independently verifies; never trusted in place of verification (D5). Returns
    True if newly queued, False if already present."""
    return append_request({
        "request_id": f"merge|{ticket_id}|a{attempt}",
        "ticket_id": ticket_id,
        "session_id": f"{ticket_id}-merge-a{attempt}",
        "kind": "mergeRequest",
        "payload": {"pr": pr, "branch": branch, "self_description": self_description,
                    "guidance": guidance, "attempt": attempt, "evidence": evidence,
                    "preservation_override": preservation_override},
        "workspace_path": workspace_path,
        "created_at": created_at or _now_iso(),
    }, base=base)


def append_merge_review(ticket_id: str, *, pr=None, branch=None, result: str,
                        reason: str | None = None, disposition: dict | None = None,
                        workspace_path: str | None = None, attempt: int = 1,
                        created_at: str | None = None,
                        base: Path | str | None = None) -> bool:
    """Surface a PR that could not cleanly land to the Director (R6/R7).

    The serialized merger posts this when a merge attempt ends non-`merged`
    (escalated/failed). The live Director reads it (director_min.merge_reviews),
    decides — give a directive / re-enqueue / escalate the taste to the human — and
    answers it (director_min.answer_merge_review / requeue_merge). It is the merger's
    ONLY escalation channel: there is no merger→human path (single human surface, R7).
    request_id is `mergereview|<ticket_id>|a<attempt>`: one open escalation PER ATTEMPT
    (so a 2nd failed retry surfaces distinctly instead of being deduped away), while a
    re-delivery of the same attempt's escalation still dedupes. `attempt` rides the
    payload so the Director's requeue can bump it (`requeue_merge`)."""
    return append_request({
        "request_id": f"mergereview|{ticket_id}|a{attempt}",
        "ticket_id": ticket_id,
        "session_id": f"{ticket_id}-mergereview-a{attempt}",
        "kind": "mergeReview",
        "payload": {"pr": pr, "branch": branch, "result": result,
                    "reason": reason, "disposition": disposition, "attempt": attempt},
        "workspace_path": workspace_path,
        "created_at": created_at or _now_iso(),
    }, base=base)


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


# -- Parked-ticket set (restart-safety, gap #2) ------------------------------
# A durable set of ticket ids the orchestrator PARKED in `started` (an `escalate`, or a
# `blocked` left in `started` because no blocked board-state is configured). Startup
# orphan-reattach reads it to SKIP re-readying a parked ticket — it is parked-for-human,
# not a crash orphan — so a daemon restart never re-runs a parked worker (which could
# duplicate its already-filed children). Stored as a JSON id list; atomic temp+replace
# under the same `_APPEND_LOCK` as `append_request`, so the read-modify-write never races.

def _parked_path(root: Path) -> Path:
    return root / "parked.json"


def read_parked(base: Path | str | None = None) -> set[str]:
    """The parked ticket-id set. Empty on a missing/corrupt file — fail-open to 'nothing
    parked' (i.e. today's re-ready-all recovery), never a crash."""
    p = _parked_path(_root(base))
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def _write_parked(ids: set[str], root: Path) -> None:
    _ensure(root)
    fd, tmp = tempfile.mkstemp(dir=str(root), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(sorted(ids), f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, _parked_path(root))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def append_parked(tid: str, base: Path | str | None = None) -> None:
    """Record `tid` as parked-in-`started`. Idempotent; atomic under the append lock."""
    root = _root(base)
    with _APPEND_LOCK:
        ids = read_parked(base)
        if tid not in ids:
            ids.add(tid)
            _write_parked(ids, root)


def clear_parked(tid: str, base: Path | str | None = None) -> None:
    """Drop `tid` from the parked set — called when the ticket is re-claimed (a fresh
    attempt that must be orphan-recoverable again). No-op when absent."""
    root = _root(base)
    with _APPEND_LOCK:
        ids = read_parked(base)
        if tid in ids:
            ids.discard(tid)
            _write_parked(ids, root)


def gc_parked(keep: set[str], base: Path | str | None = None) -> set[str]:
    """Intersect the parked set with `keep` (the tids still in `started`) and persist —
    dropping entries for tickets that have since LEFT `started` (a human re-readied/moved
    them). Returns the kept set. Run once at startup recovery to keep the set honest."""
    root = _root(base)
    with _APPEND_LOCK:
        ids = read_parked(base) & set(keep)
        _write_parked(ids, root)
    return ids


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
