"""Serialized PR-merger (worker-qa-and-serialized-pr-merge slice, D-47/D-50/D-53).

A worker finishes a ticket, self-QAs, and opens a PR (it does NOT merge). The PR
lands here: a SINGLE consumer drains the `mergeRequest` queue one PR at a time —
rebase onto the latest main, run the integration gate, squash-merge when GREEN.
Serialization is the whole point (R3): "clean against a stale main" is not safe, so
PRs must land sequentially, each re-based + re-gated against the main the previous
merge produced. A single consumer draining one-at-a-time gives that for free — no
lock, no concurrency counter in the hot path.

The merger does NOT invent a turn machine: each PR runs through `director.run.drive`
with the vendored `land` skill, and the per-turn disposition is owned by the injected
`decide` (D-50) — exactly the seam the worker driver uses. A clean landing returns a
`terminal(done)` disposition; a conflict it cannot resolve, a red integration gate, or
a taste call surfaces as `escalate`/`stuck`/`failed`, which the merger routes to the
human VIA the Director (single surface, R4/R7) — it never silently merges.

This module owns the drain + classification. The Director-escalation wiring and the
worker→enqueue call site are M3; the live serializer wire-pin is M4.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import os
import sys
import time
from typing import Callable

import director.queue as dq
from director import config, run
from director.decider import autonomous_decide, make_queue_decider
from director.worker import autonomy

MERGE_REQUEST_KIND = "mergeRequest"

# Safety bound on one drain pass (mirrors the orchestrator's max_dispatched): a drain
# should terminate because every item is consumed, but this guards a processing path
# that somehow fails to consume from spinning forever. Value owned by
# config.DEFAULTS["merger"]["max_merges"] (single source); a host overrides via
# .harness.json director.merger.max_merges (merger.main resolves the live value).
DEFAULT_MAX_MERGES = config.DEFAULTS["merger"]["max_merges"]

_LAND_PROMPT = """\
You are the PR-MERGER landing ONE pull request. Follow the `land` skill exactly:
locate the PR for this branch, REBASE it onto the latest `main`, run the full
integration gate (`python3 plugin/scripts/check.py` / the host gate) against that
rebased state, resolve any conflicts the `land` skill can cleanly resolve, and
squash-merge ONLY when the gate is GREEN. Land exactly this one PR — do not touch
others.

Do NOT force a merge. If you hit a conflict you cannot cleanly resolve, the
integration gate goes red and you cannot fix it within scope, or a product/taste
judgment is needed, STOP and surface it: report_outcome(status="needs_human",
reason="…") (or end your turn explaining). The work is already done and the ticket
is closed — a bad merge is worse than a delayed one.

PR to land:
  pr: {pr}
  branch: {branch}
The author's PR self-description (what was built, which reviews/tests they ran):
{self_description}{guidance}"""

# Appended only on a guided retry (attempt 2+): the Director's directive from the
# mergeReview the previous attempt raised. Rendered by land_prompt when present.
_GUIDANCE_BLOCK = """

DIRECTOR GUIDANCE (this is retry attempt {attempt} — a previous attempt escalated, and the
Director answered with this directive; follow it):
{guidance}"""


def land_prompt(payload: dict) -> str:
    """The land-lane prompt for one PR, framed from the merge request's payload. On a
    guided retry the Director's `guidance` (from `requeue_merge`) is rendered in so the
    land agent follows the directive that resolved the prior escalation."""
    payload = payload or {}
    guidance = (payload.get("guidance") or "").strip()
    guidance_block = _GUIDANCE_BLOCK.format(
        attempt=payload.get("attempt", 1), guidance=guidance) if guidance else ""
    return _LAND_PROMPT.format(
        pr=payload.get("pr") or "(see current branch)",
        branch=payload.get("branch") or "(current branch)",
        self_description=(payload.get("self_description") or "(none provided)").strip(),
        guidance=guidance_block,
    )


def land_ticket_from_request(req: dict) -> dict:
    """Build the synthetic 'ticket' the land lane drives for one merge request. It
    reuses the worker's own workspace (where the PR branch + git checkout already
    live), so the `land` skill operates on the real branch."""
    return {
        "id": f"merge-{req.get('ticket_id')}",
        "prompt": land_prompt(req.get("payload") or {}),
        "workspace": req.get("workspace_path"),
    }


def classify(disp: dict) -> str:
    """Map a land-lane drive disposition to a merge result.

    Only a clean `terminal(done)` is a merge; everything else (a non-done terminal, an
    escalate, a max-turns stuck, or a failed turn) needs the human's attention and is
    surfaced — the merger never quietly drops a PR (R4)."""
    kind = (disp or {}).get("kind")
    if kind == "terminal" and (disp.get("outcome") or {}).get("status") == "done":
        return "merged"
    if kind == "failed":
        return "failed"
    return "escalated"


def pending_merges(base=None) -> list[dict]:
    """Queued, not-yet-consumed merge requests in FIFO (append) order. FIFO + 'rebase
    onto latest main each time' is the ordering policy (spec Open Q): a sibling that
    hasn't landed yet simply makes the integration gate fail → escalate, not corruption."""
    return [r for r in dq.read_pending(base=base) if r.get("kind") == MERGE_REQUEST_KIND]


