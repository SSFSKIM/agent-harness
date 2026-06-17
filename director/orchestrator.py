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
import signal
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import director.queue as dq
from director import config, decider, run, status as status_mod, taxonomy
from director.board import linear as board_linear
from director.worker import autonomy

# Default logical-state → Linear workflow-state-name mapping. The VALUES are owned by
# `config.DEFAULTS["states"]` (single source — declarative-config slice); aliased so
# `resolve_states` and direct callers keep working. A host overrides ready/started/
# done/failed/blocked in `.harness.json` `director.states` (the CLI flags still win
# over both). `failed`/`blocked` are OPTIONAL (None = no such state → leave the ticket
# in `started` + comment).
DEFAULT_STATE_NAMES = dict(config.DEFAULTS["states"])  # copy — never alias the shared DEFAULTS


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
              workspace_root=None, external_state=None) -> dict:
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
    elif kind == "cancelled":
        # Active-run reconciliation stopped this worker: its ticket left `started`
        # (a human moved it). The human OWNS the new state, so we do NOT re-transition
        # the board and do NOT retry (D-62 / Symphony "terminate without cleanup").
        # `final_state` is the OBSERVED external state the human moved it to (consistent
        # with the other branches = the board state the ticket ends in); "released" is
        # the fallback when that observation wasn't captured.
        final = external_state or "released"
        comment(f"🛑 worker stopped after {turns} turn(s) — ticket moved to {final!r} "
                f"externally (reconciliation); claim released")
        summary = summarize("cancelled", final)
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


def _stuck_report(pending: list[dict], done_set: set) -> list[dict]:
    """Each pending-but-blocked ticket with its not-yet-done blockers — the operator's
    "why is nothing progressing" view (R7). A None state_type (an unreadable blocker)
    surfaces here too. Pure; shared by `run_until_drained` (its terminal "stuck" report)
    and the daemon's idle heartbeat (stuck-as-status, D-66)."""
    return [{"ticket": t.get("identifier") or t["id"],
             "blocked_by": [{"id": b.get("id"), "state_type": b.get("state_type")}
                            for b in t.get("blockers", [])
                            if b.get("state_type") not in done_set]}
            for t in pending]


def _backoff_s(n: int, *, base: float, cap: float) -> float:
    """Exponential backoff (Symphony §8.4): `min(base · 2^(n-1), cap)` for the n-th
    occurrence (n≥1 → base, n=2 → 2·base, …, capped at `cap`). Pure; shared by the
    daemon's retry / idle-poll / claim-re-admission backoff (spec D-78). `n<1` clamps to
    `base` (defensive — every caller passes n≥1)."""
    return min(base * (2 ** max(0, n - 1)), cap)


def _reconcile_in_flight(board, in_flight_tickets, cancel_events: dict,
                         started_state_id, cancelled_states: dict | None = None) -> list:
    """Active-run reconciliation (Symphony §16.3): re-read the tracker state of the
    in-flight tickets and signal cancel for any ticket a human moved OUT of `started`
    (the operator-control lever). A ticket whose id is absent from the refresh
    (deleted/unknown) is left running — never cancel on missing data. When a cancel is
    signalled, the observed external state name is recorded in `cancelled_states[tid]`
    so the summary can report what the human moved it to (not just "released").

    **Fail-soft (R5/§8.5):** the WHOLE pass is total — any error (a
    `fetch_issue_states_by_ids` raise, or anything else) keeps every worker running
    (returns []) and never raises into the wave loop. Returns the ids newly cancelled."""
    try:
        tickets = list(in_flight_tickets)
        ids = [t["id"] for t in tickets]
        if not ids:
            return []
        states_now = board.fetch_issue_states_by_ids(ids)
        cancelled: list = []
        for t in tickets:
            tid = t["id"]
            cur = states_now.get(tid)
            if cur is None:
                continue  # unknown id → conservative, keep running
            if cur.get("state_id") != started_state_id:
                ev = cancel_events.get(tid)
                if ev is not None and not ev.is_set():
                    ev.set()
                    if cancelled_states is not None:
                        cancelled_states[tid] = cur.get("state_name")
                    cancelled.append(tid)
        return cancelled
    except Exception:
        return []  # any error in the pass → skip this reconcile tick (§8.5, R5/R12)


