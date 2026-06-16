"""Orchestrator — poll→dispatch→reconcile loop (Phase 2 second half; thin·watched).

`python -m director.orchestrator --team <id>` reads a board's "ready" tickets,
dispatches a Codex worker per ticket (up to a concurrency cap), and reconciles
each result back to the board — success → done state + comment, failure → one
re-dispatch, then a failure comment. Approval requests still flow through the
shared Director queue (the main session / a watched responder answers them); the
orchestrator never answers them itself (decision D-6/R6 in the spec).

Design owner: docs/product-specs/2026-06-14-orchestrator-dispatch-loop.md (R1–R7,
D-8..D-12). This module owns the build only. Single pass, bounded concurrency,
retry-once. DAG, backoff, crash-recovery, and the linear_graphql guardrail are
later phases (non-goals here).
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import director.queue as dq
from director import decider, run, status as status_mod, taxonomy
from director.board import linear as board_linear
from director.worker import autonomy

# Default logical-state → Linear workflow-state-name mapping (overridable on the CLI).
# `failed`/`blocked` are OPTIONAL (None = no such state → leave the ticket in `started`
# + comment).
DEFAULT_STATE_NAMES = {"ready": "Todo", "started": "In Progress",
                       "done": "Done", "failed": None, "blocked": None}


def resolve_states(board, team: str, names: dict | None = None) -> dict:
    """Resolve the four logical states (ready/started/done/failed) to board state ids,
    reading the team's workflow states once. A configured-but-missing name is a
    startup error — we fail before launching any worker, never mid-flight. `failed`
    may be None (no failed state → leave failures in `started` + comment, D-12)."""
    names = {**DEFAULT_STATE_NAMES, **(names or {})}
    states = board.workflow_states(team)
    out: dict = {}
    for logical in ("ready", "started", "done"):
        name = names[logical]
        if name not in states:
            raise RuntimeError(
                f"workflow state {name!r} (for {logical!r}) not found in team "
                f"{team!r}; have: {sorted(states)}")
        out[logical] = states[name]["id"]
    for opt in ("failed", "blocked"):  # optional terminal states
        oname = names.get(opt)
        if oname:
            if oname not in states:
                raise RuntimeError(
                    f"configured {opt} state {oname!r} not found in team {team!r}")
            out[opt] = states[oname]["id"]
        else:
            out[opt] = None
    return out


def dispatch(ticket: dict, **kwargs) -> dict:
    """Drive one worker through one ticket across multiple turns (wraps run.drive),
    converting any crash into a {kind: failed} disposition so one bad worker never
    sinks the pool. A module-level function so tests can patch it deterministically.

    The worker's prompt is composed via the dev-stage taxonomy (Phase 3b): a typed
    ticket (a Linear stage label) gets its stage-workflow template wrapped around the
    task; an untyped ticket passes through unchanged.

    Returns a DISPOSITION (`{kind: terminal|escalate|stuck|failed, ...}`) — the
    worker's/Director's judgment of what the turns meant, NOT a turn-status. reconcile
    executes it onto the board (R4: code never judges done-ness).

    `composed` is an intentional SHALLOW copy — its `blockers`/`labels` lists alias the
    board ticket's. Nothing downstream (drive) mutates them; callers must not."""
    composed = {**ticket, "prompt": taxonomy.compose_worker_prompt(ticket)}
    try:
        return run.drive(composed, **kwargs)
    except Exception as exc:  # subprocess death, handshake error, etc.
        return {"kind": "failed", "status": "failed", "turn_id": None, "turns": 0,
                "error": str(exc)}


def _maybe_enqueue_merge(tid, ticket: dict, outcome: dict, queue_base, workspace_root,
                         errs: list) -> bool:
    """If a `done` worker opened a PR, enqueue it to the serialized PR-merger (R4).

    The worker PROPOSES its PR via `report_outcome(done, pr_url=…, pr_branch=…)`; the
    orchestrator EXECUTES the `mergeRequest` enqueue here (D-40 — workers never write the
    Director queue themselves). Best-effort: an enqueue failure is recorded in `errs`
    (→ summary `reconcile_error`), never raised (mirrors the board-write discipline). No
    PR fields → nothing queued. The workspace path (where the PR branch lives, for the
    land lane) is derived the same way `run._workspace_for` does, without a run.py edit.
    Returns whether a mergeRequest was newly queued."""
    pr_url = outcome.get("pr_url")
    pr_branch = outcome.get("pr_branch")
    if not (pr_url or pr_branch):
        return False
    ws = ticket.get("workspace")
    if ws is None and workspace_root is not None:
        ws = str(Path(workspace_root) / str(tid))
    try:
        return dq.append_merge_request(tid, pr=pr_url, branch=pr_branch,
                                       workspace_path=ws, base=queue_base)
    except Exception as exc:
        errs.append(f"merge enqueue: {exc}")
        return False