# A ticket's merge runs through at most `max_attempts` (config default 3) attempts before
# the Director abandons; 20 is an ample belt-and-suspenders scan bound (merge-gated-eligibility).
_MERGE_ATTEMPT_SCAN = 20


def merge_outcome(ticket_id, *, base=None) -> str:
    """Where a ticket's PR-merge stands, read from the queue (merge-gated-eligibility R3) —
    the signal the orchestrator's merge sweep uses to finalize `merging`→`done` WITHOUT the
    merger ever writing the board (it stays board-free; the queue is the hand-off).

      - "landed"     — no `merge|<tid>|*` is still pending AND the latest answered attempt
                       was `merge_result == "merged"` (the PR is on main).
      - "pending"    — a `merge|<tid>|aN` is still queued (in flight / awaiting the merger).
      - "unresolved" — escalated / abandoned / failed with no successful land and nothing
                       pending; also the (shouldn't-happen) no-record case.

    Reads `dq.read_pending` (in-flight) + `dq.read_answer("merge|<tid>|aN")` across attempts
    (a requeue bumps the attempt — `_consume` writes `merge_result` on each). The
    highest-numbered answered attempt is authoritative."""
    for r in dq.read_pending(base=base):
        if r.get("kind") == MERGE_REQUEST_KIND and r.get("ticket_id") == ticket_id:
            return "pending"
    latest = None
    for n in range(1, _MERGE_ATTEMPT_SCAN + 1):
        ans = dq.read_answer(f"merge|{ticket_id}|a{n}", base=base)
        if ans is not None:
            latest = ans  # keep the highest-attempt answer
    if latest is None:
        return "unresolved"
    return "landed" if latest.get("merge_result") == "merged" else "unresolved"


@contextlib.contextmanager
def _single_consumer_lock(base):
    """Enforce R4's *single* PR-merger across processes (completion-gate review fix).

    `drain` reads pending → drives `pend[0]` → consumes; the queue's atomicity covers
    append/write but NOT this read-then-drive window, so two concurrent drains could pick
    the SAME PR and merge it twice — exactly the concurrent-main thrash a merge QUEUE
    exists to prevent (D-47). An exclusive, non-blocking `flock` makes single-consumer an
    enforced invariant, not an assumption: a second concurrent drain fails loud. The lock
    is held only for the drain and auto-releases on close / process death (crash-safe,
    unlike a pidfile). flock is per open-file-description (BSD/Linux), so this also trips
    a second drain inside one process."""
    root = dq._root(base)
    root.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(root / "merger.lock"), os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError(
                f"another PR-merger is already draining {root} — refusing a second "
                f"concurrent drain (single-consumer, R4)")
        yield
    finally:
        os.close(fd)  # releases the flock


def _consume(req: dict, result: str, *, base=None, now=dq._now_iso) -> None:
    """Mark a merge request CONSUMED by writing its answer (removes it from pending).
    Always called after processing — including on escalate/failed — so the drain loop
    makes progress and never re-processes the same PR (the no-infinite-loop guarantee).
    A non-merged result is also SURFACED to the Director (_surface_escalation)."""
    dq.write_answer({"request_id": req["request_id"], "answered_by": "merger",
                     "answered_at": now(), "merge_result": result}, base=base)