class _RunState:
    """The orchestrator's running-map + the claim/submit/reap machinery shared by the
    batch wave (`_dispatch_wave`) and the continuous daemon (`run_forever`). It holds
    the per-worker `futures` (the running-map), the claim bookkeeping, and the cancel
    Events; its methods carry the ONE implementation of claim-before-act, worker submit,
    and reap→reconcile→retry-or-terminal so the two loops never duplicate that logic
    (spec D-63).

    Single-threaded by contract: every method runs on the orchestrator's MAIN thread
    (workers run in the pool and only ever READ their `cancel_event`), so the dicts need
    no lock and the StatusWriter stays a lock-free single writer (RELIABILITY R13)."""

    def __init__(self, *, board, states, status, retry_budget: int, concurrency: int,
                 queue_base, workspace_root, retain_results: bool = True, **dispatch_kwargs):
        self.board = board
        self.states = states
        self.status = status or status_mod.NoopStatusWriter()
        self.retry_budget = retry_budget
        self.queue_base = queue_base
        self.workspace_root = workspace_root
        # The batch wave RETURNS its results dict, so it retains every terminal summary.
        # The daemon (run_forever) runs unbounded, so it does NOT retain (its durable
        # output is the bounded status.json `recent[]`) — preventing an unbounded
        # in-memory leak over a multi-week run.
        self.retain_results = retain_results
        # Fixed per-worker dispatch kwargs (command/tools/posture/decide/timeouts/…);
        # `attempt` and `cancel_event` are added per submit. queue_base/workspace_root
        # are stored separately (reconcile needs them too), so they are NOT in here.
        self._dispatch_kwargs = dispatch_kwargs
        self.pool = ThreadPoolExecutor(max_workers=max(1, concurrency))
        self.futures: dict = {}          # Future -> ticket (the running-map)
        self.attempts: dict = {}         # tid -> attempt count
        self.in_flight: set = set()      # tids claimed/dispatched, not yet terminal
        self.cancel_events: dict = {}    # tid -> threading.Event (set by reconciliation)
        self.cancelled_states: dict = {} # tid -> observed external state name at cancel
        self.results: dict = {}          # tid -> terminal summary
        self.claim_failed: set = set()   # tids whose claim raised/returned False

    def submit(self, ticket) -> None:
        # FRESH cancel Event per attempt — a retried ticket starts cancellable-clean
        # (the prior attempt's event is discarded). The main thread sets it during
        # reconciliation; the worker thread reads it (Event is thread-safe).
        ev = threading.Event()
        self.cancel_events[ticket["id"]] = ev
        fut = self.pool.submit(
            dispatch, ticket, queue_base=self.queue_base, workspace_root=self.workspace_root,
            attempt=self.attempts.get(ticket["id"], 1), cancel_event=ev,
            **self._dispatch_kwargs)
        self.futures[fut] = ticket
        self.status.dispatched(ticket)

    def _claim_failed(self, ticket, reason) -> None:
        tid = ticket["id"]
        self.claim_failed.add(tid)  # daemon dedup: never re-claim a failed-claim ticket
        row = {"ticket": ticket.get("identifier") or tid, "status": "claim_failed",
               "final_state": "ready", "attempts": 0, "error": reason}
        if self.retain_results:
            self.results[tid] = row
        self.status.terminal(ticket, row)

    def claim_and_submit(self, ticket, *, wave: int) -> bool:
        """Claim = mark-before-act (D-9): transition to `started` BEFORE spawning, so a
        crash leaves the ticket visibly in-progress (not silently re-run) and the board
        shows progress to the watched Director. A write that raises OR returns False is a
        failed claim — never dispatch unclaimed. Returns whether the worker dispatched."""
        tid = ticket["id"]
        try:
            claimed = self.board.update_issue_state(tid, self.states["started"])
        except Exception as exc:
            self._claim_failed(ticket, f"claim raised: {exc}")
            return False
        if not claimed:
            self._claim_failed(ticket, "board rejected claim (update_issue_state returned False)")
            return False
        self.attempts[tid] = 1
        self.in_flight.add(tid)
        self.status.claimed(ticket, wave=wave, attempt=1)
        self.submit(ticket)
        return True

    def reap(self, done, on_retry=None) -> None:
        """Execute each completed future's disposition: pop it, drop its cancel Event,
        reconcile (retry → re-submit within budget [stays in_flight], else terminal →
        results + status). The future result is the final word — a cancel Event that
        fired on an already-finished worker is inert (no double processing).

        `on_retry` is the single seam for daemon retry backoff (spec D-75): a retry within
        budget calls `(on_retry or self.submit)(ticket)`. Default None → IMMEDIATE submit
        — the batch wave is byte-unchanged. The daemon passes a hook that SCHEDULES the
        re-dispatch after a backoff (the ticket stays in_flight, not in futures)."""
        for fut in done:
            ticket = self.futures.pop(fut)
            tid = ticket["id"]
            self.cancel_events.pop(tid, None)  # worker ended — drop its cancel Event
            outcome = reconcile(self.board, ticket, fut.result(), self.attempts[tid],
                                self.states, self.retry_budget, queue_base=self.queue_base,
                                workspace_root=self.workspace_root,
                                external_state=self.cancelled_states.pop(tid, None))
            if outcome.get("retry"):
                self.attempts[tid] += 1
                self.status.retrying(ticket, attempt=self.attempts[tid])
                (on_retry or self.submit)(ticket)  # daemon defers (backoff); batch now
            else:
                self.in_flight.discard(tid)
                self.attempts.pop(tid, None)  # terminal — drop bookkeeping (daemon memory)
                if self.retain_results:
                    self.results[tid] = outcome["summary"]
                self.status.terminal(ticket, outcome["summary"])

    def reconcile_in_flight(self) -> None:
        """Active-run reconciliation (§16.3, stage 1, lifted UNCHANGED): re-read in-flight
        states and signal cancel for any ticket a human moved out of `started`. On the
        MAIN thread → StatusWriter stays a lock-free single writer (R13/D-60)."""
        _reconcile_in_flight(self.board, self.futures.values(), self.cancel_events,
                             self.states["started"], self.cancelled_states)

    def shutdown(self) -> None:
        self.pool.shutdown(wait=True)