def reconcile(board, ticket: dict, disp: dict, attempts: int,
              states: dict, retry_budget: int, *, queue_base=None,
              workspace_root=None) -> dict:
    """EXECUTE a drive disposition onto the board. Returns {"retry": True} to ask
    run_once to re-dispatch (a `failed` disposition within budget), or
    {"summary": {...}} for a terminal outcome. This is the R4 redesign: the board
    transition follows the worker/Director DISPOSITION (terminal done/blocked,
    escalate, stuck) — there is NO turn-status→board-state mapping. Board writes are
    best-effort — a write failure is recorded in the summary, never raised (the ticket
    stays visible in `started` for the watched Director)."""
    tid = ticket["id"]
    label = ticket.get("identifier") or tid
    kind = disp.get("kind")
    turns = disp.get("turns")
    telemetry = disp.get("telemetry")  # Symphony-grade per-ticket telemetry (plan M3)
    errs: list[str] = []

    def set_state(state_id):
        # A board write has THREE outcomes: success, raise, or return False (the
        # GraphQL call returned success:false). False is a failed write, recorded
        # so the summary never claims a state moved when it didn't.
        try:
            if not board.update_issue_state(tid, state_id):
                errs.append(f"set_state({state_id}) returned False")
        except Exception as exc:
            errs.append(f"set_state: {exc}")

    def comment(body):
        try:
            if not board.comment_issue(tid, body):
                errs.append("comment returned False")
        except Exception as exc:
            errs.append(f"comment: {exc}")

    def summarize(status, final_state, **extra):
        s = {"ticket": label, "status": status, "final_state": final_state,
             "attempts": attempts, "turns": turns}
        if telemetry is not None:  # carry telemetry to the StatusWriter (recent[] + aggregate)
            s["telemetry"] = telemetry
        s.update(extra)
        return s

    if kind == "terminal":
        outcome = disp.get("outcome") or {}
        ostatus = outcome.get("status")
        if ostatus == "done":
            set_state(states["done"])
            reason = f": {outcome.get('reason')}" if outcome.get("reason") else ""
            comment(f"✅ worker done after {turns} turn(s) (turn {disp.get('turn_id')}){reason}")
            # R4 handoff: a done worker that opened a PR feeds the serialized merger.
            enqueued = _maybe_enqueue_merge(tid, ticket, outcome, queue_base,
                                            workspace_root, errs)
            summary = summarize("completed", "done", merge_enqueued=enqueued)
        elif ostatus == "blocked":
            spawned = outcome.get("spawned_ticket_ids") or []
            final = "started"
            if states.get("blocked"):
                set_state(states["blocked"])
                final = "blocked"
            note = f" (spawned {', '.join(spawned)})" if spawned else ""
            comment(f"⛔ worker blocked after {turns} turn(s): {outcome.get('reason')}{note}")
            summary = summarize("blocked", final, spawned_ticket_ids=spawned)
        else:
            # A terminal with an unrecognized/missing status must NEVER silently mark
            # Done (R4: code never falsely completes). The standard paths only ever
            # produce done/blocked (needs_human is mapped to escalate by the decider
            # before reconcile), so this guards a malformed Director answer — surface
            # it and leave the ticket visible in `started` (review fix).
            comment(f"⚠️ terminal with unrecognized outcome {ostatus!r} after "
                    f"{turns} turn(s) — left in progress for review")
            summary = summarize("terminal_unknown", "started")
    elif kind == "escalate":
        comment(f"🙋 escalated to human after {turns} turn(s): {disp.get('reason')}")
        summary = summarize("escalated", "started")  # stays visible; human acts async
    elif kind == "stuck":
        final = "started"
        if states.get("failed"):
            set_state(states["failed"])
            final = "failed"
        comment(f"🌀 worker stuck ({disp.get('reason')}) after {turns} turn(s)")
        summary = summarize("stuck", final)
    elif kind == "failed":
        if attempts < 1 + retry_budget:
            return {"retry": True}
        detail = f": {disp['error']}" if disp.get("error") else ""
        comment(f"❌ worker failed ({disp.get('status')}) after {attempts} attempt(s){detail}")
        final = "started"
        if states.get("failed"):
            set_state(states["failed"])
            final = "failed"
        summary = summarize("failed", final)
    else:  # unknown disposition — never silently drop; surface and stay visible
        comment(f"⚠️ unknown disposition {kind!r} after {turns} turn(s)")
        summary = summarize("unknown", "started")

    if errs:
        summary["reconcile_error"] = "; ".join(errs)
    return {"summary": summary}


