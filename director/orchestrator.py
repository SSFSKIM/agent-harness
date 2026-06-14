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

from director import run
from director.board import linear as board_linear

# Default logical-state → Linear workflow-state-name mapping (overridable on the CLI).
DEFAULT_STATE_NAMES = {"ready": "Todo", "started": "In Progress",
                       "done": "Done", "failed": None}


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
    failed_name = names.get("failed")
    if failed_name:
        if failed_name not in states:
            raise RuntimeError(
                f"configured failed state {failed_name!r} not found in team {team!r}")
        out["failed"] = states[failed_name]["id"]
    else:
        out["failed"] = None
    return out


def dispatch(ticket: dict, **kwargs) -> dict:
    """Drive one worker through one ticket (wraps run.run_ticket), converting any
    crash into a {status: failed} result so one bad worker never sinks the pool.
    A module-level function so tests can patch it deterministically."""
    try:
        return run.run_ticket(ticket, **kwargs)
    except Exception as exc:  # subprocess death, handshake error, etc.
        return {"status": "failed", "turn_id": None, "error": str(exc)}


def reconcile(board, ticket: dict, result: dict, attempts: int,
              states: dict, retry_budget: int) -> dict:
    """Map a worker result to board state/comment. Returns {"retry": True} to ask
    run_once to re-dispatch, or {"summary": {...}} for a terminal outcome. Board
    writes are best-effort — a write failure is recorded in the summary, never
    raised (the ticket stays visible in `started` for the watched Director)."""
    tid = ticket["id"]
    label = ticket.get("identifier") or tid
    status = result.get("status")
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

    if status == "completed":
        set_state(states["done"])
        comment(f"✅ worker completed (turn {result.get('turn_id')})")
        summary = {"ticket": label, "status": "completed",
                   "final_state": "done", "attempts": attempts}
    elif attempts < 1 + retry_budget:
        return {"retry": True}
    else:
        detail = f": {result['error']}" if result.get("error") else ""
        comment(f"❌ worker failed ({status}) after {attempts} attempt(s){detail}")
        final = "started"
        if states.get("failed"):
            set_state(states["failed"])
            final = "failed"
        summary = {"ticket": label, "status": "failed",
                   "final_state": final, "attempts": attempts}

    if errs:
        summary["reconcile_error"] = "; ".join(errs)
    return {"summary": summary}


def run_once(board, command: list[str], *, team: str, states: dict,
             concurrency: int = 3, queue_base=None,
             workspace_root=run.DEFAULT_WORKSPACE_ROOT, retry_budget: int = 1,
             tools=None, tool_executor=None, install_skills: bool = False,
             read_timeout_s: float = 30.0, timeout_s: float = 300.0) -> list[dict]:
    """One poll→dispatch→reconcile pass. Polls ready tickets, claims each (mark
    before act), dispatches up to `concurrency` workers, and reconciles each as it
    finishes (re-dispatching a failure within budget). Returns a per-ticket summary
    list. The shared Director queue (queue_base) carries approvals to the watched
    responder — this function never answers them."""
    ready = board.list_ready_issues(team, states["ready"])
    results: dict = {}
    attempts: dict = {}
    in_flight: set = set()  # ticket ids claimed/dispatched this pass (incl. pending retry)
    pool = ThreadPoolExecutor(max_workers=max(1, concurrency))
    futures: dict = {}

    def submit(ticket):
        fut = pool.submit(
            dispatch, ticket, command=command, queue_base=queue_base,
            workspace_root=workspace_root, tools=tools, tool_executor=tool_executor,
            install_skills=install_skills, read_timeout_s=read_timeout_s,
            timeout_s=timeout_s)
        futures[fut] = ticket

    def claim_failed(ticket, reason):
        tid = ticket["id"]
        results[tid] = {"ticket": ticket.get("identifier") or tid,
                        "status": "claim_failed", "final_state": "ready",
                        "attempts": 0, "error": reason}

    try:
        for ticket in ready:
            tid = ticket["id"]
            if tid in in_flight or tid in results:
                continue  # duplicate ready entry this pass — claim/dispatch exactly once
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
            submit(ticket)

        while futures:
            done, _ = wait(list(futures), return_when=FIRST_COMPLETED)
            for fut in done:
                ticket = futures.pop(fut)
                tid = ticket["id"]
                outcome = reconcile(board, ticket, fut.result(),
                                    attempts[tid], states, retry_budget)
                if outcome.get("retry"):
                    attempts[tid] += 1
                    submit(ticket)  # stays in_flight across the retry
                else:
                    in_flight.discard(tid)
                    results[tid] = outcome["summary"]
    finally:
        pool.shutdown(wait=True)
    return list(results.values())


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
        return [dict(i) for i in self._issues.values() if i["state_id"] == ready_state_id]

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
    return ["bash", "-lc", args.codex]


def main(argv=None, *, board=None) -> int:
    ap = argparse.ArgumentParser(prog="director.orchestrator")
    ap.add_argument("--team", required=True, help="Linear team id to poll")
    ap.add_argument("--ready-state", default="Todo")
    ap.add_argument("--started-state", default="In Progress")
    ap.add_argument("--done-state", default="Done")
    ap.add_argument("--failed-state", default=None,
                    help="optional workflow state for exhausted failures (else stay started)")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--mock", action="store_true", help="in-memory board + fake worker")
    ap.add_argument("--mock-scenario", default="plain", choices=["plain", "approval"])
    ap.add_argument("--codex", default="codex app-server", help="real worker command")
    ap.add_argument("--queue-dir", default=None)
    ap.add_argument("--workspace-root", default=None)
    ap.add_argument("--tools", choices=["none", "linear"], default="none")
    ap.add_argument("--install-skills", action="store_true")
    args = ap.parse_args(argv)

    board = board if board is not None else _build_board(args)
    states = resolve_states(board, args.team, {
        "ready": args.ready_state, "started": args.started_state,
        "done": args.done_state, "failed": args.failed_state})

    tools = tool_executor = None
    if args.tools == "linear":
        from director.worker.tools import linear_graphql_spec, make_linear_tool_executor
        tools = [linear_graphql_spec()]
        tool_executor = make_linear_tool_executor()

    kwargs = {"team": args.team, "states": states, "concurrency": args.concurrency,
              "queue_base": args.queue_dir, "tools": tools, "tool_executor": tool_executor,
              "install_skills": args.install_skills}
    if args.workspace_root:
        kwargs["workspace_root"] = Path(args.workspace_root)
    summaries = run_once(board, _command(args), **kwargs)

    for s in summaries:
        print(json.dumps(s, ensure_ascii=False))
    return 0 if all(s["status"] != "claim_failed" for s in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