def _surface_escalation(req: dict, result: dict, *, base=None) -> bool:
    """If a PR did not cleanly merge, escalate it to the Director by posting a
    `mergeReview` to the SAME queue (R6) — the merger's ONLY escalation channel, never
    a direct line to the human (R7). Returns whether it surfaced (merged → False).

    Fire-and-forget on purpose: the merger surfaces and moves on (the serial queue keeps
    flowing); the Director acts on the mergeReview asynchronously (directive / re-enqueue
    / human). The PR stays UNMERGED — surfacing is never a silent merge (R6)."""
    if result.get("result") == "merged":
        return False
    disp = result.get("disposition") or {}
    payload = req.get("payload") or {}
    reason = disp.get("reason") or result.get("error") or disp.get("kind") or "merge failed"
    # Carry the attempt (default 1) into the mergeReview: the review id discriminates per
    # attempt (a 2nd failed retry surfaces distinctly) and the Director's requeue reads it
    # to bump attempt+1. Return the ACTUAL append result — a dedup means nothing NEW
    # surfaced, so don't claim it did.
    return dq.append_merge_review(
        req.get("ticket_id"), pr=payload.get("pr"), branch=payload.get("branch"),
        result=result["result"], reason=reason, disposition=disp,
        workspace_path=req.get("workspace_path"), attempt=payload.get("attempt", 1),
        base=base)


def process_request(req: dict, *, driver: Callable = run.drive,
                    decide: Callable = autonomous_decide, **drive_kwargs) -> dict:
    """Run ONE merge request through the land lane and classify the outcome. A driver
    crash becomes a `failed` result (one bad PR never sinks the drain) — mirrors the
    orchestrator's dispatch-wraps-drive discipline."""
    ticket = land_ticket_from_request(req)
    try:
        disp = driver(ticket, decide=decide, **drive_kwargs)
    except Exception as exc:
        return {"request_id": req["request_id"], "ticket_id": req.get("ticket_id"),
                "result": "failed", "error": str(exc)}
    return {"request_id": req["request_id"], "ticket_id": req.get("ticket_id"),
            "result": classify(disp), "disposition": disp}


def drain(*, base=None, driver: Callable = run.drive, decide: Callable = autonomous_decide,
          max_merges: int = DEFAULT_MAX_MERGES, **drive_kwargs) -> list[dict]:
    """Drain the merge queue SERIALLY: pop the oldest pending PR, land it, mark it
    consumed, repeat — strictly one PR in flight at a time (R3). Returns a per-PR result
    list ({request_id, ticket_id, result: merged|escalated|failed, ...}).

    Single-consumer ⇒ serialization is structural (this loop processes one request fully
    before reading the next), so there is no concurrency to guard. The loop terminates
    because each iteration consumes one request (it leaves `pending`); `max_merges` is a
    belt-and-suspenders bound. `drive_kwargs` (command, queue_base, workspace_root,
    install_skills, posture, …) pass straight through to the land lane."""
    results: list[dict] = []
    processed = 0
    with _single_consumer_lock(base):  # enforce single PR-merger (R4) before any drive
        while processed < max_merges:
            pend = pending_merges(base=base)
            if not pend:
                break
            req = pend[0]  # FIFO — oldest queued PR first
            result = process_request(req, driver=driver, decide=decide, **drive_kwargs)
            # Surface BEFORE consume (review fix): if surfacing a non-merged PR fails or the
            # process dies between the two, the request stays PENDING and is re-surfaced
            # next drain (mergeReview dedupes on mergereview|<ticket>) — a failed merge is
            # never silently dropped (R6). Consuming first would lose the escalation.
            result["escalated_to_director"] = _surface_escalation(req, result, base=base)
            _consume(req, result["result"], base=base)
            results.append(result)
            processed += 1
    return results


def run_loop(*, base=None, command, poll: float = 1.0, once: bool = False,
             decide: Callable = autonomous_decide, max_merges: int = DEFAULT_MAX_MERGES,
             **drive_kwargs) -> int:
    """The standalone merger's body: drain the merge queue, then either exit (`once`) or
    keep watching for new PRs (the drain-runner; spec Open Q resolved to a standalone,
    event-woken process — D-47/R7). `once` runs a single drain pass and returns (cron /
    tests). Otherwise it polls the queue and drains whenever a `mergeRequest` is pending,
    sleeping `poll` between checks — woken by work, never a busy-spin. `max_merges` bounds
    one drain pass (config `director.merger.max_merges`). Returns 0."""
    while True:
        if pending_merges(base=base):  # only take the flock + drive when there is work
            drain(base=base, command=command, decide=decide, max_merges=max_merges,
                  **drive_kwargs)
        if once:
            return 0
        time.sleep(poll)