def eligible_tickets(tickets: list[dict], *, done_types=("completed",)) -> list[dict]:
    """The DAG-eligible subset: a ticket whose every blocked_by blocker is in a
    done state-type. A ticket with no blockers is always eligible. Pure function —
    blockers come from the board read (list_ready_issues -> ticket['blockers'])."""
    done = set(done_types)
    return [t for t in tickets
            if all(b.get("state_type") in done for b in t.get("blockers", []))]


def _dispatch_wave(board, tickets: list[dict], *, command: list[str], states: dict,
                   concurrency: int = 3, queue_base=None,
                   workspace_root=run.DEFAULT_WORKSPACE_ROOT, retry_budget: int = 1,
                   tools=None, tool_executor=None, install_skills: bool = False,
                   read_timeout_s: float = 30.0, timeout_s: float = 300.0,
                   status=None, wave: int = 1,
                   approval_policy: str = "untrusted",
                   sandbox: str = "workspace-write",
                   decide=decider.autonomous_decide,
                   max_turns: int = run.DEFAULT_MAX_TURNS) -> dict:
    """Claim, dispatch (bounded concurrency), and fully drain a given (already
    eligible) ticket list; returns {ticket_id: summary}. The wave BARRIER: returns
    only once every ticket has reached a terminal summary (incl. retries), so the
    continuous loop never has cross-wave in-flight tickets to re-dispatch.

    `status` (default no-op) is the orchestration-visibility writer (R3): claim →
    dispatch → terminal transitions are recorded for the Director to read. The calls
    are pure side-channel — with the no-op writer the returned summaries are
    byte-identical, so visibility never changes dispatch behavior."""
    status = status or status_mod.NoopStatusWriter()
    results: dict = {}
    attempts: dict = {}
    in_flight: set = set()  # ticket ids claimed/dispatched this wave (incl. pending retry)
    pool = ThreadPoolExecutor(max_workers=max(1, concurrency))
    futures: dict = {}

    def submit(ticket):
        fut = pool.submit(
            dispatch, ticket, command=command, queue_base=queue_base,
            workspace_root=workspace_root, tools=tools, tool_executor=tool_executor,
            install_skills=install_skills, read_timeout_s=read_timeout_s,
            timeout_s=timeout_s, approval_policy=approval_policy, sandbox=sandbox,
            decide=decide, max_turns=max_turns, attempt=attempts.get(ticket["id"], 1))
        futures[fut] = ticket
        status.dispatched(ticket)

    def claim_failed(ticket, reason):
        tid = ticket["id"]
        results[tid] = {"ticket": ticket.get("identifier") or tid,
                        "status": "claim_failed", "final_state": "ready",
                        "attempts": 0, "error": reason}
        status.terminal(ticket, results[tid])

    try:
        for ticket in tickets:
            tid = ticket["id"]
            if tid in in_flight or tid in results:
                continue  # duplicate ready entry this wave — claim/dispatch exactly once
            # claim = mark-before-act: transition to `started` BEFORE spawning, so a
            # crash leaves the ticket visibly in-progress (not silently re-run) and
            # the board shows progress to the watched Director (D-9). A write that
            # raises OR returns False is a failed claim — we never dispatch unclaimed.
            try:
                claimed = board.update_issue_state(tid, states["started"])
            except Exception as exc:
                claim_failed(ticket, f"claim raised: {exc}")
                continue
            if not claimed:
                claim_failed(ticket, "board rejected claim (update_issue_state returned False)")
                continue
            attempts[tid] = 1
            in_flight.add(tid)
            status.claimed(ticket, wave=wave, attempt=1)
            submit(ticket)

        while futures:
            done, _ = wait(list(futures), return_when=FIRST_COMPLETED)
            for fut in done:
                ticket = futures.pop(fut)
                tid = ticket["id"]
                outcome = reconcile(board, ticket, fut.result(),
                                    attempts[tid], states, retry_budget,
                                    queue_base=queue_base, workspace_root=workspace_root)
                if outcome.get("retry"):
                    attempts[tid] += 1
                    status.retrying(ticket, attempt=attempts[tid])
                    submit(ticket)  # stays in_flight across the retry
                else:
                    in_flight.discard(tid)
                    results[tid] = outcome["summary"]
                    status.terminal(ticket, outcome["summary"])
    finally:
        pool.shutdown(wait=True)
    return results


