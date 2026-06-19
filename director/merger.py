"""Serialized PR-merger (worker-qa-and-serialized-pr-merge slice, D-47/D-50/D-53).

A worker finishes a ticket, self-QAs, and opens a PR (it does NOT merge). The PR
lands here: a SINGLE consumer drains the `mergeRequest` queue one PR at a time —
rebase onto the latest main, run the integration gate, resolve threads. Serialization
is the whole point (R3): "clean against a stale main" is not safe, so PRs must land
sequentially, each re-based + re-gated against the main the previous merge produced. A
single consumer draining one-at-a-time gives that for free — no lock, no concurrency
counter in the hot path.

The merger does NOT invent a turn machine: each PR runs through `director.run.drive`
with the vendored `land` skill, and the per-turn disposition is owned by the injected
`decide` (D-50) — exactly the seam the worker driver uses. The land lane *prepares* the
PR (rebase, fix CI, resolve threads, push) and reports `terminal(done)` = ready; a
conflict it cannot resolve, a red integration gate, or a taste call surfaces as
`escalate`/`stuck`/`failed`, routed to the human VIA the Director (single surface, R4/R7).

**Code owns the irreversible merge (merge-preservation-hardening D1).** The land worker
does NOT run `gh pr merge`; on a prepared `done` the merger runs a code gate —
a preservation tripwire (`merge_preserve`, R1: did the PR's change survive the rebase?)
then a hygiene gate (R3: CI green + threads resolved) — and only then issues the
squash-merge itself. Any gate failure withholds + escalates (a `mergeReview`); CI still
running defers (retry later). It never silently merges, and the irreversible act is
gated by code, not the land worker's prose judgment.

This module owns the drain + classification. The Director-escalation wiring and the
worker→enqueue call site are M3; the live serializer wire-pin is M4.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import subprocess
import sys
import time
from typing import Callable

import director.merge_preserve as mp
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
# Aliased from DEFAULTS (ARCHITECTURE invariant 5: no parallel default literal in director/).
DEFAULT_REQUIRE_RESOLVED_THREADS = config.DEFAULTS["merger"]["require_resolved_threads"]

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
    # Prefer the code gate's reason (a prepared `done` whose preservation/hygiene gate
    # withheld it — the land-lane disposition would otherwise read as a bare "done").
    reason = (result.get("gate_reason") or disp.get("reason") or result.get("error")
              or disp.get("kind") or "merge failed")
    # Carry the attempt (default 1) into the mergeReview: the review id discriminates per
    # attempt (a 2nd failed retry surfaces distinctly) and the Director's requeue reads it
    # to bump attempt+1. Return the ACTUAL append result — a dedup means nothing NEW
    # surfaced, so don't claim it did.
    return dq.append_merge_review(
        req.get("ticket_id"), pr=payload.get("pr"), branch=payload.get("branch"),
        result=result["result"], reason=reason, disposition=disp,
        workspace_path=req.get("workspace_path"), attempt=payload.get("attempt", 1),
        base=base)


def _is_prepared(disp: dict) -> bool:
    """A land-lane `terminal(done)` now means the PR is PREPARED (rebased, gate-green,
    threads replied, pushed) — ready for the merger's code gate, NOT yet merged (D1)."""
    return (disp or {}).get("kind") == "terminal" \
        and ((disp or {}).get("outcome") or {}).get("status") == "done"


def _squash_merge(pr: str | None, *, cwd: str | None = None, run=subprocess.run) -> bool:
    """The code-issued squash-merge (merge-preservation D1) — the irreversible act the land
    worker no longer performs. argv (never a shell string; `pr` is worker-supplied). Returns
    True iff `gh pr merge` succeeded; False (fail-closed) on missing pr / non-zero / error."""
    if not pr:
        return False
    try:
        # `gh pr merge <url>` addresses the PR by URL (cwd-independent); `cwd=ws` is
        # workspace-locality, not a correctness requirement — and a stale/absent workspace
        # raises here → caught → fail-closed (escalate), which is the safe direction.
        proc = run(["gh", "pr", "merge", pr, "--squash"], cwd=cwd,
                   capture_output=True, text=True)
    except Exception:
        return False
    return proc.returncode == 0