def _dispatch_wave(board, tickets: list[dict], *, command: list[str], states: dict,
                   concurrency: int = 3, queue_base=None,
                   workspace_root=run.DEFAULT_WORKSPACE_ROOT, retry_budget: int = 1,
                   tools=None, tool_executor=None, install_skills: bool = False,
                   read_timeout_s: float = 30.0, timeout_s: float = 300.0,
                   status=None, wave: int = 1,
                   approval_policy: str = "untrusted",
                   sandbox: str = "workspace-write",
                   decide=decider.autonomous_decide,
                   max_turns: int = run.DEFAULT_MAX_TURNS,
                   reconcile_interval_s: float = 15.0) -> dict:
    """Claim, dispatch (bounded concurrency), and fully drain a given (already
    eligible) ticket list; returns {ticket_id: summary}. The wave BARRIER: returns
    only once every ticket has reached a terminal summary (incl. retries), so the
    continuous loop never has cross-wave in-flight tickets to re-dispatch.

    This is the BATCH claim discipline — every eligible ticket is claimed up front
    ("flood"); the pool bounds how many RUN at once. The daemon (`run_forever`) instead
    claims only as slots free (bounded top-up, D-64) — the difference is the claim
    cadence, not the per-worker machinery, which both share via `_RunState`.

    `status` (default no-op) is the orchestration-visibility writer (R3): claim →
    dispatch → terminal transitions are recorded for the Director to read. The calls
    are pure side-channel — with the no-op writer the returned summaries are
    byte-identical, so visibility never changes dispatch behavior."""
    state = _RunState(board=board, states=states, status=status, retry_budget=retry_budget,
                      concurrency=concurrency, queue_base=queue_base,
                      workspace_root=workspace_root, command=command, tools=tools,
                      tool_executor=tool_executor, install_skills=install_skills,
                      read_timeout_s=read_timeout_s, timeout_s=timeout_s,
                      approval_policy=approval_policy, sandbox=sandbox, decide=decide,
                      max_turns=max_turns)
    try:
        for ticket in tickets:
            tid = ticket["id"]
            if tid in state.in_flight or tid in state.results:
                continue  # duplicate ready entry this wave — claim/dispatch exactly once
            state.claim_and_submit(ticket, wave=wave)

        last_reconcile = time.monotonic()
        while state.futures:
            # Wake at least every reconcile_interval_s even if no worker finished, so the
            # barrier reconciles in-flight tickets between completions (D-60). `done` is
            # empty on a pure timeout wake.
            done, _ = wait(list(state.futures), timeout=reconcile_interval_s,
                           return_when=FIRST_COMPLETED)
            state.reap(done)
            now = time.monotonic()
            if state.futures and now - last_reconcile >= reconcile_interval_s:
                state.reconcile_in_flight()
                last_reconcile = now
    finally:
        state.shutdown()
    return state.results


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
                stuck = _stuck_report(pending, done)
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