def run_once(board, command: list[str], *, team: str, states: dict,
             done_types=("completed",), status=None, **wave_kwargs) -> list[dict]:
    """One poll→filter→dispatch→reconcile pass. Polls ready tickets, keeps only the
    DAG-eligible ones (blockers all done), then dispatches+drains that wave. Returns
    a per-ticket summary list. The shared Director queue carries approvals to the
    watched responder — this function never answers them.

    A single-pass primitive: it records per-ticket transitions AND its own pass
    lifecycle (wave 1 → finished "pass_complete"). The MULTI-pass run envelope
    (re-poll waves, stuck detection, drained/stuck terminal) belongs to
    run_until_drained — a `--once` snapshot ends at "pass_complete" by design."""
    status = status or status_mod.NoopStatusWriter()
    status.wave(1)
    ready = board.list_ready_issues(team, states["ready"])
    eligible = eligible_tickets(ready, done_types=done_types)
    summaries = list(_dispatch_wave(board, eligible, command=command, states=states,
                                    status=status, **wave_kwargs).values())
    status.finished("pass_complete")
    return summaries


def run_until_drained(board, command: list[str], *, team: str, states: dict,
                      done_types=("completed",), max_passes: int = 50,
                      max_dispatched: int = 200, status=None, **wave_kwargs) -> dict:
    """Re-poll the board and dispatch each newly-eligible wave until the DAG drains.

    Board-as-truth: a completed ticket leaves the `ready` state (reconciled to done),
    so its dependents become eligible on the next poll — no in-memory completion
    ledger. `results` only remembers terminal tickets of THIS run so a claim-failed
    ticket (which stays in `ready`) isn't retried forever. Terminates on:
      - "drained"       — nothing left to do (no pending tickets)
      - "stuck"         — pending tickets remain but none eligible (a failed blocker
                          keeps dependents blocked, or a dependency cycle)
      - "max_passes" / "max_dispatched" — safety bounds against runaway / cycles
    Returns {summaries, passes, stopped_reason, stuck}."""
    results: dict = {}
    dispatched_count = 0
    passes = 0
    stopped_reason = "drained"
    stuck: list = []
    poll_error = None
    done = set(done_types)
    status = status or status_mod.NoopStatusWriter()
    while True:
        if passes >= max_passes:
            stopped_reason = "max_passes"
            break
        passes += 1
        status.wave(passes)
        try:
            ready = board.list_ready_issues(team, states["ready"])
        except Exception as exc:  # a transient poll failure ends the run cleanly, not a crash
            stopped_reason = "poll_failed"
            poll_error = str(exc)
            break
        pending = [t for t in ready if t["id"] not in results]  # not yet terminal this run
        eligible = eligible_tickets(pending, done_types=done_types)
        if not eligible:
            # No progress possible: every pending ticket (if any) is blocked — a failed
            # blocker, a cycle, or an unreadable blocker state. Report each with its
            # not-yet-done blockers (a None state_type shows up here) so the human sees
            # WHY it stuck, rather than spinning (R7).
            if pending:
                stopped_reason = "stuck"
                stuck = [{"ticket": t.get("identifier") or t["id"],
                          "blocked_by": [{"id": b.get("id"), "state_type": b.get("state_type")}
                                         for b in t.get("blockers", [])
                                         if b.get("state_type") not in done]}
                         for t in pending]
                status.stuck(stuck)
            break
        if dispatched_count + len(eligible) > max_dispatched:
            stopped_reason = "max_dispatched"
            break
        wave_summaries = _dispatch_wave(board, eligible, command=command, states=states,
                                        status=status, wave=passes, **wave_kwargs)
        # count only tickets that actually dispatched — a claim failure is not a dispatch,
        # so it must not consume the max_dispatched budget.
        dispatched_count += sum(1 for v in wave_summaries.values()
                                if v.get("status") != "claim_failed")
        results.update(wave_summaries)
    status.finished(stopped_reason)
    out = {"summaries": list(results.values()), "passes": passes,
           "stopped_reason": stopped_reason, "stuck": stuck}
    if poll_error:
        out["error"] = poll_error
    return out