def _finalize_merge(req: dict, *, intended, require_resolved_threads: bool,
                    run=subprocess.run) -> dict:
    """Code gate (R1 preservation tripwire → R3 hygiene gate) then the code-issued
    squash-merge — run after the land lane reports the PR PREPARED. Returns a dict with
    `result` ∈ {merged, escalated, deferred} (+ `gate`/`gate_reason` context):
      - preservation trip / hygiene failing / unreadable fact → `escalated` (withhold);
      - CI still running → `deferred` (retry later, never a merge-while-pending);
      - both gates clean → code issues `gh pr merge` → `merged` (or `escalated` if it fails).
    Fail-closed throughout: a fact we cannot read withholds the merge."""
    payload = req.get("payload") or {}
    pr = payload.get("pr")
    ws = req.get("workspace_path")
    gate: dict = {}
    # R1 preservation tripwire — skipped only on a Director-approved override (still hygiene-
    # gated). `intended` was captured BEFORE the land lane rebased; `actual` is post-rebase.
    if not payload.get("preservation_override"):
        if intended is None:
            return {"result": "escalated",
                    "gate_reason": "could not read the PR's intended diff pre-rebase (fail-closed)"}
        actual = mp.files_from_pr(pr, run=run)
        if actual is None:
            return {"result": "escalated",
                    "gate_reason": "could not read the merged diff post-rebase (fail-closed)"}
        delta = mp.preservation_delta(intended, actual)
        gate["preservation"] = delta
        if not delta["ok"]:
            return {"result": "escalated", "gate": gate,
                    "gate_reason": "preservation tripwire — dropped=%s shrunk=%s"
                    % (delta["dropped_paths"], delta["shrunk_paths"])}
    # R3 hygiene gate
    hy = mp.pr_hygiene(pr, require_threads=require_resolved_threads, run=run)
    gate["hygiene"] = hy
    if hy == "pending":
        return {"result": "deferred", "gate": gate, "gate_reason": "CI checks still pending"}
    if hy == "failing":
        return {"result": "escalated", "gate": gate,
                "gate_reason": "hygiene gate — CI not green or unresolved review threads"}
    # both gates clean → CODE performs the irreversible merge
    if _squash_merge(pr, cwd=ws, run=run):
        return {"result": "merged", "gate": gate}
    # Idempotency guard (reliability review): a crash after a prior attempt's `gh pr merge`
    # succeeded but before consume re-drives finalize, and re-merging a MERGED PR fails. If the
    # PR is in fact already merged, this is an idempotent success — finalize as merged so the
    # ticket isn't stranded in `merging` with its work already on main.
    if mp.pr_is_merged(pr, run=run):
        return {"result": "merged", "gate": gate}
    return {"result": "escalated", "gate": gate,
            "gate_reason": "gh pr merge failed (fail-closed)"}


def _log_evidence_audit(req: dict, fin: dict) -> None:
    """R4/R5 audit: record the worker's self-reported sweep evidence vs what the code gate
    independently verified, on a finalized (merged/escalated) result. Three structured lines:
      - no evidence (R5 degraded)            → `no_sweep_evidence`;
      - evidence + gate withheld a claim-clean PR → `protocol_misfire` (the sweep missed
        something the merger caught — the signal the human/Director learns from);
      - evidence + consistent                → `sweep_evidence_verified`.
    Skipped for `deferred` (verification is incomplete — CI still pending). Best-effort;
    never raises (a daemon-diagnostic line, like the orchestrator's `*_skipped` logs)."""
    result = fin.get("result")
    if result == "deferred":
        return
    ticket = req.get("ticket_id")
    ev = (req.get("payload") or {}).get("evidence") or {}
    if not ev:
        print(json.dumps({"merger": "no_sweep_evidence", "ticket": ticket,
                          "verified_result": result}), file=sys.stderr)
        return
    claimed_clean = ev.get("checks_state") in (None, "green") and not ev.get("unresolved_threads")
    misfire = claimed_clean and result == "escalated"
    if misfire:
        event = "protocol_misfire"            # worker claimed clean; the gate caught a problem
    elif claimed_clean:
        event = "sweep_evidence_verified"     # worker claimed clean; the gate agrees
    else:
        event = "sweep_evidence_consistent"   # worker honestly reported issues; gate recorded
    print(json.dumps({"merger": event, "ticket": ticket, "claimed": ev,
                      "verified_result": result, "gate_reason": fin.get("gate_reason"),
                      "misfire": misfire}), file=sys.stderr)