def _idle_wait_s(poll_interval_s: float, idle_streak: int, cap: float) -> float:
    """How long the daemon sleeps before its next poll when fully idle (no workers
    running). Exponential backoff on a quiet board (gap #3, the D-70 seam): the first
    idle tick (streak 0) waits `poll_interval_s`, then doubles each consecutive idle tick
    up to `cap` — `_backoff_s(idle_streak+1, base=poll_interval_s, cap=cap)`. A poll that
    finds/claims work resets the streak to 0 (the caller). A failing poll lands here too
    (futures empty → idle), so poll-failure backoff is subsumed (spec D-77)."""
    return _backoff_s(idle_streak + 1, base=poll_interval_s, cap=cap)


def _daemon_signal_action(shutdown_event: threading.Event,
                          force_event: threading.Event) -> None:
    """One stop signal's effect, factored out so it is testable without real signals
    (D-68): the 1st signal requests a graceful shutdown (stop claiming, drain in-flight);
    a 2nd signal escalates to force (cancel every in-flight worker)."""
    if shutdown_event.is_set():
        force_event.set()
    else:
        shutdown_event.set()


def _install_daemon_signals(shutdown_event: threading.Event,
                            force_event: threading.Event):
    """Install SIGTERM/SIGINT handlers that ONLY flip Events (a handler runs between
    bytecodes on the MAIN thread, so flipping a `threading.Event` is the safe minimum —
    no I/O, no locks; the StatusWriter single-writer invariant R13 is untouched). Returns
    a `restore()` that reinstalls the prior handlers. Must be called on the main thread
    (signal.signal's constraint) — production does; tests pass install_signals=False."""
    def handler(signum, frame):
        _daemon_signal_action(shutdown_event, force_event)
    prev = {sig: signal.signal(sig, handler)
            for sig in (signal.SIGTERM, signal.SIGINT)}

    def restore():
        for sig, h in prev.items():
            signal.signal(sig, h)
    return restore