class MockBoard:
    """In-memory board for `--mock` runs and tests: holds issues + workflow states,
    records transitions and comments. `fail_state_for` makes update_issue_state raise
    for given issue ids (exercises the claim/reconcile error paths)."""

    STATES = {"Todo": {"id": "st_todo", "type": "unstarted"},
              "In Progress": {"id": "st_prog", "type": "started"},
              "Done": {"id": "st_done", "type": "completed"}}

    def __init__(self, issues, states=None, *, fail_state_for=None):
        self._states = states or {k: dict(v) for k, v in self.STATES.items()}
        self._issues = {i["id"]: dict(i) for i in issues}
        self.comments: dict = {}
        self.transitions: dict = {}
        self._fail = set(fail_state_for or ())

    @classmethod
    def demo(cls) -> "MockBoard":
        return cls([
            {"id": "u1", "identifier": "DEMO-1", "title": "first",
             "description": "do first", "prompt": "DEMO-1: do first", "state_id": "st_todo"},
            {"id": "u2", "identifier": "DEMO-2", "title": "second",
             "description": "do second", "prompt": "DEMO-2: do second", "state_id": "st_todo"}])

    def workflow_states(self, team):
        return self._states

    def list_ready_issues(self, team, ready_state_id):
        out = []
        for i in self._issues.values():
            if i["state_id"] != ready_state_id:
                continue
            t = dict(i)
            # resolve each blocker id to its current {id, state_type} (DAG truth)
            t["blockers"] = [{"id": bid, "state_type": self._state_type(bid)}
                             for bid in i.get("blockers", [])]
            t["labels"] = list(i.get("labels", []))  # dev-stage type labels
            out.append(t)
        return out

    def _state_type(self, issue_id):
        iss = self._issues.get(issue_id)
        if not iss:
            return None
        sid = iss["state_id"]
        return next((v["type"] for v in self._states.values() if v["id"] == sid), None)

    def update_issue_state(self, issue_id, state_id):
        if issue_id in self._fail:
            raise RuntimeError(f"mock board: refusing state write for {issue_id}")
        self._issues[issue_id]["state_id"] = state_id
        self.transitions.setdefault(issue_id, []).append(state_id)
        return True

    def comment_issue(self, issue_id, body):
        self.comments.setdefault(issue_id, []).append(body)
        return True

    def state_name(self, issue_id) -> str:
        sid = self._issues[issue_id]["state_id"]
        return next((n for n, v in self._states.items() if v["id"] == sid), sid)


def _build_board(args):
    if args.mock:
        return MockBoard.demo()
    return board_linear.LinearBoard()


def _command(args) -> list[str]:
    if args.mock:
        return [sys.executable, run._MOCK, args.mock_scenario]
    # Both modes self-govern per-action (auto_review) AND get full network; the only
    # watched/un-watched difference is the turn-end decider. Exfil deferred (T11).
    # `bash -c` not `-lc`: a login shell would re-inject host profile env past the
    # deny-by-default boundary (run._command has the full rationale; SECURITY.md T11).
    codex = autonomy.codex_command(args.codex)
    return ["bash", "-c", codex]