def process_request(req: dict, *, driver: Callable = run.drive,
                    decide: Callable = autonomous_decide,
                    require_resolved_threads: bool = DEFAULT_REQUIRE_RESOLVED_THREADS,
                    sh=subprocess.run, finalize: Callable = _finalize_merge,
                    **drive_kwargs) -> dict:
    """Run ONE merge request: capture the PR's intended diff, drive the land lane to PREPARE
    the PR, then (on a prepared `done`) run the code gate + code-issued merge (D1). A driver
    crash becomes a `failed` result (one bad PR never sinks the drain). Non-`done` land-lane
    outcomes classify/escalate exactly as before; a prepared `done` becomes
    merged/escalated/deferred per `finalize` (the gate; injectable for tests)."""
    base = {"request_id": req["request_id"], "ticket_id": req.get("ticket_id")}
    payload = req.get("payload") or {}
    pr = payload.get("pr")
    # Capture INTENDED (the PR's per-file change) BEFORE the land lane rebases (R1). Skipped
    # when there is no PR or the Director already approved the drop (override). `sh` is the
    # injectable subprocess runner (tests fake it; merger is module `run`, hence the name).
    intended = mp.files_from_pr(pr, run=sh) if (pr and not payload.get("preservation_override")) else None
    ticket = land_ticket_from_request(req)
    try:
        disp = driver(ticket, decide=decide, **drive_kwargs)
    except Exception as exc:
        return {**base, "result": "failed", "error": str(exc)}
    if not _is_prepared(disp):
        return {**base, "result": classify(disp), "disposition": disp}
    fin = finalize(req, intended=intended,
                   require_resolved_threads=require_resolved_threads, run=sh)
    _log_evidence_audit(req, fin)
    return {**base, "disposition": disp, **fin}


def drain(*, base=None, driver: Callable = run.drive, decide: Callable = autonomous_decide,
          max_merges: int = DEFAULT_MAX_MERGES,
          require_resolved_threads: bool = DEFAULT_REQUIRE_RESOLVED_THREADS,
          sh=subprocess.run, finalize: Callable = _finalize_merge, **drive_kwargs) -> list[dict]:
    """Drain the merge queue SERIALLY: pop the oldest pending PR, run it through the land
    lane + code gate, mark it consumed (or DEFER it), repeat — one PR in flight at a time
    (R3). Returns a per-PR result list ({request_id, ticket_id, result: merged|escalated|
    failed|deferred, ...}).

    Single-consumer ⇒ serialization is structural. A `deferred` result (CI still running)
    is left PENDING — not consumed, not surfaced — and skipped for the rest of THIS pass
    (a per-pass `deferred` set), so other queued PRs still drain (no head-of-line block)
    and the merger's poll loop retries it later (no busy-spin). The loop terminates because
    every non-deferred request is consumed and deferred ones are skipped; `max_merges`
    bounds it. `drive_kwargs` pass straight through to the land lane."""
    results: list[dict] = []
    processed = 0
    deferred: set[str] = set()
    with _single_consumer_lock(base):  # enforce single PR-merger (R4) before any drive
        while processed < max_merges:
            pend = [r for r in pending_merges(base=base)
                    if r["request_id"] not in deferred]
            if not pend:
                break
            req = pend[0]  # FIFO — oldest queued PR first
            result = process_request(req, driver=driver, decide=decide,
                                     require_resolved_threads=require_resolved_threads,
                                     sh=sh, finalize=finalize, **drive_kwargs)
            if result["result"] == "deferred":
                # CI still running: leave PENDING (do not consume/surface), skip this pass.
                deferred.add(req["request_id"])
                results.append(result)
                processed += 1
                continue
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
             require_resolved_threads: bool = DEFAULT_REQUIRE_RESOLVED_THREADS,
             **drive_kwargs) -> int:
    """The standalone merger's body: drain the merge queue, then either exit (`once`) or
    keep watching for new PRs (the drain-runner; spec Open Q resolved to a standalone,
    event-woken process — D-47/R7). `once` runs a single drain pass and returns (cron /
    tests). Otherwise it polls the queue and drains whenever a `mergeRequest` is pending,
    sleeping `poll` between checks — woken by work, never a busy-spin (a `deferred`
    CI-pending PR is retried on the next poll). `max_merges` bounds one drain pass. Returns 0."""
    while True:
        if pending_merges(base=base):  # only take the flock + drive when there is work
            drain(base=base, command=command, decide=decide, max_merges=max_merges,
                  require_resolved_threads=require_resolved_threads, **drive_kwargs)
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
                    require_resolved_threads=cfg.merger.require_resolved_threads,
                    hooks=hooks, hook_timeout_s=cfg.workspace.hook_timeout_s)


if __name__ == "__main__":
    raise SystemExit(main())