def run_forever(board, command: list[str], *, team: str, states: dict,
                done_types=("completed",), concurrency: int = 3, queue_base=None,
                workspace_root=run.DEFAULT_WORKSPACE_ROOT, retry_budget: int = 1,
                tools=None, tool_executor=None, install_skills: bool = False,
                read_timeout_s: float = 30.0, timeout_s: float = 300.0, status=None,
                approval_policy: str = "untrusted", sandbox: str = "workspace-write",
                decide=decider.autonomous_decide, max_turns: int = run.DEFAULT_MAX_TURNS,
                reconcile_interval_s: float = config.DEFAULTS["reconcile_interval_s"],
                poll_interval_s: float = config.DEFAULTS["poll_interval_s"],
                backoff_base_s: float = config.DEFAULTS["backoff_base_s"],
                backoff_cap_s: float = config.DEFAULTS["backoff_cap_s"],
                shutdown_event=None, force_event=None, install_signals: bool = True,
                max_ticks: int | None = None) -> dict:
    """The always-on daemon (gap #2): poll → claim ready work into free slots → keep
    ticking forever, never exiting on a drained board (the Symphony identity). Unlike
    the batch wave, this NEVER returns on its own — only a stop signal ends it.

    Each tick (over one daemon-lifetime `_RunState`):
      1. TOP UP — claim ≤ `concurrency - running` ready tickets (bounded top-up, D-64),
         so the board's `In Progress` count equals the running-worker count and each poll
         re-prioritizes. A poll that raises is fail-soft (D-69): skip top-up, survive.
      2. WAIT — two-path (D-67): block on a worker completion up to `poll_interval_s` when
         busy; sleep on the shutdown Event for `_idle_wait_s()` when idle (`wait([], …)`
         returns instantly → would busy-spin).
      3. REAP completed futures → reconcile (retry/terminal), the shared `_RunState.reap`.
      4. RECONCILE in-flight on the `reconcile_interval_s` monotonic cadence (stage 1,
         lifted unchanged).
    When nothing runs and ready work is all blocked, the stuck set is a STATUS signal
    (D-66), never a termination. Graceful shutdown (D-68): the 1st signal sets
    `shutdown_event` (stop claiming, drain in-flight); a 2nd sets `force_event` (cancel
    every in-flight worker via stage 1's cooperative cancel). `shutdown_event`/`force_event`
    are injectable + `install_signals=False` + `max_ticks` so tests drive it without real
    signals. Returns a light session summary `{stopped_reason, polls}` (the per-ticket
    record lives in the bounded status.json, not an unbounded return dict)."""
    shutdown_event = shutdown_event if shutdown_event is not None else threading.Event()
    force_event = force_event if force_event is not None else threading.Event()
    state = _RunState(board=board, states=states, status=status, retry_budget=retry_budget,
                      concurrency=concurrency, queue_base=queue_base,
                      workspace_root=workspace_root, retain_results=False, command=command,
                      tools=tools, tool_executor=tool_executor, install_skills=install_skills,
                      read_timeout_s=read_timeout_s, timeout_s=timeout_s,
                      approval_policy=approval_policy, sandbox=sandbox, decide=decide,
                      max_turns=max_turns)
    restore = _install_daemon_signals(shutdown_event, force_event) if install_signals else None
    done_set = set(done_types)
    last_reconcile = time.monotonic()
    forced = False
    poll_failing = False  # log a board-poll failure once on entry + once on recovery
    idle_streak = 0       # consecutive idle ticks → exponential idle-poll backoff (B)
    pending_retry: dict = {}  # tid -> (ticket, retry_at) — scheduled retry backoff (A)
    claim_retry_at: dict = {}  # tid -> when a claim-failed ticket may be re-admitted (D)
    claim_fails: dict = {}     # tid -> consecutive claim-failure count (exponential input)

    def schedule_retry(ticket):
        # Retry backoff (A, §8.4): instead of re-dispatching now (the batch default), hold
        # the ticket and re-submit after _backoff_s. `attempts` was just bumped in reap, so
        # the first retry (attempts==2) waits `base`. The ticket stays in state.in_flight.
        tid = ticket["id"]
        delay = _backoff_s(state.attempts[tid] - 1, base=backoff_base_s, cap=backoff_cap_s)
        pending_retry[tid] = (ticket, time.monotonic() + delay)

    ticks = 0
    try:
        while True:
            draining = shutdown_event.is_set()
            if draining and not state.futures:
                break  # stopped claiming and all in-flight drained → exit
            if max_ticks is not None and ticks >= max_ticks:
                break
            ticks += 1
            now = time.monotonic()  # one clock per tick (due-retry + reconcile cadence)
            # 2nd signal → cancel every in-flight (running) worker once (cooperative,
            # stage 1). A failed worker's retry can't escape the force-stop: the daemon
            # SCHEDULES retries (not immediate) and the due-retry step is `not draining`-
            # guarded, so a retry queued during the drain is abandoned, never resubmitted
            # (D-81 — this supersedes stage 2's `born_cancelled`).
            if draining and force_event.is_set() and not forced:
                forced = True
                for ev in state.cancel_events.values():
                    ev.set()

            if not draining:
                # DUE RETRIES (A): re-dispatch any pending whose backoff elapsed (now first
                # so they count in futures below). Guarded by `not draining` — a shutdown
                # abandons pending retries (D-81), left In Progress for board-as-truth.
                for tid in [t for t, (_, at) in pending_retry.items() if at <= now]:
                    state.submit(pending_retry.pop(tid)[0])  # → futures; already in_flight
                # TOP UP — bounded by free slots MINUS pending retries (claimed/reserved,
                # D-76): so the board's In-Progress count never exceeds `concurrency`.
                free = concurrency - len(state.futures) - len(pending_retry)
                blocked: list = []
                if free > 0:
                    # CLAIM RE-ADMISSION (D, D-79): a claim that failed is excluded only
                    # until its backoff elapses — re-admit due ones (transient board hiccup
                    # recovers; a permanent failure just retries at most every `cap`).
                    for tid in [t for t in state.claim_failed
                                if now >= claim_retry_at.get(t, now)]:
                        state.claim_failed.discard(tid)
                    try:
                        ready = board.list_ready_issues(team, states["ready"])
                    except Exception as exc:  # transient board error — survive, retry next tick
                        ready = None
                        if not poll_failing:  # log once on entry, not every tick (D-69)
                            poll_failing = True
                            print(json.dumps({"daemon": "poll_failed", "error": str(exc)}),
                                  file=sys.stderr)
                    if ready is not None:
                        if poll_failing:  # recovered — log the transition back
                            poll_failing = False
                            print(json.dumps({"daemon": "poll_recovered"}), file=sys.stderr)
                        eligible = eligible_tickets(ready, done_types=done_types)
                        elig_ids = {t["id"] for t in eligible}
                        claimable = [t for t in eligible if t["id"] not in state.in_flight
                                     and t["id"] not in state.claim_failed]
                        for ticket in claimable[:free]:
                            tid = ticket["id"]
                            if state.claim_and_submit(ticket, wave=ticks):
                                claim_fails.pop(tid, None)       # success → clear claim backoff
                                claim_retry_at.pop(tid, None)
                            else:  # failed claim → schedule a backed-off re-admission (D)
                                claim_fails[tid] = claim_fails.get(tid, 0) + 1
                                claim_retry_at[tid] = now + _backoff_s(
                                    claim_fails[tid], base=backoff_base_s, cap=backoff_cap_s)
                        pending = [t for t in ready if t["id"] not in state.in_flight
                                   and t["id"] not in state.claim_failed]
                        blocked = [t for t in pending if t["id"] not in elig_ids]
                state.status.polled(phase="active" if state.futures else "idle")
                # Refresh the stuck heartbeat every poll so it tracks LIVE state (D-66):
                # the blocked set only when fully idle, else cleared (work IS progressing —
                # not stuck). Without the clear, a resolved stuck set lingers in status.json.
                state.status.stuck(_stuck_report(blocked, done_set) if not state.futures else [])
            else:
                state.status.polled(phase="draining")

            # WAIT — block on a completion when busy; sleep on the shutdown Event when
            # idle (so a shutdown during idle wakes us immediately — no busy-spin, D-67).
            if state.futures:
                idle_streak = 0  # work is running → reset idle backoff (B)
                done, _ = wait(list(state.futures), timeout=poll_interval_s,
                               return_when=FIRST_COMPLETED)
                state.reap(done, on_retry=schedule_retry)  # failed→retry is SCHEDULED (A)
            elif not draining:
                shutdown_event.wait(_idle_wait_s(poll_interval_s, idle_streak, backoff_cap_s))
                idle_streak += 1  # consecutive idle tick → next idle wait doubles (cap)

            # FRESH clock here — the WAIT above can sleep a long time (idle backoff), so the
            # tick-top `now` (used pre-wait for due-retry/claim) is stale for the cadence.
            mono = time.monotonic()
            if state.futures and mono - last_reconcile >= reconcile_interval_s:
                state.reconcile_in_flight()
                last_reconcile = mono
        state.status.finished("shutdown")
        return {"stopped_reason": "shutdown", "polls": ticks}
    finally:
        if restore is not None:
            restore()
        state.shutdown()


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

    def fetch_issue_states_by_ids(self, issue_ids) -> dict:
        """Current {id: {state_id, state_name, state_type}} for the given ids present in
        the board (active-run reconciliation read). Ids absent from the board are
        omitted (the caller never cancels on missing data)."""
        out: dict = {}
        for iid in issue_ids:
            iss = self._issues.get(iid)
            if iss is None:
                continue
            out[iid] = {"state_id": iss["state_id"], "state_name": self.state_name(iid),
                        "state_type": self._state_type(iid)}
        return out