def main(argv=None, *, board=None) -> int:
    ap = argparse.ArgumentParser(prog="director.orchestrator")
    ap.add_argument("--team", required=True, help="Linear team id to poll")
    ap.add_argument("--ready-state", default="Todo")
    ap.add_argument("--started-state", default="In Progress")
    ap.add_argument("--done-state", default="Done")
    ap.add_argument("--failed-state", default=None,
                    help="optional workflow state for exhausted failures (else stay started)")
    ap.add_argument("--blocked-state", default=None,
                    help="optional workflow state for a worker-reported blocked terminal "
                         "(else stay started + comment)")
    ap.add_argument("--max-turns", type=int, default=run.DEFAULT_MAX_TURNS,
                    help="multi-turn drive bound per ticket (R6); over it → stuck")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--mock", action="store_true", help="in-memory board + fake worker")
    ap.add_argument("--mock-scenario", default="plain",
                    choices=["plain", "approval", "approval_done", "report",
                             "tool", "turn_failed"])
    ap.add_argument("--codex", default="codex app-server", help="real worker command")
    ap.add_argument("--queue-dir", default=None)
    ap.add_argument("--workspace-root", default=None)
    ap.add_argument("--tools", choices=["none", "linear"], default="none")
    ap.add_argument("--install-skills", action="store_true")
    ap.add_argument("--once", action="store_true",
                    help="single pass (no re-poll); default is the DAG-aware continuous loop")
    ap.add_argument("--max-passes", type=int, default=50,
                    help="continuous loop safety bound on re-poll passes")
    ap.add_argument("--max-dispatched", type=int, default=200,
                    help="continuous loop safety bound on total tickets dispatched")
    ap.add_argument("--done-types", default="completed",
                    help="comma-separated blocker state-types that count as done (unblock)")
    ap.add_argument("--no-status", action="store_true",
                    help="disable the orchestration-visibility snapshot (default: on)")
    ap.add_argument("--status-dir", default=None,
                    help="orchestration-status dir override (default: .claude/harness/director-status)")
    ap.add_argument("--autonomous", action="store_true",
                    help="un-watched: use the code turn-end decider (no live Director "
                         "answers turn ends). Per-action self-governance (on-request + "
                         "auto_review) and full network are shared with the watched default")
    ap.add_argument("--read-timeout", type=float, default=30.0,
                    help="per-event read timeout for a worker turn (s); raise for slow "
                         "real codex workers that think >30s mid-turn")
    ap.add_argument("--turn-review-timeout", type=float, default=300.0,
                    help="watched: how long the queue decider waits for the Director to "
                         "answer a turn end before escalating (s)")
    args = ap.parse_args(argv)

    board = board if board is not None else _build_board(args)
    states = resolve_states(board, args.team, {
        "ready": args.ready_state, "started": args.started_state,
        "done": args.done_state, "failed": args.failed_state,
        "blocked": args.blocked_state})
    done_types = tuple(s.strip() for s in args.done_types.split(",") if s.strip())

    # Decider selection (spec R5). Watched (default): each turn-end routes to the
    # Director queue and the live main session answers free-form (docs/DIRECTOR.md).
    # Un-watched (--autonomous) and offline (--mock) use the code decider:
    # --mock has no live Director session to answer turnReviews, so the watched queue
    # decider would hang — the code decider self-resolves + trusts the worker proposal.
    decide = (decider.autonomous_decide if (args.autonomous or args.mock)
              else decider.make_queue_decider(base=args.queue_dir,
                                              timeout_s=args.turn_review_timeout))

    tools = tool_executor = None
    if args.tools == "linear":
        from director.worker.tools import linear_graphql_spec, make_linear_tool_executor
        tools = [linear_graphql_spec()]
        tool_executor = make_linear_tool_executor()

    kwargs = {"team": args.team, "states": states, "concurrency": args.concurrency,
              "queue_base": args.queue_dir, "tools": tools, "tool_executor": tool_executor,
              "install_skills": args.install_skills, "done_types": done_types,
              "status": None if args.no_status else status_mod.StatusWriter(base=args.status_dir),
              # Shared per-action posture for both modes (auto_review wrapped in _command);
              # --autonomous differs only by network (T11) + the code decider above.
              "approval_policy": autonomy.APPROVAL_POLICY,
              "sandbox": autonomy.SANDBOX,
              "decide": decide, "max_turns": args.max_turns,
              "read_timeout_s": args.read_timeout}
    if args.workspace_root:
        kwargs["workspace_root"] = Path(args.workspace_root)

    if args.once:
        summaries = run_once(board, _command(args), **kwargs)
        for s in summaries:
            print(json.dumps(s, ensure_ascii=False))
        return 0 if all(s["status"] != "claim_failed" for s in summaries) else 1

    result = run_until_drained(board, _command(args), max_passes=args.max_passes,
                               max_dispatched=args.max_dispatched, **kwargs)
    for s in result["summaries"]:
        print(json.dumps(s, ensure_ascii=False))
    print(json.dumps({"stopped_reason": result["stopped_reason"],
                      "passes": result["passes"], "stuck": result["stuck"]},
                     ensure_ascii=False))
    return 0 if result["stopped_reason"] == "drained" else 1


if __name__ == "__main__":
    raise SystemExit(main())