def select_decider(*, autonomous: bool, mock: bool, queue_base=None,
                   turn_review_timeout: float = 300.0):
    """The land lane's turn-end decider (mirrors orchestrator.main, R9/D-50). WATCHED is
    the default: land-lane turn-ends (a conflict/taste question mid-merge) route to the
    Director as `turnReview`, exactly like a worker's — the Director answers free-form.
    `--autonomous` (un-watched) or `--mock` (no live Director to answer) use the code
    decider, which self-resolves and escalates only terminal needs_human (→ mergeReview)."""
    if autonomous or mock:
        return autonomous_decide
    return make_queue_decider(base=queue_base, timeout_s=turn_review_timeout)


def _command(args, codex_command, posture) -> list[str]:
    if args.mock:
        return [sys.executable, run._MOCK, args.mock_scenario]
    # Real land agent: the resolved worker posture (auto_review + network, a host may
    # tighten it), wrapped in non-login bash (run._command has the env-boundary
    # rationale, SECURITY T11).
    return ["bash", "-c", autonomy.codex_command(codex_command,
                                                 auto_review=posture.auto_review,
                                                 network=posture.network)]


def main(argv=None) -> int:
    """`python3 -m director.merger` — the single serialized PR-merger process. Drains the
    `mergeRequest` queue one PR at a time (the `flock` makes it the enforced sole consumer,
    R4); escalations surface to the Director as `mergeReview` (R6/R7). It is a SEPARATE
    component from the Director (which owns the human surface), per the design."""
    ap = argparse.ArgumentParser(prog="director.merger")
    ap.add_argument("--once", action="store_true",
                    help="drain currently-pending PRs then exit (cron / tests)")
    ap.add_argument("--poll", type=float, default=None, help="loop poll interval (s)")
    ap.add_argument("--queue-dir", default=None, help="Director queue dir override")
    ap.add_argument("--codex", default=None, help="real land-agent command")
    ap.add_argument("--mock", action="store_true", help="use the bundled fake app-server")
    ap.add_argument("--mock-scenario", default="report",
                    choices=["plain", "approval", "approval_done", "report",
                             "tool", "turn_failed"])
    ap.add_argument("--autonomous", action="store_true",
                    help="no-agent: self-resolve land-lane turn-ends with the code decider — "
                         "the --mock/CI/truly-detached niche (no judging agent). Default routes "
                         "turn-ends to the Director (a human-attended session OR a lights-out "
                         "daemon — same queue path, DIRECTOR.md §6); R9")
    ap.add_argument("--turn-review-timeout", type=float, default=None,
                    help="watched: how long the land lane waits for the Director to answer a "
                         "turn-end before escalating (s)")
    ap.add_argument("--read-timeout", type=float, default=None,
                    help="per-event read timeout for a land turn (s); land agents think")
    args = ap.parse_args(argv)

    # Resolve CLI > config > default (declarative-config slice). A malformed
    # .harness.json director block raises here, before any drain/spawn.
    cfg = config.load_director_config()
    posture = cfg.posture
    queue_dir = args.queue_dir if args.queue_dir is not None else cfg.paths.queue_dir
    poll = args.poll if args.poll is not None else cfg.merger.poll_s
    codex_command = args.codex if args.codex is not None else cfg.codex_command
    turn_review_timeout = (args.turn_review_timeout if args.turn_review_timeout is not None
                           else cfg.turn_review_timeout_s)
    read_timeout = (args.read_timeout if args.read_timeout is not None
                    else cfg.merger.read_timeout_s)
    decide = select_decider(autonomous=args.autonomous, mock=args.mock,
                            queue_base=queue_dir, turn_review_timeout=turn_review_timeout)
    # Workspace lifecycle hooks (R4) reach the land lane too — off under --mock. A land
    # worker on a FRESH box still needs `after_create` to re-clone the workspace, BUT
    # `before_run` is DROPPED here (review-arch P2): the land worker reuses the PR branch's
    # checkout, and a typical `before_run` sync (`git reset --hard origin/<default>`) would
    # reset the PR commits away before the merge. The land skill does its own fetch/rebase.
    hooks = None if args.mock else {k: v for k, v in cfg.workspace.hooks.items()
                                    if k != "before_run"}
    return run_loop(base=queue_dir, command=_command(args, codex_command, posture),
                    poll=poll, once=args.once, decide=decide, queue_base=queue_dir,
                    approval_policy=posture.approval_policy, sandbox=posture.sandbox,
                    read_timeout_s=read_timeout, max_merges=cfg.merger.max_merges,
                    hooks=hooks, hook_timeout_s=cfg.workspace.hook_timeout_s)


if __name__ == "__main__":
    raise SystemExit(main())