def _build_board(args):
    if args.mock:
        return MockBoard.demo()
    return board_linear.LinearBoard()


def _pick(cli, cfg_value):
    """CLI flag (explicit, non-None) wins over the config value — which already
    carries the built-in default (precedence R4: CLI > config > default)."""
    return cli if cli is not None else cfg_value


def resolve_settings(args, cfg) -> dict:
    """Resolve every run setting CLI > config > default — pure, given the parsed
    args namespace and a `config.DirectorConfig`. The single resolution point both
    `main()` and the tests exercise (precedence R4). `done_types` is the one knob a
    CLI flag delivers as a comma-string vs. the config's tuple."""
    states = {k: _pick(getattr(args, f"{k}_state", None), cfg.states[k])
              for k in ("ready", "started", "done", "failed", "blocked")}
    done_types = (tuple(s.strip() for s in args.done_types.split(",") if s.strip())
                  if args.done_types else cfg.done_types)
    return {
        "team": _pick(args.team, cfg.team), "states": states, "done_types": done_types,
        "concurrency": _pick(args.concurrency, cfg.concurrency),
        "max_turns": _pick(args.max_turns, cfg.max_turns),
        "max_passes": _pick(args.max_passes, cfg.max_passes),
        "max_dispatched": _pick(args.max_dispatched, cfg.max_dispatched),
        "read_timeout_s": _pick(args.read_timeout, cfg.read_timeout_s),
        "turn_review_timeout_s": _pick(args.turn_review_timeout, cfg.turn_review_timeout_s),
        "reconcile_interval_s": _pick(args.reconcile_interval, cfg.reconcile_interval_s),
        "poll_interval_s": _pick(args.poll_interval, cfg.poll_interval_s),
        "backoff_base_s": _pick(args.backoff_base, cfg.backoff_base_s),
        "backoff_cap_s": _pick(args.backoff_cap, cfg.backoff_cap_s),
        "codex_command": _pick(args.codex, cfg.codex_command),
        "workspace_root": _pick(args.workspace_root, cfg.paths.workspace_root),
        "queue_dir": _pick(args.queue_dir, cfg.paths.queue_dir),
        "status_dir": _pick(args.status_dir, cfg.paths.status_dir),
        "posture": cfg.posture,
    }


def _command(args, codex_command, posture) -> list[str]:
    if args.mock:
        return [sys.executable, run._MOCK, args.mock_scenario]
    # Posture (auto_review / network) comes from the resolved config — a host may
    # tighten it in .harness.json director.worker. Exfil deferred (T11).
    # `bash -c` not `-lc`: a login shell would re-inject host profile env past the
    # deny-by-default boundary (run._command has the full rationale; SECURITY.md T11).
    codex = autonomy.codex_command(codex_command, auto_review=posture.auto_review,
                                   network=posture.network)
    return ["bash", "-c", codex]


def main(argv=None, *, board=None) -> int:
    ap = argparse.ArgumentParser(prog="director.orchestrator")
    # config-backed flags default to None (sentinel = "not passed") so the resolver
    # can apply CLI > config > default (R4); the config carries the real defaults.
    ap.add_argument("--team", default=None,
                    help="Linear team id to poll (else director.team in .harness.json)")
    ap.add_argument("--ready-state", default=None)
    ap.add_argument("--started-state", default=None)
    ap.add_argument("--done-state", default=None)
    ap.add_argument("--failed-state", default=None,
                    help="optional workflow state for exhausted failures (else stay started)")
    ap.add_argument("--blocked-state", default=None,
                    help="optional workflow state for a worker-reported blocked terminal "
                         "(else stay started + comment)")
    ap.add_argument("--max-turns", type=int, default=None,
                    help="multi-turn drive bound per ticket (R6); over it → stuck")
    ap.add_argument("--concurrency", type=int, default=None)
    ap.add_argument("--mock", action="store_true", help="in-memory board + fake worker")
    ap.add_argument("--mock-scenario", default="plain",
                    choices=["plain", "approval", "approval_done", "report",
                             "tool", "turn_failed"])
    ap.add_argument("--codex", default=None, help="real worker command")
    ap.add_argument("--queue-dir", default=None)
    ap.add_argument("--workspace-root", default=None)
    ap.add_argument("--tools", choices=["none", "linear"], default="none")
    ap.add_argument("--install-skills", action="store_true")
    ap.add_argument("--once", action="store_true",
                    help="single pass (no re-poll); default is the DAG-aware continuous loop")
    ap.add_argument("--max-passes", type=int, default=None,
                    help="continuous loop safety bound on re-poll passes")
    ap.add_argument("--max-dispatched", type=int, default=None,
                    help="continuous loop safety bound on total tickets dispatched")
    ap.add_argument("--done-types", default=None,
                    help="comma-separated blocker state-types that count as done (unblock)")
    ap.add_argument("--no-status", action="store_true",
                    help="disable the orchestration-visibility snapshot (default: on)")
    ap.add_argument("--status-dir", default=None,
                    help="orchestration-status dir override (default: .claude/harness/director-status)")
    ap.add_argument("--autonomous", action="store_true",
                    help="un-watched: use the code turn-end decider (no live Director "
                         "answers turn ends). Per-action self-governance (on-request + "
                         "auto_review) and full network are shared with the watched default")
    ap.add_argument("--read-timeout", type=float, default=None,
                    help="per-event read timeout for a worker turn (s); raise for slow "
                         "real codex workers that think >30s mid-turn")
    ap.add_argument("--turn-review-timeout", type=float, default=None,
                    help="watched: how long the queue decider waits for the Director to "
                         "answer a turn end before escalating (s)")
    ap.add_argument("--reconcile-interval", type=float, default=None,
                    help="active-run reconciliation cadence (s): how often in-flight "
                         "ticket states are re-read to stop externally-moved tickets")
    ap.add_argument("--daemon", action="store_true",
                    help="continuous always-on loop (run_forever): keep polling forever, "
                         "never exit on drained; stop with SIGTERM / double-SIGINT")
    ap.add_argument("--poll-interval", type=float, default=None,
                    help="daemon (--daemon) board-poll cadence (s): how often new ready "
                         "work is picked up and the idle loop ticks")
    ap.add_argument("--backoff-base", type=float, default=None,
                    help="daemon (--daemon) exponential-backoff base (s) for retry/claim "
                         "re-admission: wait min(base*2^(n-1), cap) (Symphony §8.4)")
    ap.add_argument("--backoff-cap", type=float, default=None,
                    help="daemon (--daemon) exponential-backoff ceiling (s), shared by "
                         "retry / idle-poll / claim re-admission")
    args = ap.parse_args(argv)

    # Load + resolve config FIRST — a malformed .harness.json director block raises
    # here, before any board read or worker dispatch (fail-loud, spec R7).
    cfg = config.load_director_config()
    s = resolve_settings(args, cfg)
    if not s["team"]:
        ap.error("team not configured (set director.team in .harness.json or pass --team)")

    board = board if board is not None else _build_board(args)
    states = resolve_states(board, s["team"], s["states"])

    # Decider selection (spec R5). Watched (default): each turn-end routes to the
    # Director queue and the live main session answers free-form (docs/DIRECTOR.md).
    # Un-watched (--autonomous) and offline (--mock) use the code decider:
    # --mock has no live Director session to answer turnReviews, so the watched queue
    # decider would hang — the code decider self-resolves + trusts the worker proposal.
    decide = (decider.autonomous_decide if (args.autonomous or args.mock)
              else decider.make_queue_decider(base=s["queue_dir"],
                                              timeout_s=s["turn_review_timeout_s"]))

    tools = tool_executor = None
    if args.tools == "linear":
        from director.worker.tools import linear_graphql_spec, make_linear_tool_executor
        tools = [linear_graphql_spec()]
        tool_executor = make_linear_tool_executor()

    kwargs = {"team": s["team"], "states": states, "concurrency": s["concurrency"],
              "queue_base": s["queue_dir"], "tools": tools, "tool_executor": tool_executor,
              "install_skills": args.install_skills, "done_types": s["done_types"],
              "status": None if args.no_status else status_mod.StatusWriter(base=s["status_dir"]),
              # Posture from the resolved config (a host may tighten it in
              # .harness.json director.worker); --autonomous differs only by the decider.
              "approval_policy": s["posture"].approval_policy,
              "sandbox": s["posture"].sandbox,
              "decide": decide, "max_turns": s["max_turns"],
              "read_timeout_s": s["read_timeout_s"],
              "reconcile_interval_s": s["reconcile_interval_s"]}
    if s["workspace_root"]:
        kwargs["workspace_root"] = Path(s["workspace_root"])

    command = _command(args, s["codex_command"], s["posture"])
    if args.daemon:
        # The always-on loop (gap #2): blocks until SIGTERM / double-SIGINT, then returns
        # a session summary. Takes precedence over --once (both → daemon). Signal handlers
        # install by default (main thread); --once/batch bounds (max_passes/dispatched)
        # do not apply — the daemon is unbounded by design.
        result = run_forever(board, command, poll_interval_s=s["poll_interval_s"],
                             backoff_base_s=s["backoff_base_s"],
                             backoff_cap_s=s["backoff_cap_s"], **kwargs)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.once:
        summaries = run_once(board, command, **kwargs)
        for summary in summaries:
            print(json.dumps(summary, ensure_ascii=False))
        return 0 if all(x["status"] != "claim_failed" for x in summaries) else 1

    result = run_until_drained(board, command, max_passes=s["max_passes"],
                               max_dispatched=s["max_dispatched"], **kwargs)
    for s in result["summaries"]:
        print(json.dumps(s, ensure_ascii=False))
    print(json.dumps({"stopped_reason": result["stopped_reason"],
                      "passes": result["passes"], "stuck": result["stuck"]},
                     ensure_ascii=False))
    return 0 if result["stopped_reason"] == "drained" else 1


if __name__ == "__main__":
    raise SystemExit(main())
