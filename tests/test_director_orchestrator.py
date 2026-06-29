import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.director_min as dmin  # noqa: E402
import director.history as dh  # noqa: E402
import director.orchestrator as orch  # noqa: E402
import director.queue as dq  # noqa: E402
import director.board_snapshot as bs  # noqa: E402
import director.run as run  # noqa: E402
import director.status as ds  # noqa: E402
import director.ticket_events as te  # noqa: E402

MOCK = str(Path(run.__file__).resolve().parent / "worker" / "_mock_app_server.py")

# Drive dispositions a faked dispatch returns (the post-R4 contract: dispatch yields a
# disposition, not a turn-status). reconcile EXECUTES these onto the board.
def _done(**extra):
    return {"kind": "terminal", "outcome": {"status": "done", "reason": "ok"},
            "turns": 1, "turn_id": "t", **extra}


def _failed():
    return {"kind": "failed", "status": "failed", "turn_id": None}


class ResolveStatesTest(unittest.TestCase):
    def test_resolves_defaults_to_ids(self):
        states = orch.resolve_states(orch.MockBoard.demo(), "T")
        self.assertEqual(states, {"ready": "st_todo", "started": "st_prog",
                                  "done": "st_done", "failed": None, "blocked": None,
                                  "merging": None})

    def test_missing_state_name_raises_before_dispatch(self):
        with self.assertRaises(RuntimeError):
            orch.resolve_states(orch.MockBoard.demo(), "T", {"ready": "Nope"})

    def test_failed_state_resolved_when_present(self):
        board = orch.MockBoard([], states={
            "Todo": {"id": "st_todo", "type": "unstarted"},
            "In Progress": {"id": "st_prog", "type": "started"},
            "Done": {"id": "st_done", "type": "completed"},
            "Blocked": {"id": "st_block", "type": "started"}})
        states = orch.resolve_states(board, "T", {"failed": "Blocked"})
        self.assertEqual(states["failed"], "st_block")

    def test_configured_failed_state_missing_raises(self):
        with self.assertRaises(RuntimeError):
            orch.resolve_states(orch.MockBoard.demo(), "T", {"failed": "Blocked"})

    def test_merging_state_resolved_when_present(self):
        # merge-gated-eligibility R1: `merging` is an OPTIONAL resolved state (pre-done).
        board = orch.MockBoard([], states={
            "Todo": {"id": "st_todo", "type": "unstarted"},
            "In Progress": {"id": "st_prog", "type": "started"},
            "Done": {"id": "st_done", "type": "completed"},
            "Merging": {"id": "st_merge", "type": "started"}})
        states = orch.resolve_states(board, "T", {"merging": "Merging"})
        self.assertEqual(states["merging"], "st_merge")

    def test_merging_state_none_when_unconfigured(self):
        # absent merging → None → merge-gating inert (today's behavior)
        states = orch.resolve_states(orch.MockBoard.demo(), "T")
        self.assertIsNone(states["merging"])

    def test_configured_merging_state_missing_raises(self):
        with self.assertRaises(RuntimeError):
            orch.resolve_states(orch.MockBoard.demo(), "T", {"merging": "Merging"})


class EligibilityTest(unittest.TestCase):
    def _t(self, tid, blockers):
        return {"id": tid, "identifier": tid, "blockers": blockers}

    def test_no_blockers_eligible(self):
        out = orch.eligible_tickets([self._t("a", [])])
        self.assertEqual([t["id"] for t in out], ["a"])

    def test_blocker_not_done_ineligible(self):
        out = orch.eligible_tickets([self._t("b", [{"id": "a", "state_type": "unstarted"}])])
        self.assertEqual(out, [])

    def test_blocker_completed_eligible(self):
        out = orch.eligible_tickets([self._t("b", [{"id": "a", "state_type": "completed"}])])
        self.assertEqual([t["id"] for t in out], ["b"])

    def test_canceled_blocker_ineligible_by_default(self):
        out = orch.eligible_tickets([self._t("b", [{"id": "a", "state_type": "canceled"}])])
        self.assertEqual(out, [])  # default done_types = {completed}

    def test_done_types_configurable(self):
        out = orch.eligible_tickets([self._t("b", [{"id": "a", "state_type": "canceled"}])],
                                    done_types=("completed", "canceled"))
        self.assertEqual([t["id"] for t in out], ["b"])

    def test_all_blockers_must_be_done(self):
        out = orch.eligible_tickets([self._t("c", [{"id": "a", "state_type": "completed"},
                                                   {"id": "b", "state_type": "unstarted"}])])
        self.assertEqual(out, [])

    def test_require_label_drops_without_agent_ready(self):
        # F1 (ADR 0009): with require_label, ONLY a ticket carrying the `agent-ready`
        # dispatch label survives — an unlabeled ticket AND a ticket with some OTHER label
        # (a stray board label) are both dropped, so non-harness tickets never dispatch.
        ready = {"id": "b", "identifier": "b", "blockers": [], "labels": ["agent-ready"]}
        unlabeled = self._t("a", [])                                   # no 'labels' key
        other = {"id": "c", "identifier": "c", "blockers": [], "labels": ["Bug"]}
        out = orch.eligible_tickets([unlabeled, ready, other], require_label=True)
        self.assertEqual([t["id"] for t in out], ["b"])

    def test_require_label_default_off_keeps_unlabeled(self):
        # The eligible_tickets PRIMITIVE defaults require_label=False (dispatch everything);
        # the config layer is what defaults the gate ON (see test_director_config).
        out = orch.eligible_tickets([self._t("a", [])])
        self.assertEqual([t["id"] for t in out], ["a"])

    def test_run_once_require_label_skips_without_agent_ready(self):
        # End-to-end: run_once threads dispatch_requires_label into eligible_tickets, so a
        # ready ticket WITHOUT the agent-ready label is never handed to dispatch.
        board = orch.MockBoard([
            {"id": "a", "identifier": "A", "title": "t", "description": "d",
             "prompt": "pa", "state_id": "st_todo"},  # unlabeled
            {"id": "b", "identifier": "B", "title": "t", "description": "d",
             "prompt": "pb", "state_id": "st_todo", "labels": ["agent-ready"]}])
        states = orch.resolve_states(board, "T")
        seen = []

        def fake(ticket, **kw):
            seen.append(ticket["id"])
            return _done()

        with mock.patch("director.orchestrator.dispatch", fake):
            res = orch.run_once(board, command=["x"], team="T", states=states,
                                dispatch_requires_label=True)
        self.assertEqual(seen, ["b"])  # A (unlabeled) skipped
        self.assertEqual([r["ticket"] for r in res], ["B"])

    def test_run_once_skips_blocked_ticket(self):
        board = orch.MockBoard([
            {"id": "a", "identifier": "A", "title": "t", "description": "d",
             "prompt": "pa", "state_id": "st_todo"},
            {"id": "b", "identifier": "B", "title": "t", "description": "d",
             "prompt": "pb", "state_id": "st_todo", "blockers": ["a"]}])
        states = orch.resolve_states(board, "T")
        seen = []

        def fake(ticket, **kw):
            seen.append(ticket["id"])
            return _done()

        with mock.patch("director.orchestrator.dispatch", fake):
            res = orch.run_once(board, command=["x"], team="T", states=states)
        self.assertEqual(seen, ["a"])  # B is blocked by A (still Todo) — not dispatched
        self.assertEqual([r["ticket"] for r in res], ["A"])


class RunOnceEndToEndTest(unittest.TestCase):
    """The headline integration: a real mock app-server worker per ticket, a watched
    auto_respond answering approvals, the board moved Todo→In Progress→Done."""

    def test_two_tickets_dispatched_reconciled_with_watched_responder(self):
        board = orch.MockBoard.demo()
        states = orch.resolve_states(board, "T")
        with tempfile.TemporaryDirectory() as tmp:
            qbase = Path(tmp) / "q"
            stop = threading.Event()
            responder = threading.Thread(
                target=dmin.auto_respond, kwargs={"base": qbase, "stop": stop})
            responder.start()
            try:
                res = orch.run_once(
                    board, command=[sys.executable, MOCK, "approval_done"],
                    team="T", states=states, concurrency=2,
                    queue_base=qbase, workspace_root=Path(tmp) / "ws")
            finally:
                stop.set()
                responder.join(timeout=5)

            # Read the queue BEFORE the tmp dir is cleaned up (read_requests
            # tolerates a missing file, so a post-cleanup read silently returns []).
            reqs = dq.read_requests(base=qbase)
            answered = [dq.read_answer(r["request_id"], base=qbase) for r in reqs]

        self.assertEqual({r["status"] for r in res}, {"completed"})
        self.assertEqual(board.state_name("u1"), "Done")
        self.assertEqual(board.state_name("u2"), "Done")
        self.assertTrue(board.comments["u1"] and board.comments["u2"])
        # each ticket: claim (In Progress) then reconcile (Done)
        self.assertEqual(board.transitions["u1"], ["st_prog", "st_done"])
        # both approvals queued and answered, no corruption
        self.assertEqual(len(reqs), 2)
        self.assertTrue(all(answered))


class TelemetryPersistenceTest(unittest.TestCase):
    def test_run_once_persists_telemetry_to_status_snapshot(self):
        # M3 end-to-end: a 2-ticket run over the `usage` mock scenario fills
        # status.json with per-ticket tokens and a summed run aggregate — the whole
        # producer path (app_server → drive → reconcile → StatusWriter).
        board = orch.MockBoard.demo()  # u1, u2 ready
        states = orch.resolve_states(board, "T")
        with tempfile.TemporaryDirectory() as tmp:
            sdir = Path(tmp) / "s"
            w = ds.StatusWriter(base=sdir)
            res = orch.run_once(board, command=[sys.executable, MOCK, "usage"],
                                team="T", states=states, concurrency=2,
                                workspace_root=Path(tmp) / "ws", status=w)
            snap = ds.read_status(base=sdir)
        assert snap is not None  # the run wrote it
        self.assertEqual({r["status"] for r in res}, {"completed"})
        # each ticket ran one turn → its own worker process reported absolute total 100
        toks = [r["tokens"] for r in snap["recent"]]
        self.assertEqual(len(toks), 2)
        self.assertTrue(all(t == {"input": 60, "output": 40, "total": 100} for t in toks))
        self.assertTrue(all(r["session_id"] for r in snap["recent"]))
        # run aggregate = sum across the 2 tickets; runtime is a live non-negative aggregate
        self.assertEqual(snap["run"]["codex_totals"]["total"], 200)
        self.assertGreaterEqual(snap["run"]["codex_totals"]["seconds_running"], 0.0)


class CrossRunHistoryHookTest(unittest.TestCase):
    """Phase B (R7): a completed run appends ONE summary record to the cross-run history,
    derived from the final snapshot — and a Noop (visibility-off) run writes nothing."""

    def _run(self, status, hbase, tmp):
        board = orch.MockBoard.demo()  # u1, u2 ready
        states = orch.resolve_states(board, "T")
        orch.run_until_drained(board, command=[sys.executable, MOCK, "usage"],
                               team="T", states=states, concurrency=2,
                               workspace_root=Path(tmp) / "ws", status=status,
                               history_base=hbase)

    def test_run_until_drained_appends_one_history_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            hbase = Path(tmp) / "h"
            self._run(ds.StatusWriter(base=Path(tmp) / "s"), hbase, tmp)
            recs = dh.read_history(base=hbase)
        self.assertEqual(len(recs), 1)
        rec = recs[0]
        self.assertEqual(rec["stopped_reason"], "drained")
        self.assertEqual(rec["codex_totals"]["total"], 200)   # 2 tickets × absolute 100
        self.assertEqual(rec["outcomes"].get("completed"), 2)
        self.assertEqual(rec["ticket_count"], 2)

    def test_noop_status_writes_no_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            hbase = Path(tmp) / "h"
            self._run(None, hbase, tmp)  # status=None → NoopStatusWriter
            self.assertEqual(dh.read_history(base=hbase), [])  # history is off when visibility is off


class _RecordingStatus:
    """A StatusWriter spy: records accrue() calls; every other transition is a no-op.
    Lets a test assert the marshal touches the writer ONLY via accrue, on the main thread."""
    def __init__(self):
        self.accrued = []

    def accrue(self, tid, usage):
        self.accrued.append((tid, usage))

    def __getattr__(self, _name):
        return lambda *a, **k: None


def _usage_event(total):
    # the absolute-total wrapper extract_usage trusts on any event (§13.5).
    return {"method": "thread/tokenUsage/updated",
            "params": {"total_token_usage": {"input": total, "output": 0, "total": total}}}


class Layer2AccrualMarshalTest(unittest.TestCase):
    """M2: per-event usage is observed on the worker-pool thread but applied to the
    StatusWriter ONLY on the main thread (R13), via a thread-safe queue (R16)."""

    def _state(self, status):
        return orch._RunState(board=None, states={}, status=status, retry_budget=0,
                              concurrency=1, queue_base=None, workspace_root=None)

    def test_enqueue_usage_only_puts_never_touches_writer(self):
        # R13: the worker-thread callback ONLY enqueues — it never calls a writer method.
        spy = _RecordingStatus()
        state = self._state(spy)
        try:
            state._enqueue_usage("u1", _usage_event(100))
            self.assertEqual(spy.accrued, [])              # writer untouched off the main thread
            tid, usage = state.accrual.get_nowait()
            self.assertEqual((tid, usage["total"]), ("u1", 100))
            state._enqueue_usage("u1", {"method": "item/completed", "params": {}})  # no usage
            self.assertTrue(state.accrual.empty())          # extract_usage → None → nothing enqueued
        finally:
            state.shutdown()

    def test_enqueue_usage_is_exception_total_never_gates_the_turn(self):
        # review-reliability P2: the callback fires inside run_turn's read loop, which
        # does NOT isolate it — a raise would propagate up and fail a healthy turn. It
        # must be exception-total: a hiccup drops silently, never raises, never enqueues.
        spy = _RecordingStatus()
        state = self._state(spy)
        try:
            with mock.patch("director.orchestrator.app_server.extract_usage",
                            side_effect=RuntimeError("boom")):
                state._enqueue_usage("u1", _usage_event(100))  # must NOT raise
            self.assertTrue(state.accrual.empty())  # nothing enqueued on the hiccup
            self.assertEqual(spy.accrued, [])
        finally:
            state.shutdown()

    def test_drain_accrual_coalesces_latest_per_tid_on_main_thread(self):
        # Coalesce: many queued events for a tid → ONE accrue with the LATEST usage
        # (bounds status.json rewrites to ~one per tick); applied on the main thread.
        spy = _RecordingStatus()
        state = self._state(spy)
        try:
            state.accrual.put(("u1", {"input": 1, "output": 1, "total": 100}))
            state.accrual.put(("u1", {"input": 1, "output": 1, "total": 250}))  # newer
            state.accrual.put(("u2", {"input": 1, "output": 1, "total": 70}))
            state.drain_accrual()
            self.assertEqual({tid: u["total"] for tid, u in spy.accrued}, {"u1": 250, "u2": 70})
            self.assertEqual(len(spy.accrued), 2)            # 3 events coalesced to 2 accrues
            self.assertTrue(state.accrual.empty())           # fully drained
        finally:
            state.shutdown()

    def test_live_accrual_end_to_end_through_drain(self):
        # The full marshal against a REAL StatusWriter, deterministically (no subprocess
        # race): claim → enqueue usage (as a worker would) → drain → snapshot shows the
        # in-flight ticket's LIVE tokens AND the run total including them, before terminal.
        with tempfile.TemporaryDirectory() as tmp:
            sdir = Path(tmp) / "s"
            w = ds.StatusWriter(base=sdir)
            state = self._state(w)
            try:
                w.claimed({"id": "u1", "identifier": "D-1"}, wave=1, attempt=1)
                state._enqueue_usage("u1", _usage_event(100))
                state.drain_accrual()
                snap = ds.read_status(base=sdir)
                self.assertEqual(snap["in_flight"][0]["tokens"]["total"], 100)
                self.assertEqual(snap["run"]["codex_totals"]["total"], 100)  # live, pre-terminal
            finally:
                state.shutdown()


class TicketEventCaptureWiringTest(unittest.TestCase):
    """M2: the per-ticket on_event fan-out records the NORMALIZED play-by-play to the
    event log AND still marshals usage — and a Noop writer leaves no trace (off-path)."""

    def _state(self, status, events):
        return orch._RunState(board=None, states={}, status=status, events=events,
                              retry_budget=0, concurrency=1, queue_base=None, workspace_root=None)

    def test_observe_event_records_normalized_events_and_marshals_usage(self):
        d = tempfile.mkdtemp(prefix="te_wire_")
        state = self._state(_RecordingStatus(), te.TicketEventWriter(d))
        try:
            state._observe_event("LIN-9", {"method": "turn/started", "params": {"turn": {"id": "u1"}}})
            state._observe_event("LIN-9", {"method": "item/completed",
                                           "params": {"item": {"type": "agentMessage", "text": "hi", "phase": "commentary"}}})
            state._observe_event("LIN-9", _usage_event(100))   # also lands on the accrual queue
            evs = te.read_events("LIN-9", base=d)
            self.assertEqual([e["kind"] for e in evs], ["turn_started", "agent_message", "token_usage"])
            self.assertEqual(state.accrual.get_nowait()[0], "LIN-9")  # usage still marshaled (R13)
        finally:
            state.shutdown()

    def test_noop_event_writer_leaves_no_trace(self):
        d = tempfile.mkdtemp(prefix="te_noop_")
        state = self._state(_RecordingStatus(), te.NoopTicketEventWriter())
        try:
            state._observe_event("LIN-9", {"method": "turn/started", "params": {"turn": {"id": "u1"}}})
            self.assertEqual(te.read_events("LIN-9", base=d), [])   # off-path: nothing written
        finally:
            state.shutdown()

    def test_observe_event_exception_total_never_gates_turn(self):
        # A raise in the event-record path must not propagate (it fires inside run_turn's
        # read loop, like _enqueue_usage). Force record() to blow up → _observe_event swallows.
        state = self._state(_RecordingStatus(), te.TicketEventWriter(tempfile.mkdtemp(prefix="te_x_")))
        try:
            with mock.patch.object(state.events, "record", side_effect=RuntimeError("boom")):
                state._observe_event("LIN-9", _usage_event(100))   # must NOT raise
            self.assertEqual(state.accrual.get_nowait()[0], "LIN-9")  # usage path still ran first
        finally:
            state.shutdown()


class RunOnceConcurrencyTest(unittest.TestCase):
    def test_concurrency_cap_is_respected(self):
        # 5 ready tickets, cap 2: never more than 2 dispatch calls live at once.
        issues = [{"id": f"u{i}", "identifier": f"D-{i}", "title": "t",
                   "description": "d", "prompt": f"p{i}", "state_id": "st_todo"}
                  for i in range(5)]
        board = orch.MockBoard(issues)
        states = orch.resolve_states(board, "T")
        live = {"now": 0, "max": 0}
        guard = threading.Lock()

        def fake_dispatch(ticket, **kw):
            with guard:
                live["now"] += 1
                live["max"] = max(live["max"], live["now"])
            time.sleep(0.05)
            with guard:
                live["now"] -= 1
            return _done()

        with mock.patch("director.orchestrator.dispatch", fake_dispatch):
            res = orch.run_once(board, command=["x"], team="T", states=states,
                                concurrency=2)
        self.assertEqual(len(res), 5)
        self.assertEqual({r["status"] for r in res}, {"completed"})
        self.assertLessEqual(live["max"], 2)


class RunOnceRetryTest(unittest.TestCase):
    def test_failure_retried_once_then_failed(self):
        board = orch.MockBoard([{"id": "u1", "identifier": "D-1", "title": "t",
                                 "description": "d", "prompt": "p", "state_id": "st_todo"}])
        states = orch.resolve_states(board, "T")
        calls = {"u1": 0}

        def always_fail(ticket, **kw):
            calls[ticket["id"]] += 1
            return _failed()

        with mock.patch("director.orchestrator.dispatch", always_fail):
            res = orch.run_once(board, command=["x"], team="T", states=states,
                                concurrency=1, retry_budget=1)
        self.assertEqual(calls["u1"], 2)  # initial + one retry
        self.assertEqual(res[0]["status"], "failed")
        self.assertEqual(res[0]["attempts"], 2)
        self.assertEqual(res[0]["final_state"], "started")  # no failed state configured
        self.assertTrue(board.comments["u1"])  # failure comment posted

    def test_failed_state_used_when_configured(self):
        board = orch.MockBoard(
            [{"id": "u1", "identifier": "D-1", "title": "t", "description": "d",
              "prompt": "p", "state_id": "st_todo"}],
            states={**orch.MockBoard.STATES, "Blocked": {"id": "st_block", "type": "started"}})
        states = orch.resolve_states(board, "T", {"failed": "Blocked"})
        with mock.patch("director.orchestrator.dispatch",
                        lambda ticket, **kw: _failed()):
            res = orch.run_once(board, command=["x"], team="T", states=states,
                                concurrency=1, retry_budget=0)
        self.assertEqual(res[0]["final_state"], "failed")
        self.assertEqual(board.state_name("u1"), "Blocked")


class RunOnceErrorPathsTest(unittest.TestCase):
    def test_claim_failure_skips_dispatch(self):
        board = orch.MockBoard(
            [{"id": "u1", "identifier": "D-1", "title": "t", "description": "d",
              "prompt": "p", "state_id": "st_todo"}], fail_state_for={"u1"})
        states = orch.resolve_states(board, "T")
        with mock.patch("director.orchestrator.dispatch") as disp:
            res = orch.run_once(board, command=["x"], team="T", states=states)
        disp.assert_not_called()
        self.assertEqual(res[0]["status"], "claim_failed")

    def test_reconcile_write_failure_recorded_not_raised(self):
        class FailDone(orch.MockBoard):
            def update_issue_state(self, issue_id, state_id):
                if state_id == "st_done":
                    raise RuntimeError("boom on done")
                return super().update_issue_state(issue_id, state_id)

        board = FailDone([{"id": "u1", "identifier": "D-1", "title": "t",
                           "description": "d", "prompt": "p", "state_id": "st_todo"}])
        states = orch.resolve_states(board, "T")
        with mock.patch("director.orchestrator.dispatch",
                        lambda ticket, **kw: _done()):
            res = orch.run_once(board, command=["x"], team="T", states=states)
        self.assertEqual(res[0]["status"], "completed")
        self.assertIn("reconcile_error", res[0])

    def test_claim_returning_false_skips_dispatch(self):
        # A board that returns False (not raises) on the claim write must not dispatch.
        class RejectClaim(orch.MockBoard):
            def update_issue_state(self, issue_id, state_id):
                if state_id == "st_prog":
                    return False
                return super().update_issue_state(issue_id, state_id)

        board = RejectClaim([{"id": "u1", "identifier": "D-1", "title": "t",
                              "description": "d", "prompt": "p", "state_id": "st_todo"}])
        states = orch.resolve_states(board, "T")
        with mock.patch("director.orchestrator.dispatch") as disp:
            res = orch.run_once(board, command=["x"], team="T", states=states)
        disp.assert_not_called()
        self.assertEqual(res[0]["status"], "claim_failed")
        self.assertIn("False", res[0]["error"])

    def test_reconcile_false_write_recorded_as_error(self):
        # update_issue_state returning False (GraphQL success:false) on the done
        # transition must surface as reconcile_error, not a silent "done".
        class RejectDone(orch.MockBoard):
            def update_issue_state(self, issue_id, state_id):
                if state_id == "st_done":
                    return False
                return super().update_issue_state(issue_id, state_id)

        board = RejectDone([{"id": "u1", "identifier": "D-1", "title": "t",
                             "description": "d", "prompt": "p", "state_id": "st_todo"}])
        states = orch.resolve_states(board, "T")
        with mock.patch("director.orchestrator.dispatch",
                        lambda ticket, **kw: _done()):
            res = orch.run_once(board, command=["x"], team="T", states=states)
        self.assertEqual(res[0]["status"], "completed")
        self.assertIn("reconcile_error", res[0])
        self.assertIn("False", res[0]["reconcile_error"])

    def test_duplicate_ready_entry_dispatched_once(self):
        # A duplicate id in the ready set (e.g. a future Phase-3 DAG union) is
        # claimed/dispatched exactly once.
        class DupBoard(orch.MockBoard):
            def list_ready_issues(self, team, ready_state_id):
                one = super().list_ready_issues(team, ready_state_id)
                return one + one  # same issue twice

        board = DupBoard([{"id": "u1", "identifier": "D-1", "title": "t",
                           "description": "d", "prompt": "p", "state_id": "st_todo"}])
        states = orch.resolve_states(board, "T")
        calls = {"n": 0}

        def fake(ticket, **kw):
            calls["n"] += 1
            return _done()

        with mock.patch("director.orchestrator.dispatch", fake):
            res = orch.run_once(board, command=["x"], team="T", states=states)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(len(res), 1)

    def test_terminal_with_unknown_outcome_not_marked_done(self):
        # R4 guard: a terminal disposition with an unrecognized outcome status must
        # NOT silently mark Done — it stays visible for review (review fix).
        board = orch.MockBoard([{"id": "u1", "identifier": "D-1", "title": "t",
                                 "description": "d", "prompt": "p", "state_id": "st_todo"}])
        states = orch.resolve_states(board, "T")
        with mock.patch("director.orchestrator.dispatch",
                        lambda ticket, **kw: {"kind": "terminal",
                                              "outcome": {"status": "weird"}, "turns": 1}):
            res = orch.run_once(board, command=["x"], team="T", states=states)
        self.assertEqual(res[0]["status"], "terminal_unknown")
        self.assertEqual(res[0]["final_state"], "started")
        self.assertNotEqual(board.state_name("u1"), "Done")  # never falsely completed


def _issue(tid, blockers=None, state="st_todo", labels=None):
    d = {"id": tid, "identifier": tid.upper(), "title": "t", "description": "d",
         "prompt": f"p-{tid}", "state_id": state}
    if blockers:
        d["blockers"] = blockers
    # A dispatchable mock ticket carries the agent-ready label (ADR 0009: the dispatch gate
    # is on by default). Callers pass `labels` explicitly only to test a different set.
    d["labels"] = list(labels) if labels else ["agent-ready"]
    return d


def _completing_dispatch(order):
    def fake(ticket, **kw):
        order.append(ticket["id"])
        return _done()
    return fake


class RunUntilDrainedTest(unittest.TestCase):
    def test_chain_drains_in_order(self):
        board = orch.MockBoard([_issue("a"), _issue("b", ["a"]), _issue("c", ["b"])])
        states = orch.resolve_states(board, "T")
        order = []
        with mock.patch("director.orchestrator.dispatch", _completing_dispatch(order)):
            out = orch.run_until_drained(board, command=["x"], team="T", states=states,
                                         concurrency=2)
        self.assertEqual(order, ["a", "b", "c"])  # each only after its blocker done
        self.assertEqual(out["stopped_reason"], "drained")
        self.assertEqual(len(out["summaries"]), 3)
        self.assertEqual(board.state_name("c"), "Done")

    def test_diamond_dispatches_middle_in_parallel(self):
        board = orch.MockBoard([_issue("a"), _issue("b", ["a"]), _issue("c", ["a"]),
                                _issue("d", ["b", "c"])])
        states = orch.resolve_states(board, "T")
        order = []
        with mock.patch("director.orchestrator.dispatch", _completing_dispatch(order)):
            out = orch.run_until_drained(board, command=["x"], team="T", states=states,
                                         concurrency=2)
        self.assertEqual(order[0], "a")
        self.assertEqual(set(order[1:3]), {"b", "c"})  # b,c same wave (both unblocked by a)
        self.assertEqual(order[3], "d")
        self.assertEqual(out["stopped_reason"], "drained")

    def test_failed_blocker_leaves_dependent_stuck(self):
        board = orch.MockBoard([_issue("a"), _issue("b", ["a"])])
        states = orch.resolve_states(board, "T")
        with mock.patch("director.orchestrator.dispatch",
                        lambda ticket, **kw: _failed()):
            out = orch.run_until_drained(board, command=["x"], team="T", states=states)
        self.assertEqual(out["stopped_reason"], "stuck")
        # B blocked by failed A; stuck reports the unmet blocker (A now in 'started')
        self.assertEqual([s["ticket"] for s in out["stuck"]], ["B"])
        self.assertEqual(out["stuck"][0]["blocked_by"][0]["id"], "a")
        self.assertEqual(out["stuck"][0]["blocked_by"][0]["state_type"], "started")

    def test_cycle_terminates_stuck_without_hang(self):
        board = orch.MockBoard([_issue("a", ["b"]), _issue("b", ["a"])])
        states = orch.resolve_states(board, "T")
        order = []
        with mock.patch("director.orchestrator.dispatch", _completing_dispatch(order)):
            out = orch.run_until_drained(board, command=["x"], team="T", states=states)
        self.assertEqual(order, [])  # neither ever eligible
        self.assertEqual(out["stopped_reason"], "stuck")
        self.assertEqual({s["ticket"] for s in out["stuck"]}, {"A", "B"})

    def test_poll_failure_terminates_cleanly(self):
        class BadPoll(orch.MockBoard):
            def list_ready_issues(self, team, ready_state_id):
                raise RuntimeError("network down")

        board = BadPoll([_issue("a")])
        states = orch.resolve_states(board, "T")
        out = orch.run_until_drained(board, command=["x"], team="T", states=states)
        self.assertEqual(out["stopped_reason"], "poll_failed")
        self.assertIn("network down", out["error"])  # error surfaced, not a crash

    def test_max_dispatched_bound_counts_only_real_dispatches(self):
        board = orch.MockBoard([_issue("a"), _issue("b", ["a"]), _issue("c", ["b"])])
        states = orch.resolve_states(board, "T")
        order = []
        with mock.patch("director.orchestrator.dispatch", _completing_dispatch(order)):
            out = orch.run_until_drained(board, command=["x"], team="T", states=states,
                                         max_dispatched=2)
        self.assertEqual(out["stopped_reason"], "max_dispatched")
        self.assertEqual(order, ["a", "b"])  # 2 dispatched, then the bound stops C

    def test_worker_created_ticket_picked_up(self):
        class GrowingBoard(orch.MockBoard):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                self._polls = 0

            def list_ready_issues(self, team, ready_state_id):
                self._polls += 1
                if self._polls == 2:  # a worker "created" D after the first pass
                    self._issues["d"] = _issue("d")
                return super().list_ready_issues(team, ready_state_id)

        board = GrowingBoard([_issue("a")])
        states = orch.resolve_states(board, "T")
        order = []
        with mock.patch("director.orchestrator.dispatch", _completing_dispatch(order)):
            out = orch.run_until_drained(board, command=["x"], team="T", states=states)
        self.assertIn("d", order)  # the mid-run ticket was dispatched
        self.assertEqual(out["stopped_reason"], "drained")

    def test_max_passes_bound_terminates(self):
        board = orch.MockBoard([_issue("a"), _issue("b", ["a"]), _issue("c", ["b"])])
        states = orch.resolve_states(board, "T")
        order = []
        with mock.patch("director.orchestrator.dispatch", _completing_dispatch(order)):
            out = orch.run_until_drained(board, command=["x"], team="T", states=states,
                                         max_passes=2)
        self.assertEqual(out["stopped_reason"], "max_passes")
        self.assertEqual(out["passes"], 2)
        self.assertEqual(order, ["a", "b"])  # c never reached


class DispatchPromptTest(unittest.TestCase):
    """ADR 0009: the dispatch label (`agent-ready`) only ADMITS a ticket; it never shapes the
    prompt — dispatch passes the ticket's own prompt through unchanged. DAG sequencing is pure
    `blocked_by` (the removed dev-stage taxonomy never typed it)."""

    def test_dispatch_passes_prompt_raw(self):
        captured = {}

        def fake_drive(ticket, **kw):
            captured["prompt"] = ticket["prompt"]
            return _done()

        with mock.patch("director.orchestrator.run.drive", fake_drive):
            orch.dispatch(_issue("a"), command=["x"])
        self.assertEqual(captured["prompt"], "p-a")           # raw, no template wrapping
        self.assertNotIn("product-design", captured["prompt"])
        self.assertNotIn("TASK:", captured["prompt"])

    def test_pipeline_sequenced_by_dag_not_by_label(self):
        # Sequencing is the blocked_by chain alone — every ticket carries the SAME agent-ready
        # label, yet they still drain in dependency order. ADR 0009: the label admits; the DAG
        # orders. Each worker receives its ticket's raw prompt.
        board = orch.MockBoard([
            _issue("plan"),
            _issue("design", ["plan"]),
            _issue("spec", ["design"]),
            _issue("impl", ["spec"])])
        states = orch.resolve_states(board, "T")
        seen = []

        def fake_drive(ticket, **kw):
            seen.append((ticket["id"], ticket["prompt"]))
            return _done()

        with mock.patch("director.orchestrator.run.drive", fake_drive):
            out = orch.run_until_drained(board, command=["x"], team="T", states=states)
        self.assertEqual([s[0] for s in seen], ["plan", "design", "spec", "impl"])  # DAG order
        prompts = dict(seen)
        for tid in ("plan", "design", "spec", "impl"):       # each prompt is raw (no template)
            self.assertEqual(prompts[tid], f"p-{tid}")
            self.assertNotIn("TASK:", prompts[tid])
        self.assertEqual(out["stopped_reason"], "drained")


class MainCliTest(unittest.TestCase):
    def test_main_mock_runs_and_reconciles(self):
        # --autonomous: an offline mock run has no live Director to answer turn reviews,
        # so it uses the code decider; the `report` worker signals report_outcome(done).
        board = orch.MockBoard.demo()
        with tempfile.TemporaryDirectory() as q, tempfile.TemporaryDirectory() as ws:
            rc = orch.main(["--team", "T", "--mock", "--mock-scenario", "report",
                            "--autonomous", "--queue-dir", q, "--workspace-root", ws,
                            "--concurrency", "2", "--no-status"], board=board)
        self.assertEqual(rc, 0)
        self.assertEqual(board.state_name("u1"), "Done")
        self.assertEqual(board.state_name("u2"), "Done")

    def test_main_once_skips_blocked(self):
        board = orch.MockBoard([_issue("a"), _issue("b", ["a"])])
        with tempfile.TemporaryDirectory() as q, tempfile.TemporaryDirectory() as ws:
            rc = orch.main(["--team", "T", "--mock", "--mock-scenario", "report", "--once",
                            "--autonomous", "--queue-dir", q, "--workspace-root", ws,
                            "--no-status"], board=board)
        self.assertEqual(rc, 0)
        self.assertEqual(board.state_name("a"), "Done")
        self.assertEqual(board.state_name("b"), "Todo")  # single pass: B stays blocked

    def test_main_continuous_drains_chain(self):
        board = orch.MockBoard([_issue("a"), _issue("b", ["a"])])
        with tempfile.TemporaryDirectory() as q, tempfile.TemporaryDirectory() as ws:
            rc = orch.main(["--team", "T", "--mock", "--mock-scenario", "report",
                            "--autonomous", "--queue-dir", q, "--workspace-root", ws,
                            "--no-status"], board=board)
        self.assertEqual(rc, 0)
        self.assertEqual(board.state_name("a"), "Done")
        self.assertEqual(board.state_name("b"), "Done")  # continuous: A unblocks B

    def test_main_daemon_routes_to_run_forever_with_resolved_poll_interval(self):
        # --daemon routes to run_forever (not the batch paths); --poll-interval (CLI) wins
        # over config/default. run_forever is mocked so the CLI test never loops forever
        # or installs real signal handlers.
        board = orch.MockBoard.demo()
        with mock.patch("director.orchestrator.run_forever",
                        return_value={"stopped_reason": "shutdown", "polls": 0}) as rf:
            with tempfile.TemporaryDirectory() as q, tempfile.TemporaryDirectory() as ws:
                rc = orch.main(["--team", "T", "--mock", "--daemon", "--poll-interval", "2",
                                "--autonomous", "--queue-dir", q, "--workspace-root", ws,
                                "--no-status"], board=board)
        self.assertEqual(rc, 0)
        rf.assert_called_once()
        self.assertEqual(rf.call_args.kwargs["poll_interval_s"], 2.0)

    def test_main_writes_status_snapshot_to_status_dir(self):
        board = orch.MockBoard([_issue("a"), _issue("b", ["a"])])
        with tempfile.TemporaryDirectory() as q, tempfile.TemporaryDirectory() as ws, \
                tempfile.TemporaryDirectory() as st:
            rc = orch.main(["--team", "T", "--mock", "--mock-scenario", "report",
                            "--autonomous", "--queue-dir", q, "--workspace-root", ws,
                            "--status-dir", st], board=board)
            snap = ds.read_status(base=st)
        self.assertEqual(rc, 0)
        # chain drained: snapshot survives, empty in_flight, both tickets in recent,
        # run finished as drained.
        assert snap is not None
        self.assertEqual(snap["in_flight"], [])
        self.assertEqual(snap["run"]["stopped_reason"], "drained")
        self.assertEqual({r["ticket_id"] for r in snap["recent"]}, {"a", "b"})


class OrchestrationVisibilityTest(unittest.TestCase):
    """M2: the orchestrator records its run state to the status snapshot the Director
    reads (R1/R5), and visibility is read-only — off → byte-identical (R3)."""

    def _chain_board(self):
        return orch.MockBoard([_issue("a"), _issue("b", ["a"])])

    def test_status_off_keeps_summaries_byte_identical(self):
        def drive(board, status):
            states = orch.resolve_states(board, "T")
            with mock.patch("director.orchestrator.dispatch", _completing_dispatch([])):
                return orch.run_until_drained(board, command=["x"], team="T",
                                              states=states, status=status)
        off = drive(self._chain_board(), None)
        with tempfile.TemporaryDirectory() as st:
            on = drive(self._chain_board(), ds.StatusWriter(base=st))
        self.assertEqual(off["summaries"], on["summaries"])  # visibility never alters dispatch
        self.assertEqual(off["stopped_reason"], on["stopped_reason"])

    def test_snapshot_shows_ticket_in_flight_during_dispatch(self):
        board = orch.MockBoard([_issue("a")])
        states = orch.resolve_states(board, "T")
        with tempfile.TemporaryDirectory() as st:
            seen = {}

            def capturing(ticket, **kw):
                # the worker reads the snapshot mid-turn: its own ticket is in flight
                snap = ds.read_status(base=st)
                seen["in_flight"] = snap["in_flight"] if snap else None
                return _done()

            with mock.patch("director.orchestrator.dispatch", capturing):
                orch.run_until_drained(board, command=["x"], team="T", states=states,
                                       status=ds.StatusWriter(base=st))
            # and after drain: nothing in flight, the ticket terminal in recent
            final = ds.read_status(base=st)
        assert final is not None
        self.assertEqual([e["ticket_id"] for e in seen["in_flight"]], ["a"])
        self.assertEqual(final["in_flight"], [])
        self.assertEqual([r["ticket_id"] for r in final["recent"]], ["a"])

    def test_snapshot_records_stuck_and_finished(self):
        board = self._chain_board()  # b blocked by a; a will fail → b stuck
        states = orch.resolve_states(board, "T")
        with tempfile.TemporaryDirectory() as st:
            with mock.patch("director.orchestrator.dispatch",
                            lambda ticket, **kw: _failed()):
                orch.run_until_drained(board, command=["x"], team="T", states=states,
                                       status=ds.StatusWriter(base=st))
            snap = ds.read_status(base=st)
        assert snap is not None
        self.assertEqual(snap["run"]["stopped_reason"], "stuck")
        self.assertEqual([s["ticket"] for s in snap["stuck"]], ["B"])
        self.assertEqual(snap["stuck"][0]["blocked_by"][0]["id"], "a")

    def test_snapshot_attempt_bumps_on_retry(self):
        board = orch.MockBoard([_issue("a")])
        states = orch.resolve_states(board, "T")
        with tempfile.TemporaryDirectory() as st:
            attempts_seen = []

            def fail_capturing(ticket, **kw):
                snap = ds.read_status(base=st)
                assert snap is not None
                attempts_seen.append(snap["in_flight"][0]["attempt"])
                return _failed()

            with mock.patch("director.orchestrator.dispatch", fail_capturing):
                orch.run_until_drained(board, command=["x"], team="T", states=states,
                                       concurrency=1, retry_budget=1,
                                       status=ds.StatusWriter(base=st))
        self.assertEqual(attempts_seen, [1, 2])  # initial attempt, then the retry

    def test_run_once_records_single_pass_lifecycle(self):
        board = orch.MockBoard([_issue("a")])
        states = orch.resolve_states(board, "T")
        with tempfile.TemporaryDirectory() as st:
            with mock.patch("director.orchestrator.dispatch", _completing_dispatch([])):
                orch.run_once(board, command=["x"], team="T", states=states,
                              status=ds.StatusWriter(base=st))
            snap = ds.read_status(base=st)
        assert snap is not None
        self.assertEqual(snap["run"]["stopped_reason"], "pass_complete")
        self.assertEqual([r["ticket_id"] for r in snap["recent"]], ["a"])

    def test_context_for_reads_live_orchestrator_snapshot(self):
        # R5 end-to-end: context_for joins a queued request to the ticket entry the
        # REAL orchestrator wrote — single-ticket wave keeps it deterministic.
        board = orch.MockBoard([_issue("b")])
        states = orch.resolve_states(board, "T")
        with tempfile.TemporaryDirectory() as st:
            captured = {}

            def capturing(ticket, **kw):
                captured["ctx"] = ds.context_for({"ticket_id": "b",
                                                  "kind": "commandApproval"}, base=st)
                return _done()

            with mock.patch("director.orchestrator.dispatch", capturing):
                orch.run_until_drained(board, command=["x"], team="T", states=states,
                                       status=ds.StatusWriter(base=st))
        ctx = captured["ctx"]
        self.assertIsNotNone(ctx["ticket"])
        self.assertEqual(ctx["ticket"]["ticket_id"], "b")
        self.assertIsNotNone(ctx["run"])


class ReconcileMergeEnqueueTest(unittest.TestCase):
    """M1 (activate-serialized-merge-pipeline): reconcile feeds the serialized merger —
    a done worker that opened a PR enqueues a mergeRequest (R4 handoff, D-40)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.qbase = self.tmp / "q"
        self.board = orch.MockBoard([{"id": "u1", "identifier": "D-1", "title": "t",
                                      "description": "d", "prompt": "p",
                                      "state_id": "st_todo"}])
        self.states = orch.resolve_states(self.board, "T")

    def _reconcile(self, disp, ticket=None):
        return orch.reconcile(self.board, ticket or {"id": "u1", "identifier": "D-1"},
                              disp, 1, self.states, 1, queue_base=self.qbase,
                              workspace_root=self.tmp / "wsr")

    def _done(self, **outcome_extra):
        return {"kind": "terminal",
                "outcome": {"status": "done", "reason": "ok", **outcome_extra},
                "turns": 1, "turn_id": "t"}

    def _merge_reqs(self):
        return [r for r in dq.read_pending(base=self.qbase) if r["kind"] == "mergeRequest"]

    def _seed(self, *ids, labels=("agent-ready",)):
        """Put agent-ready child tickets on the board so reconcile's spawned-id
        validation reads them as real, dispatchable follow-ups."""
        for i in ids:
            self.board._issues[i] = {"id": i, "identifier": i, "title": "child",
                                     "description": "", "prompt": "", "state_id": "st_todo",
                                     "labels": list(labels)}

    def test_done_with_pr_enqueues_a_merge_request(self):
        out = self._reconcile(self._done(pr_url="http://pr/7", pr_branch="feat/x"))
        self.assertEqual(out["summary"]["status"], "completed")
        self.assertTrue(out["summary"]["merge_enqueued"])
        pend = self._merge_reqs()
        self.assertEqual(len(pend), 1)
        self.assertEqual(pend[0]["ticket_id"], "u1")
        self.assertEqual(pend[0]["payload"]["pr"], "http://pr/7")
        self.assertEqual(pend[0]["payload"]["branch"], "feat/x")
        self.assertTrue(pend[0]["workspace_path"].endswith("u1"))  # workspace_root/<id>

    def test_done_without_pr_enqueues_nothing(self):
        out = self._reconcile(self._done())
        self.assertFalse(out["summary"]["merge_enqueued"])
        self.assertEqual(self._merge_reqs(), [])

    def test_done_with_follow_ups_surfaces_spawned_ids(self):
        # done-with-follow-ups (worker-policy-polish): a worker can finish the ticket
        # (done) AND have filed non-blocking follow-up tickets (WORKER_PROTOCOL trigger
        # #2 — deferred/out-of-scope work). Those ids must surface on the done path —
        # summary + board comment — not be dropped (previously only the blocked path
        # consumed spawned_ticket_ids). This is a payload enrichment on done, NOT a new
        # report_outcome status: the board action is still done. The follow-ups are real
        # agent-ready children on the board, so spawned-id validation passes them through.
        self._seed("D-2", "D-3")
        out = self._reconcile(self._done(spawned_ticket_ids=["D-2", "D-3"]))
        self.assertEqual(out["summary"]["spawned_ticket_ids"], ["D-2", "D-3"])
        self.assertNotIn("spawned_invalid", out["summary"])
        body = "\n".join(self.board.comments["u1"])
        self.assertIn("D-2", body)
        self.assertIn("D-3", body)

    def test_done_without_follow_ups_summary_has_empty_spawned(self):
        # uniform shape with the blocked path: the key is always present (empty list when
        # the worker filed no follow-ups) so the StatusWriter sees a consistent summary.
        out = self._reconcile(self._done())
        self.assertEqual(out["summary"]["spawned_ticket_ids"], [])

    def test_pr_bearing_done_parked_in_merging_still_surfaces_follow_ups(self):
        # follow-ups are independent of the merge gate: a PR-bearing done that PARKS in
        # `merging` must still surface its follow-up ids (summary + comment).
        states = dict(self.states)
        states["merging"] = "st_merge"
        self._seed("D-9")
        out = orch.reconcile(self.board, {"id": "u1", "identifier": "D-1"},
                             self._done(pr_url="http://pr/7", pr_branch="feat/x",
                                        spawned_ticket_ids=["D-9"]),
                             1, states, 1, queue_base=self.qbase,
                             workspace_root=self.tmp / "wsr")
        self.assertEqual(out["summary"]["final_state"], "merging")
        self.assertEqual(out["summary"]["spawned_ticket_ids"], ["D-9"])
        self.assertIn("D-9", "\n".join(self.board.comments["u1"]))

    def test_done_with_evidence_carries_it_into_payload(self):
        # merge-preservation M1 (R4): the worker's optional sweep evidence rides
        # outcome → _maybe_enqueue_merge → merge payload (advisory audit data).
        self._reconcile(self._done(pr_url="http://pr/9", pr_branch="feat/y",
                                   evidence={"checks_state": "green",
                                             "unresolved_threads": 0}))
        self.assertEqual(self._merge_reqs()[0]["payload"]["evidence"],
                         {"checks_state": "green", "unresolved_threads": 0})

    def test_done_with_pr_but_no_evidence_payload_evidence_is_none(self):
        # R5 backward-compat: a PR-done without evidence still enqueues; payload evidence None.
        self._reconcile(self._done(pr_url="http://pr/9", pr_branch="feat/y"))
        self.assertIsNone(self._merge_reqs()[0]["payload"]["evidence"])

    def test_pr_bearing_done_not_parked_records_misfire(self):
        # merge-gate-bypass defense-in-depth (LIN-27 dogfood): a PR-bearing done that FAILS
        # to enqueue while `merging` IS configured records a misfire in the summary — never
        # silently lands Done with the PR left unmerged.
        from unittest import mock
        states = dict(self.states)
        states["merging"] = "st_merge"  # configure merge-gating
        with mock.patch("director.queue.append_merge_request",
                        side_effect=RuntimeError("boom")):
            out = orch.reconcile(self.board, {"id": "u1", "identifier": "D-1"},
                                 self._done(pr_url="http://pr/7", pr_branch="feat/x"),
                                 1, states, 1, queue_base=self.qbase,
                                 workspace_root=self.tmp / "wsr")
        self.assertFalse(out["summary"]["merge_enqueued"])
        self.assertIn("misfire", out["summary"]["reconcile_error"])

    def test_redelivered_pr_done_parks_not_misfires(self):
        # at-least-once redelivery (crash-reattach, R19): the SAME PR-done reconciled twice.
        # The second append dedupes (queue returns False), but the merge IS handed off — so
        # it must still PARK in `merging` (not land Done early) and NOT record a misfire.
        states = dict(self.states)
        states["merging"] = "st_merge"
        disp = self._done(pr_url="http://pr/7", pr_branch="feat/x")
        out1 = orch.reconcile(self.board, {"id": "u1", "identifier": "D-1"}, disp, 1, states,
                              1, queue_base=self.qbase, workspace_root=self.tmp / "wsr")
        self.assertTrue(out1["summary"]["merge_enqueued"])
        self.assertEqual(out1["summary"]["final_state"], "merging")
        # second reconcile of the SAME attempt → dedup at the queue, still a handoff
        out2 = orch.reconcile(self.board, {"id": "u1", "identifier": "D-1"}, disp, 1, states,
                              1, queue_base=self.qbase, workspace_root=self.tmp / "wsr")
        self.assertTrue(out2["summary"]["merge_enqueued"])           # dedup = still handed off
        self.assertEqual(out2["summary"]["final_state"], "merging")  # parked, NOT Done early
        self.assertNotIn("misfire", out2["summary"].get("reconcile_error", "") or "")
        self.assertEqual(len(self._merge_reqs()), 1)                 # one queued (deduped)

    def test_done_enqueues_merge_before_terminal_transition(self):
        # act-before-consume (review-reliability P1): the PR-merge must be enqueued BEFORE
        # the `done` board write, so a crash between them never strands an un-enqueued PR
        # branch that startup cleanup would then rmtree. Spy records the board transitions
        # observed AT enqueue time — they must be empty (done not yet written).
        seen = {}
        orig = orch._maybe_enqueue_merge

        def spy(tid, *a, **k):
            seen["transitions_at_enqueue"] = list(self.board.transitions.get(tid, []))
            return orig(tid, *a, **k)

        with mock.patch.object(orch, "_maybe_enqueue_merge", spy):
            self._reconcile(self._done(pr_url="http://pr", pr_branch="b"))
        self.assertEqual(seen["transitions_at_enqueue"], [])          # done NOT yet written
        self.assertIn(self.states["done"], self.board.transitions["u1"])  # done written, after

    def test_blocked_with_pr_fields_still_does_not_enqueue(self):
        # only `done` feeds the merge queue — blocked means the work didn't finish.
        disp = {"kind": "terminal",
                "outcome": {"status": "blocked", "reason": "x", "pr_url": "http://pr/7"},
                "turns": 1, "turn_id": "t"}
        self._reconcile(disp)
        self.assertEqual(self._merge_reqs(), [])

    def test_escalate_does_not_enqueue(self):
        self._reconcile({"kind": "escalate", "reason": "taste", "turns": 1})
        self.assertEqual(self._merge_reqs(), [])

    # --- spawned-id validation (reconcile-spawned-ticket-validation M2) -------------
    def _blocked(self, **outcome_extra):
        return {"kind": "terminal",
                "outcome": {"status": "blocked", "reason": "stuck", **outcome_extra},
                "turns": 2, "turn_id": "t"}

    def test_blocked_claiming_children_none_valid_escalates(self):
        # gap #1: a worker reports blocked with spawned ids that aren't real/dispatchable
        # (a failed/refused/hallucinated issueCreate). Parking it `blocked` would wait on
        # children that never run; reconcile surfaces it as an ESCALATE instead of a
        # silent strand with a false audit trail.
        out = self._reconcile(self._blocked(spawned_ticket_ids=["GHOST-1"]))
        self.assertEqual(out["summary"]["status"], "escalated")
        self.assertEqual(out["summary"]["final_state"], "started")
        self.assertEqual(self.board.transitions.get("u1", []), [])         # not parked
        self.assertEqual(out["summary"].get("spawned_invalid"), ["GHOST-1"])
        self.assertIn("escalated", "\n".join(self.board.comments["u1"]))
        self.assertEqual(self._merge_reqs(), [])

    def test_blocked_with_a_valid_child_stays_blocked(self):
        # a blocked carrying ≥1 real agent-ready child has a dispatchable continuation —
        # it stays blocked (no escalate); the valid child is surfaced, the invalid named.
        self._seed("REAL-1")
        out = self._reconcile(self._blocked(spawned_ticket_ids=["REAL-1", "GHOST-2"]))
        self.assertEqual(out["summary"]["status"], "blocked")
        self.assertEqual(out["summary"]["spawned_ticket_ids"], ["REAL-1"])
        self.assertEqual(out["summary"].get("spawned_invalid"), ["GHOST-2"])

    def test_blocked_without_children_stays_plain_blocked(self):
        # an EMPTY claim is a legitimate "genuinely stuck, no children" — NOT escalated.
        out = self._reconcile(self._blocked())
        self.assertEqual(out["summary"]["status"], "blocked")
        self.assertEqual(out["summary"]["spawned_ticket_ids"], [])
        self.assertNotIn("spawned_invalid", out["summary"])

    def test_blocked_self_referential_spawn_escalates(self):
        # reporting the ticket's OWN id as a child is no real continuation → escalate.
        out = self._reconcile(self._blocked(spawned_ticket_ids=["u1"]))
        self.assertEqual(out["summary"]["status"], "escalated")

    def test_blocked_unlabeled_child_is_invalid_and_escalates(self):
        # F3: a child created WITHOUT the agent-ready label is silently undispatchable, so
        # it is not a real continuation — reconcile treats it as invalid and escalates.
        self._seed("NOLABEL-1", labels=())
        out = self._reconcile(self._blocked(spawned_ticket_ids=["NOLABEL-1"]))
        self.assertEqual(out["summary"]["status"], "escalated")
        self.assertEqual(out["summary"].get("spawned_invalid"), ["NOLABEL-1"])

    def test_done_with_invalid_followup_still_completes_but_names_it(self):
        # a done's primary work is complete regardless — the transition NEVER changes — but
        # an unreal follow-up id is surfaced honestly (no false audit trail) and NOT counted
        # as a real spawned ticket.
        out = self._reconcile(self._done(spawned_ticket_ids=["GHOST-3"]))
        self.assertEqual(out["summary"]["final_state"], "done")
        self.assertEqual(out["summary"]["status"], "completed")
        self.assertEqual(out["summary"]["spawned_ticket_ids"], [])
        self.assertEqual(out["summary"].get("spawned_invalid"), ["GHOST-3"])
        self.assertIn("claimed but not found", "\n".join(self.board.comments["u1"]))

    def test_spawned_verify_board_error_trusts_report_no_crash(self):
        # best-effort: a board-read failure degrades to "trust the reported ids" (today's
        # behavior), records the error, and never escalates on unverifiable data.
        with mock.patch.object(self.board, "fetch_issue_labels_by_ids",
                               side_effect=RuntimeError("board down")):
            out = self._reconcile(self._blocked(spawned_ticket_ids=["MAYBE-1"]))
        self.assertEqual(out["summary"]["status"], "blocked")               # NOT escalated
        self.assertEqual(out["summary"]["spawned_ticket_ids"], ["MAYBE-1"])  # trusted as-is
        self.assertIn("spawned-id verify failed", out["summary"]["reconcile_error"])

    def test_done_spawned_verify_board_error_trusts_report(self):
        # the done path shares the same fail-open helper: a board-read failure trusts the
        # reported follow-ups (unverified) and still completes — never a crash.
        with mock.patch.object(self.board, "fetch_issue_labels_by_ids",
                               side_effect=RuntimeError("board down")):
            out = self._reconcile(self._done(spawned_ticket_ids=["MAYBE-2"]))
        self.assertEqual(out["summary"]["final_state"], "done")
        self.assertEqual(out["summary"]["spawned_ticket_ids"], ["MAYBE-2"])  # trusted as-is
        self.assertNotIn("spawned_invalid", out["summary"])
        self.assertIn("unverified", "\n".join(self.board.comments["u1"]))
        self.assertIn("spawned-id verify failed", out["summary"]["reconcile_error"])

    # --- spawned-id identifier matching (gap #1a) ------------------------------------
    def _seed_ident(self, node_id, identifier, *, labels=("agent-ready",)):
        """Seed a child whose node id DIFFERS from its human identifier, so a worker
        reporting the identifier exercises the both-forms board lookup (not the
        id==identifier conflation the other tests use)."""
        self.board._issues[node_id] = {"id": node_id, "identifier": identifier,
                                       "title": "child", "description": "", "prompt": "",
                                       "state_id": "st_todo", "labels": list(labels)}

    def test_blocked_claiming_real_child_by_identifier_stays_blocked(self):
        # gap #1a: the worker reports a real agent-ready child by its HUMAN identifier
        # (LIN-31), not its UUID node id. The lookup resolves both forms, so the child
        # validates as valid → blocked stays blocked (was: a false escalate when the
        # filter matched node ids only).
        self._seed_ident("uuid-child", "LIN-31")
        out = self._reconcile(self._blocked(spawned_ticket_ids=["LIN-31"]))
        self.assertEqual(out["summary"]["status"], "blocked")            # NOT escalated
        self.assertEqual(out["summary"]["spawned_ticket_ids"], ["LIN-31"])
        self.assertNotIn("spawned_invalid", out["summary"])

    def test_done_followup_by_identifier_validates(self):
        # the done path resolves identifiers too — a real follow-up reported by identifier
        # is surfaced as a valid spawned id, not a misleading "claimed but not found".
        self._seed_ident("uuid-9", "LIN-9")
        out = self._reconcile(self._done(spawned_ticket_ids=["LIN-9"]))
        self.assertEqual(out["summary"]["spawned_ticket_ids"], ["LIN-9"])
        self.assertNotIn("spawned_invalid", out["summary"])
        self.assertIn("LIN-9", "\n".join(self.board.comments["u1"]))

    def test_blocked_self_referential_spawn_by_identifier_escalates(self):
        # reporting the ticket's OWN human identifier (D-1), not just its node id, is no
        # real continuation either → excluded from valid → escalate.
        out = self._reconcile(self._blocked(spawned_ticket_ids=["D-1"]))
        self.assertEqual(out["summary"]["status"], "escalated")
        self.assertEqual(out["summary"].get("spawned_invalid"), ["D-1"])

    # --- restart-safety: parked-set recording (poll-loop-strand-safety M2) -----------
    def test_blocked_in_started_records_park(self):
        # no configured blocked-state (default) → blocked stays in `started` → recorded parked
        self._reconcile(self._blocked())
        self.assertIn("u1", dq.read_parked(base=self.qbase))

    def test_blocked_in_configured_state_does_not_record_park(self):
        # a configured blocked board-state moves the ticket OUT of `started` → orphan-safe → not parked
        states = dict(self.states); states["blocked"] = "st_blocked"
        orch.reconcile(self.board, {"id": "u1", "identifier": "D-1"}, self._blocked(),
                       1, states, 1, queue_base=self.qbase, workspace_root=self.tmp / "wsr")
        self.assertNotIn("u1", dq.read_parked(base=self.qbase))

    def test_escalate_kind_records_park(self):
        self._reconcile({"kind": "escalate", "reason": "taste", "turns": 1})
        self.assertIn("u1", dq.read_parked(base=self.qbase))

    def test_blocked_escalate_downgrade_records_park(self):
        # the gap-#1 downgrade leaves the ticket in `started` (escalated) → also restart-parked
        self._reconcile(self._blocked(spawned_ticket_ids=["GHOST-X"]))
        self.assertIn("u1", dq.read_parked(base=self.qbase))

    def test_done_does_not_record_park(self):
        self._reconcile(self._done())
        self.assertEqual(dq.read_parked(base=self.qbase), set())

    def test_terminal_unknown_records_park(self):
        # a malformed terminal (unrecognized status) is left in `started` for review → parked
        self._reconcile({"kind": "terminal", "outcome": {"status": "weird"},
                         "turns": 1, "turn_id": "t"})
        self.assertIn("u1", dq.read_parked(base=self.qbase))

    def test_unknown_disposition_records_park(self):
        # an unknown disposition kind is left in `started` for review → parked
        self._reconcile({"kind": "bogus", "turns": 1})
        self.assertIn("u1", dq.read_parked(base=self.qbase))

    def test_explicit_ticket_workspace_is_used(self):
        orch.reconcile(self.board, {"id": "u1", "workspace": "/custom/ws"},
                       self._done(pr_url="u", pr_branch="b"), 1, self.states, 1,
                       queue_base=self.qbase)
        self.assertEqual(self._merge_reqs()[0]["workspace_path"], "/custom/ws")

    # -- merge-gated eligibility (R2): PR-done PARKS in `merging` when configured --
    def _merging_states(self):
        # self.states resolved against a board WITHOUT a Merging state has merging=None;
        # graft a configured merging id to exercise the gated path (config R1 already tested).
        return {**self.states, "merging": "st_merge"}

    def test_done_with_pr_parks_in_merging_when_configured(self):
        states = self._merging_states()
        out = orch.reconcile(self.board, {"id": "u1", "identifier": "D-1"},
                             self._done(pr_url="http://pr/7", pr_branch="feat/x"), 1,
                             states, 1, queue_base=self.qbase, workspace_root=self.tmp / "wsr")
        # board parked in merging (NOT done) — a child blocked_by u1 stays ineligible
        self.assertIn("st_merge", self.board.transitions["u1"])
        self.assertNotIn(states["done"], self.board.transitions.get("u1", []))
        self.assertEqual(out["summary"]["final_state"], "merging")
        self.assertEqual(out["summary"]["status"], "completed")  # worker outcome unchanged
        self.assertTrue(out["summary"]["merge_enqueued"])
        self.assertEqual(len(self._merge_reqs()), 1)  # merge still enqueued (R19 order kept)

    def test_no_pr_done_goes_to_done_even_when_merging_configured(self):
        # planning/research/spec tickets (no PR) must still reach `done` immediately so
        # their children unblock — merging only gates PR-bearing work.
        states = self._merging_states()
        out = orch.reconcile(self.board, {"id": "u1", "identifier": "D-1"}, self._done(), 1,
                             states, 1, queue_base=self.qbase, workspace_root=self.tmp / "wsr")
        self.assertIn(states["done"], self.board.transitions["u1"])
        self.assertNotIn("st_merge", self.board.transitions.get("u1", []))
        self.assertEqual(out["summary"]["final_state"], "done")
        self.assertFalse(out["summary"]["merge_enqueued"])


class _CancelBoard(orch.MockBoard):
    """A board whose `fetch_issue_states_by_ids` reports every in-flight ticket as
    moved to a non-`started` state — simulating a human moving it out of In Progress
    while its worker runs (active-run reconciliation)."""

    def __init__(self, issues, *, fetch_raises=False):
        super().__init__(issues)
        self._fetch_raises = fetch_raises

    def fetch_issue_states_by_ids(self, issue_ids):
        if self._fetch_raises:
            raise RuntimeError("tracker fetch boom")
        return {i: {"state_id": "st_done", "state_name": "Done",
                    "state_type": "completed"} for i in issue_ids}


def _wait_then(disposition, fallback):
    """A fake `dispatch` simulating a long worker: it blocks on its `cancel_event` and
    returns `disposition` if cancelled, else `fallback` after a short grace."""
    def fake(ticket, *, cancel_event=None, **kw):
        if cancel_event is not None and cancel_event.wait(timeout=3.0):
            return {**disposition, "turns": 1, "telemetry": {}}
        return {**fallback, "turns": 1, "telemetry": {}}
    return fake


class ActiveRunReconcileTest(unittest.TestCase):
    def _issue(self, iid="a", ident="A"):
        return {"id": iid, "identifier": ident, "title": "t", "description": "d",
                "prompt": "p", "state_id": "st_todo"}

    def test_externally_moved_ticket_is_cancelled_no_retry_no_write(self):
        board = _CancelBoard([self._issue()])
        states = orch.resolve_states(board, "T")
        with mock.patch("director.orchestrator.dispatch",
                        _wait_then({"kind": "cancelled", "reason": "reconciliation"},
                                   {"kind": "terminal", "outcome": {"status": "done"}})):
            summaries = orch.run_once(board, command=["x"], team="T", states=states,
                                      reconcile_interval_s=0.1)
        row = summaries[0]
        self.assertEqual(row["status"], "cancelled")
        self.assertEqual(row["final_state"], "Done")         # the OBSERVED external state
        self.assertEqual(row["attempts"], 1)                 # NOT retried
        # the only board write for A is the claim → started; reconciliation does not
        # re-transition (the human owns the new state, D-62)
        self.assertEqual(board.transitions["a"], ["st_prog"])
        self.assertEqual(len(board.comments["a"]), 1)        # one "stopped" comment

    def test_fetch_failure_is_fail_soft_workers_complete(self):
        # a fetch_issue_states_by_ids that raises must NOT sink the wave (R5): no cancel
        # is ever delivered, so the fake worker falls through to its terminal outcome.
        board = _CancelBoard([self._issue()], fetch_raises=True)
        states = orch.resolve_states(board, "T")
        with mock.patch("director.orchestrator.dispatch",
                        _wait_then({"kind": "cancelled", "reason": "reconciliation"},
                                   {"kind": "terminal", "outcome": {"status": "done"}})):
            summaries = orch.run_once(board, command=["x"], team="T", states=states,
                                      reconcile_interval_s=0.1)
        self.assertEqual(summaries[0]["status"], "completed")  # worker ran to done
        self.assertEqual(summaries[0]["final_state"], "done")

    def test_reconcile_outcome_recorded_on_main_thread(self):
        # R6/D-60: the cancelled outcome flows through the normal StatusWriter.terminal
        # path on the wave-loop (main) thread — the single-writer invariant holds.
        main_ident = threading.get_ident()
        seen = []

        class _RecordingWriter(ds.NoopStatusWriter):
            def terminal(self, ticket, summary):
                seen.append((summary.get("status"), threading.get_ident()))

        board = _CancelBoard([self._issue()])
        states = orch.resolve_states(board, "T")
        with mock.patch("director.orchestrator.dispatch",
                        _wait_then({"kind": "cancelled", "reason": "reconciliation"},
                                   {"kind": "terminal", "outcome": {"status": "done"}})):
            orch.run_once(board, command=["x"], team="T", states=states,
                          status=_RecordingWriter(), reconcile_interval_s=0.1)
        self.assertEqual(seen, [("cancelled", main_ident)])


class StartupRecoveryTest(unittest.TestCase):
    """_startup_recovery (Symphony §8.6 + §14.3): terminal-workspace cleanup +
    orphaned-`started` re-attach, both fail-soft, run once before the daemon's first tick."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.qbase = self.tmp / "q"
        self.wsroot = self.tmp / "wsroot"

    def test_before_remove_fires_before_rmtree(self):
        board = orch.MockBoard([
            {"id": "old", "identifier": "OLD", "state_id": "st_done", "prompt": "p"}])
        states = orch.resolve_states(board, "T")
        ws = run.workspace_path("old", self.wsroot); ws.mkdir(parents=True)
        marker = self.tmp / "br_ran"  # outside ws → survives the rmtree, proving the hook ran
        orch._startup_recovery(board, states, team="T", workspace_root=self.wsroot,
                               queue_base=self.qbase,
                               hooks={"before_remove": f"touch {marker}"}, hook_timeout_s=5)
        self.assertFalse(ws.exists())      # workspace removed
        self.assertTrue(marker.exists())   # before_remove ran (before the delete)

    def test_failing_before_remove_does_not_block_rmtree(self):
        board = orch.MockBoard([
            {"id": "old", "identifier": "OLD", "state_id": "st_done", "prompt": "p"}])
        states = orch.resolve_states(board, "T")
        ws = run.workspace_path("old", self.wsroot); ws.mkdir(parents=True)
        orch._startup_recovery(board, states, team="T", workspace_root=self.wsroot,
                               queue_base=self.qbase,
                               hooks={"before_remove": "exit 1"}, hook_timeout_s=5)
        self.assertFalse(ws.exists())  # delete still happened despite before_remove failure

    def test_run_once_threads_hooks_to_dispatched_worker(self):
        # hooks flow main→run_once→_dispatch_wave→_RunState→dispatch→run.drive→_prepare:
        # after_create populates the dispatched worker's workspace (the daemon-path bridge)
        board = orch.MockBoard([
            {"id": "u1", "identifier": "U-1", "state_id": "st_todo", "prompt": "p"}])
        states = orch.resolve_states(board, "T")
        wsroot = self.tmp / "wsr_once"
        orch.run_once(board, command=[sys.executable, run._MOCK, "report"], team="T",
                      states=states, queue_base=self.tmp / "q_once", workspace_root=wsroot,
                      hooks={"after_create": "touch hooked"}, hook_timeout_s=10)
        self.assertTrue((wsroot / "u1" / "hooked").exists())  # after_create ran for the worker

    def test_cleanup_removes_terminal_workspaces_except_pending_merge(self):
        board = orch.MockBoard([
            {"id": "u1", "identifier": "D-1", "state_id": "st_done", "prompt": "p"},
            {"id": "u2", "identifier": "D-2", "state_id": "st_done", "prompt": "p"}])
        states = orch.resolve_states(board, "T")
        ws1 = run.workspace_path("u1", self.wsroot); ws1.mkdir(parents=True)
        ws2 = run.workspace_path("u2", self.wsroot); ws2.mkdir(parents=True)
        # u2's workspace is still referenced by a queued PR-merge → must survive cleanup
        dq.append_merge_request("u2", pr="http://pr", workspace_path=str(ws2), base=self.qbase)
        orch._startup_recovery(board, states, team="T",
                               workspace_root=self.wsroot, queue_base=self.qbase)
        self.assertFalse(ws1.exists())   # terminal, no pending merge → removed
        self.assertTrue(ws2.exists())    # protected by pending merge → kept

    def test_reattaches_orphaned_started_tickets(self):
        board = orch.MockBoard([
            {"id": "o1", "identifier": "O-1", "state_id": "st_prog", "prompt": "p"}])
        states = orch.resolve_states(board, "T")
        orch._startup_recovery(board, states, team="T",
                               workspace_root=self.wsroot, queue_base=self.qbase)
        # the orphan was moved back to ready so the first poll re-dispatches it
        self.assertEqual(board._issues["o1"]["state_id"], states["ready"])
        self.assertIn(states["ready"], board.transitions["o1"])

    def test_parked_started_ticket_is_not_reattached(self):
        # gap #2: a ticket the orchestrator PARKED in `started` (escalate / blocked-in-started)
        # is left alone on restart — it is parked-for-human, not a crash orphan — while a
        # genuine orphan beside it is still recovered.
        board = orch.MockBoard([
            {"id": "parked", "identifier": "P-1", "state_id": "st_prog", "prompt": "p"},
            {"id": "orphan", "identifier": "O-1", "state_id": "st_prog", "prompt": "p"}])
        states = orch.resolve_states(board, "T")
        dq.append_parked("parked", base=self.qbase)
        orch._startup_recovery(board, states, team="T",
                               workspace_root=self.wsroot, queue_base=self.qbase)
        self.assertEqual(board._issues["parked"]["state_id"], "st_prog")  # left in started
        self.assertNotIn("parked", board.transitions)                     # never re-readied
        self.assertEqual(board._issues["orphan"]["state_id"], states["ready"])  # orphan recovered

    def test_parked_set_gc_drops_tickets_no_longer_started(self):
        # a parked tid that has LEFT `started` (a human moved it) is GC'd from the set, so it
        # can never suppress a future orphan-recovery of a different ticket reusing the id.
        board = orch.MockBoard([
            {"id": "moved", "identifier": "M-1", "state_id": "st_todo", "prompt": "p"}])  # ready, not started
        states = orch.resolve_states(board, "T")
        dq.append_parked("moved", base=self.qbase)
        orch._startup_recovery(board, states, team="T",
                               workspace_root=self.wsroot, queue_base=self.qbase)
        self.assertEqual(dq.read_parked(base=self.qbase), set())          # GC'd (not in started)

    def test_parked_read_failure_falls_back_to_reready_all(self):
        # fail-open: a parked-set read error degrades to re-ready all (today's behavior),
        # never strands a real orphan behind an unreadable set.
        board = orch.MockBoard([
            {"id": "o1", "identifier": "O-1", "state_id": "st_prog", "prompt": "p"}])
        states = orch.resolve_states(board, "T")
        with mock.patch("director.queue.gc_parked", side_effect=RuntimeError("disk")):
            orch._startup_recovery(board, states, team="T",
                                   workspace_root=self.wsroot, queue_base=self.qbase)
        self.assertEqual(board._issues["o1"]["state_id"], states["ready"])  # re-readied anyway

    def test_claim_and_submit_clears_parked_marker(self):
        # gap #2: claiming a ticket (a fresh attempt) drops its parked marker, so a later
        # crash recovers it — the within-lifetime path the startup GC never sees (no restart).
        board = orch.MockBoard([_issue("a")])
        states = orch.resolve_states(board, "T")
        dq.append_parked("a", base=self.qbase)
        with mock.patch("director.orchestrator.dispatch", lambda *a, **k: _DONE):
            state = orch._RunState(board=board, states=states, status=None, retry_budget=1,
                                   concurrency=1, queue_base=self.qbase,
                                   workspace_root=self.wsroot, command=["x"])
            try:
                self.assertTrue(state.claim_and_submit(_issue("a"), wave=1))
                self.assertNotIn("a", dq.read_parked(base=self.qbase))  # cleared on claim
            finally:
                state.shutdown()

    def test_fetch_failure_is_fail_soft(self):
        class _Boom(orch.MockBoard):
            def fetch_issues_by_states(self, team, state_ids):
                raise RuntimeError("tracker down")
        board = _Boom([])
        states = orch.resolve_states(board, "T")
        # must NOT raise — startup proceeds despite the fetch error (§11.4)
        orch._startup_recovery(board, states, team="T",
                               workspace_root=self.wsroot, queue_base=self.qbase)

    def test_run_forever_invokes_startup_recovery_before_loop(self):
        board = orch.MockBoard([])
        states = orch.resolve_states(board, "T")
        with mock.patch("director.orchestrator._startup_recovery") as sr:
            # max_ticks=0 → the tick loop exits immediately, but recovery runs before it
            orch.run_forever(board, command=["x"], team="T", states=states,
                             install_signals=False, max_ticks=0)
        sr.assert_called_once()


class ReconcileCancelledCleanupTest(unittest.TestCase):
    """reconcile's `cancelled` branch cleans the abandoned mid-flight workspace ONLY when
    the human moved the ticket to a TERMINAL state (Symphony §8.5 Part B)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.qbase = self.tmp / "q"
        self.wsroot = self.tmp / "wsr"
        self.board = orch.MockBoard([{"id": "u1", "identifier": "D-1", "title": "t",
                                      "description": "d", "prompt": "p",
                                      "state_id": "st_prog"}])
        self.states = orch.resolve_states(self.board, "T")

    def _cancel(self, ext):
        return orch.reconcile(
            self.board, {"id": "u1", "identifier": "D-1"},
            {"kind": "cancelled", "reason": "reconciliation", "turns": 1},
            1, self.states, 1, queue_base=self.qbase, workspace_root=self.wsroot,
            external_state=ext)

    def test_cancelled_to_terminal_cleans_workspace(self):
        ws = run.workspace_path("u1", self.wsroot); ws.mkdir(parents=True)
        out = self._cancel({"state_name": "Done", "state_type": "completed"})
        self.assertEqual(out["summary"]["final_state"], "Done")
        self.assertFalse(ws.exists())   # mid-flight kill to terminal → workspace cleaned

    def test_cancelled_to_nonterminal_keeps_workspace(self):
        ws = run.workspace_path("u1", self.wsroot); ws.mkdir(parents=True)
        out = self._cancel({"state_name": "Backlog", "state_type": "backlog"})
        self.assertEqual(out["summary"]["final_state"], "Backlog")
        self.assertTrue(ws.exists())    # parked in a non-terminal state → workspace kept

    def test_normal_done_keeps_workspace(self):
        ws = run.workspace_path("u1", self.wsroot); ws.mkdir(parents=True)
        orch.reconcile(self.board, {"id": "u1", "identifier": "D-1"},
                       {"kind": "terminal", "outcome": {"status": "done"},
                        "turns": 1, "turn_id": "t"},
                       1, self.states, 1, queue_base=self.qbase, workspace_root=self.wsroot)
        self.assertTrue(ws.exists())    # §9.1: successful runs do not auto-delete (merger needs it)


class BackoffHelperTest(unittest.TestCase):
    def test_exponential_with_cap(self):
        self.assertEqual(orch._backoff_s(1, base=2, cap=100), 2)    # n=1 → base
        self.assertEqual(orch._backoff_s(2, base=2, cap=100), 4)    # 2·base
        self.assertEqual(orch._backoff_s(3, base=2, cap=100), 8)    # 4·base
        self.assertEqual(orch._backoff_s(4, base=2, cap=100), 16)
        self.assertEqual(orch._backoff_s(99, base=2, cap=100), 100)  # capped
        self.assertEqual(orch._backoff_s(0, base=2, cap=100), 2)     # n<1 clamps to base

    def test_idle_wait_grows_from_poll_interval(self):
        # idle wait: streak 0 → poll_interval, doubling, capped at `cap`.
        self.assertEqual(orch._idle_wait_s(0.02, 0, 1.0), 0.02)
        self.assertEqual(orch._idle_wait_s(0.02, 1, 1.0), 0.04)
        self.assertEqual(orch._idle_wait_s(0.02, 2, 1.0), 0.08)
        self.assertEqual(orch._idle_wait_s(10.0, 9, 300.0), 300.0)  # capped


def _wait_for(cond, timeout=3.0, msg="condition not met in time"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return
        time.sleep(0.005)
    raise AssertionError(msg)


_DONE = {"kind": "terminal", "outcome": {"status": "done"}, "turns": 1, "telemetry": {}}


class DaemonLoopTest(unittest.TestCase):
    """run_forever (daemon stage 2): the always-on tick loop. Each test drives it on a
    background thread with an injected shutdown_event + install_signals=False + a fast
    poll_interval, so the daemon is terminable without real signals."""

    def _run_bg(self, board, fake, **kw):
        shutdown, force, result = threading.Event(), threading.Event(), {}
        states = orch.resolve_states(board, "T")

        def go():
            with mock.patch("director.orchestrator.dispatch", fake):
                result["out"] = orch.run_forever(
                    board, command=["x"], team="T", states=states,
                    shutdown_event=shutdown, force_event=force, install_signals=False,
                    poll_interval_s=0.02, **kw)
        th = threading.Thread(target=go, daemon=True)
        th.start()
        return shutdown, force, th, result

    def test_daemon_signal_action_first_drains_second_forces(self):
        shutdown, force = threading.Event(), threading.Event()
        orch._daemon_signal_action(shutdown, force)
        self.assertTrue(shutdown.is_set())
        self.assertFalse(force.is_set())  # 1st signal only requests graceful drain
        orch._daemon_signal_action(shutdown, force)
        self.assertTrue(force.is_set())   # 2nd escalates to force

    def test_never_exits_on_empty_and_idle_does_not_busyspin(self):
        # R1 + R7: an empty board keeps polling forever (does not exit on drained); the
        # idle wait sleeps (no busy-spin) and a shutdown during idle returns promptly.
        board = orch.MockBoard([])
        with tempfile.TemporaryDirectory() as st:
            w = ds.StatusWriter(base=st)
            shutdown, force, th, result = self._run_bg(board, lambda *a, **k: _DONE, status=w)
            try:
                _wait_for(lambda: (ds.read_status(base=st) or {}).get("run", {}).get("polls", 0) >= 3,
                          msg="daemon did not keep polling an empty board")
                self.assertTrue(th.is_alive())  # R1: never exits on an empty/drained board
                snap = ds.read_status(base=st)
                self.assertEqual(snap["run"]["mode"], "daemon")
                self.assertEqual(snap["run"]["phase"], "idle")
                before = snap["run"]["polls"]
                time.sleep(0.1)  # ~5 idle ticks at poll_interval 0.02 if sleeping
                after = (ds.read_status(base=st) or {})["run"]["polls"]
                self.assertLess(after - before, 200,  # a busy-spin would be many thousands
                                "idle loop appears to busy-spin")
            finally:
                shutdown.set()
                th.join(timeout=2.0)
            self.assertFalse(th.is_alive())  # R7: prompt shutdown while idle

    def test_bounded_claim_and_top_up_as_slot_frees(self):
        # R3 (bounded claim) + R2 (top-up as a slot frees, not wave-drain).
        board = orch.MockBoard([_issue("a"), _issue("b"), _issue("c")])
        release = {tid: threading.Event() for tid in ("a", "b", "c")}
        entered, lock = [], threading.Lock()

        def fake(ticket, *, cancel_event=None, **kw):
            tid = ticket["id"]
            with lock:
                entered.append(tid)
            release[tid].wait(timeout=5.0)
            return _DONE
        shutdown, force, th, result = self._run_bg(board, fake, concurrency=2)
        try:
            _wait_for(lambda: len(entered) >= 2, msg="first two not dispatched")
            time.sleep(0.1)  # prove the 3rd is NOT claimed up-front (bounded, R3)
            with lock:
                self.assertEqual(sorted(entered), ["a", "b"])
            self.assertEqual(board.state_name("c"), "Todo")
            self.assertEqual(
                sum(1 for t in ("a", "b", "c") if board.state_name(t) == "In Progress"), 2)
            release["a"].set()  # free a slot → top-up claims c while b still runs (R2)
            _wait_for(lambda: board.state_name("c") == "In Progress",
                      msg="c was not topped-up after a slot freed")
            with lock:
                self.assertIn("c", entered)
            self.assertEqual(board.state_name("b"), "In Progress")  # b still running
        finally:
            for ev in release.values():
                ev.set()
            shutdown.set()
            th.join(timeout=3.0)

    def test_stuck_is_status_not_exit(self):
        # R5: an all-blocked board (b blocked by a failed a) writes status.stuck and
        # keeps polling — stuck is a heartbeat signal, never a termination.
        board = orch.MockBoard([_issue("a"), _issue("b", ["a"])])
        with tempfile.TemporaryDirectory() as st:
            w = ds.StatusWriter(base=st)
            fail = {"kind": "failed", "status": "failed", "turn_id": None, "turns": 0}
            shutdown, force, th, result = self._run_bg(
                board, lambda *a, **k: fail, retry_budget=0, status=w)
            try:
                _wait_for(lambda: (ds.read_status(base=st) or {}).get("stuck"),
                          msg="stuck set never recorded")
                snap = ds.read_status(base=st)
                self.assertEqual([s["ticket"] for s in snap["stuck"]], ["B"])
                self.assertEqual(snap["stuck"][0]["blocked_by"][0]["id"], "a")
                self.assertTrue(th.is_alive())  # R5: stuck did NOT terminate the daemon
            finally:
                shutdown.set()
                th.join(timeout=2.0)

    def test_strand_escalates_once_past_threshold(self):
        # gap #3: a ticket blocked with no eligible progress for `strand_escalation_polls`
        # idle polls is escalated ONCE — a board comment + a `stranded` status flag — then
        # never re-fired no matter how long it keeps idling.
        board = orch.MockBoard([_issue("a"), _issue("b", ["a"])])
        with tempfile.TemporaryDirectory() as st:
            w = ds.StatusWriter(base=st)
            fail = {"kind": "failed", "status": "failed", "turn_id": None, "turns": 0}
            shutdown, force, th, result = self._run_bg(
                board, lambda *a, **k: fail, retry_budget=0, status=w,
                strand_escalation_polls=2)
            def _b_stranded():
                # the b stuck-entry on an IDLE-tick snapshot (a busy tick writes stuck=[]).
                # stuck "ticket" is the IDENTIFIER ("B"); the comment keys on the id ("b").
                snap = ds.read_status(base=st) or {}
                return next((s for s in snap.get("stuck", [])
                             if s["ticket"] == "B" and s.get("stranded")), None)
            try:
                _wait_for(lambda: _b_stranded() is not None, msg="b never flagged stranded")
                self.assertTrue(_b_stranded()["stranded"])
                self.assertGreaterEqual(_b_stranded()["polls"], 2)   # the streak count rides along
                strand = [c for c in board.comments.get("b", []) if "stranded" in c]
                self.assertEqual(len(strand), 1)              # escalated exactly once
                self.assertIn("needs human", strand[0])
                polls0 = (ds.read_status(base=st) or {})["run"]["polls"]
                _wait_for(lambda: (ds.read_status(base=st) or {})["run"]["polls"] >= polls0 + 4,
                          msg="daemon did not keep polling")
                self.assertEqual(                              # still once — no re-fire
                    len([c for c in board.comments.get("b", []) if "stranded" in c]), 1)
            finally:
                shutdown.set()
                th.join(timeout=2.0)

    def test_strand_escalation_disabled_at_zero(self):
        # strand_escalation_polls=0 → never escalate; stuck entries carry no `stranded` flag.
        board = orch.MockBoard([_issue("a"), _issue("b", ["a"])])
        with tempfile.TemporaryDirectory() as st:
            w = ds.StatusWriter(base=st)
            fail = {"kind": "failed", "status": "failed", "turn_id": None, "turns": 0}
            shutdown, force, th, result = self._run_bg(
                board, lambda *a, **k: fail, retry_budget=0, status=w,
                strand_escalation_polls=0)
            try:
                _wait_for(lambda: (ds.read_status(base=st) or {}).get("stuck"),
                          msg="stuck never recorded")
                polls0 = (ds.read_status(base=st))["run"]["polls"]
                _wait_for(lambda: (ds.read_status(base=st) or {})["run"]["polls"] >= polls0 + 5,
                          msg="daemon did not keep polling")
                self.assertEqual(
                    [c for c in board.comments.get("b", []) if "stranded" in c], [])
                self.assertFalse(
                    any(s.get("stranded") for s in (ds.read_status(base=st))["stuck"]))
            finally:
                shutdown.set()
                th.join(timeout=2.0)

    def test_strand_streak_resets_when_ticket_progresses(self):
        # a ticket that becomes eligible before the threshold never escalates: `a` completes,
        # `b` unblocks and dispatches well under a high threshold (the streak reset on progress).
        board = orch.MockBoard([_issue("a"), _issue("b", ["a"])])
        with tempfile.TemporaryDirectory() as st:
            w = ds.StatusWriter(base=st)
            shutdown, force, th, result = self._run_bg(
                board, lambda *a, **k: _DONE, status=w, strand_escalation_polls=10)
            try:
                _wait_for(lambda: board.state_name("b") in ("In Progress", "Done"),
                          msg="b never progressed after a completed")
                self.assertEqual(
                    [c for c in board.comments.get("b", []) if "stranded" in c], [])
            finally:
                shutdown.set()
                th.join(timeout=2.0)

    def test_poll_failure_is_fail_soft(self):
        # R8: a poll that raises is survived (not poll_failed-exit like the batch path);
        # the daemon recovers and claims the ticket on a later poll.
        class FlakyPoll(orch.MockBoard):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                self.polls = 0

            def list_ready_issues(self, team, ready_state_id):
                self.polls += 1
                if self.polls == 1:
                    raise RuntimeError("network down")
                return super().list_ready_issues(team, ready_state_id)

        board = FlakyPoll([_issue("a")])
        shutdown, force, th, result = self._run_bg(board, lambda *a, **k: _DONE)
        try:
            _wait_for(lambda: board.state_name("a") == "Done",
                      msg="daemon did not recover from a poll failure")
            self.assertTrue(th.is_alive())
        finally:
            shutdown.set()
            th.join(timeout=2.0)

    def test_shutdown_drains_in_flight(self):
        # R6 (graceful): shutdown stops claiming and lets the in-flight worker finish.
        board = orch.MockBoard([_issue("a")])
        release, entered = threading.Event(), threading.Event()

        def fake(ticket, *, cancel_event=None, **kw):
            entered.set()
            release.wait(timeout=5.0)
            return _DONE
        shutdown, force, th, result = self._run_bg(board, fake)
        try:
            _wait_for(entered.is_set, msg="worker never started")
            shutdown.set()
            time.sleep(0.1)
            self.assertTrue(th.is_alive())   # still draining (worker not released)
            release.set()
            th.join(timeout=3.0)
            self.assertFalse(th.is_alive())  # drained then exited
            self.assertEqual(board.state_name("a"), "Done")
            self.assertEqual(result["out"]["stopped_reason"], "shutdown")
        finally:
            release.set()
            shutdown.set()
            th.join(timeout=2.0)

    def test_stuck_self_clears_when_work_resumes(self):
        # review-arch P2: the stuck heartbeat tracks LIVE state — once blocked work
        # becomes runnable, stuck clears (it is not a one-way latch in status.json).
        board = orch.MockBoard([_issue("a"), _issue("b", ["a"])])
        with tempfile.TemporaryDirectory() as st:
            w = ds.StatusWriter(base=st)

            def fake(ticket, *, cancel_event=None, **kw):
                if ticket["id"] == "a":
                    return {"kind": "failed", "status": "failed", "turn_id": None, "turns": 0}
                return _DONE
            shutdown, force, th, result = self._run_bg(board, fake, retry_budget=0, status=w)
            try:
                _wait_for(lambda: (ds.read_status(base=st) or {}).get("stuck"),
                          msg="stuck never set")  # a failed → b blocked → stuck=[B]
                board.update_issue_state("a", "st_done")  # operator unblocks b
                _wait_for(lambda: board.state_name("b") == "Done",
                          msg="b not picked up after unblock")
                _wait_for(lambda: ds.read_status(base=st)["stuck"] == [],
                          msg="stuck did not self-clear after work resumed")
            finally:
                shutdown.set()
                th.join(timeout=2.0)

    def test_force_cancels_in_flight(self):
        # R6 (force): a 2nd signal cancels in-flight workers via stage 1's cooperative
        # cancel, so a long worker stops fast instead of being drained-for.
        board = orch.MockBoard([_issue("a")])
        entered = threading.Event()

        def fake(ticket, *, cancel_event=None, **kw):
            entered.set()
            if cancel_event is not None and cancel_event.wait(timeout=5.0):
                return {"kind": "cancelled", "reason": "reconciliation", "turns": 1,
                        "telemetry": {}}
            return _DONE
        shutdown, force, th, result = self._run_bg(board, fake)
        try:
            _wait_for(entered.is_set, msg="worker never started")
            shutdown.set()  # graceful: worker would otherwise block ~5s on its cancel_event
            force.set()     # force: cancel all in-flight → worker returns fast
            th.join(timeout=2.0)
            self.assertFalse(th.is_alive())  # force-cancel beat the 5s block
        finally:
            shutdown.set()
            force.set()
            th.join(timeout=2.0)


class DaemonBackoffTest(unittest.TestCase):
    """run_forever exponential backoff (daemon stage 3): retry / idle / claim back off
    via `_backoff_s`. Same harness as DaemonLoopTest (bg thread + injected events +
    install_signals=False); small backoff values keep it fast."""

    def _run_bg(self, board, fake, **kw):
        shutdown, force, result = threading.Event(), threading.Event(), {}
        states = orch.resolve_states(board, "T")

        def go():
            with mock.patch("director.orchestrator.dispatch", fake):
                result["out"] = orch.run_forever(
                    board, command=["x"], team="T", states=states,
                    shutdown_event=shutdown, force_event=force, install_signals=False,
                    poll_interval_s=0.02, **kw)
        th = threading.Thread(target=go, daemon=True)
        th.start()
        return shutdown, force, th, result

    # -- IDLE backoff (B) ----------------------------------------------------
    def test_idle_streak_grows_monotonically(self):
        # the idle wait is called with a growing streak 0,1,2,… on consecutive idle ticks.
        board = orch.MockBoard([])
        calls = []

        def spy(poll, streak, cap):
            calls.append(streak)
            return 0.001  # tiny real wait → fast test
        with mock.patch("director.orchestrator._idle_wait_s", spy):
            shutdown, force, th, result = self._run_bg(board, lambda *a, **k: _DONE)
            try:
                _wait_for(lambda: len(calls) >= 3, msg="idle waits not happening")
                self.assertEqual(calls[:3], [0, 1, 2])  # exponential streak input (R4)
            finally:
                shutdown.set()
                th.join(timeout=2.0)

    def test_idle_streak_resets_after_work(self):
        board = orch.MockBoard([])
        calls = []

        def spy(poll, streak, cap):
            calls.append(streak)
            return 0.001
        with mock.patch("director.orchestrator._idle_wait_s", spy):
            shutdown, force, th, result = self._run_bg(board, lambda *a, **k: _DONE)
            try:
                _wait_for(lambda: max(calls or [0]) >= 1, msg="idle streak did not grow")
                n = len(calls)                    # capture BEFORE work (slice spans the reset)
                board._issues["a"] = _issue("a")  # late work appears
                _wait_for(lambda: board.state_name("a") == "Done", msg="late work not claimed")
                # after work the idle streak resets → a fresh 0 appears in the idle calls
                _wait_for(lambda: 0 in calls[n:], msg="idle streak did not reset after work")
            finally:
                shutdown.set()
                th.join(timeout=2.0)

    def test_sustained_poll_failure_backs_off_and_recovers(self):
        # poll-failure (C) subsumed by idle backoff: the board raises for the first polls
        # (daemon backs off via the idle path), then recovers and claims the ticket (R5).
        class FlakyPoll(orch.MockBoard):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                self.polls = 0

            def list_ready_issues(self, team, ready_state_id):
                self.polls += 1
                if self.polls <= 3:
                    raise RuntimeError("board down")
                return super().list_ready_issues(team, ready_state_id)

        board = FlakyPoll([_issue("a")])
        shutdown, force, th, result = self._run_bg(board, lambda *a, **k: _DONE)
        try:
            _wait_for(lambda: board.state_name("a") == "Done",
                      msg="did not recover from sustained poll failure")
        finally:
            shutdown.set()
            th.join(timeout=3.0)

    # -- RETRY backoff (A) ---------------------------------------------------
    def test_retry_is_delayed_by_backoff(self):
        # a failed worker's re-dispatch waits ~backoff_base_s (not immediate, R2), and the
        # daemon keeps ticking during the wait (main thread not blocked).
        board = orch.MockBoard([_issue("a")])
        seen, lock = [], threading.Lock()

        def fake(ticket, *, cancel_event=None, attempt=1, **kw):
            with lock:
                seen.append((attempt, time.monotonic()))
            if attempt == 1:
                return {"kind": "failed", "status": "failed", "turn_id": None, "turns": 1,
                        "telemetry": {}}
            return _DONE
        with tempfile.TemporaryDirectory() as st:
            w = ds.StatusWriter(base=st)
            shutdown, force, th, result = self._run_bg(
                board, fake, backoff_base_s=0.3, backoff_cap_s=10.0, status=w)
            try:
                _wait_for(lambda: any(a == 2 for a, _ in seen), msg="retry never dispatched")
                with lock:
                    a1 = next(t for a, t in seen if a == 1)
                    a2 = next(t for a, t in seen if a == 2)
                self.assertGreaterEqual(a2 - a1, 0.2)  # retry waited ~base (0.3), not immediate
                self.assertGreater((ds.read_status(base=st) or {})["run"]["polls"], 1)  # ticked
            finally:
                shutdown.set()
                th.join(timeout=2.0)

    def test_pending_retry_holds_a_slot(self):
        # R3/D-76: a pending-retry ticket counts against concurrency — with concurrency=1,
        # a second ready ticket is NOT claimed while the first is in its retry backoff.
        board = orch.MockBoard([_issue("a"), _issue("b")])
        seen, lock = [], threading.Lock()

        def fake(ticket, *, cancel_event=None, attempt=1, **kw):
            with lock:
                seen.append(ticket["id"])
            if ticket["id"] == "a" and attempt == 1:
                return {"kind": "failed", "status": "failed", "turn_id": None, "turns": 1,
                        "telemetry": {}}
            return _DONE
        shutdown, force, th, result = self._run_bg(
            board, fake, concurrency=1, backoff_base_s=0.3, backoff_cap_s=10.0)
        try:
            _wait_for(lambda: "a" in seen, msg="a not dispatched")
            time.sleep(0.1)  # inside a's 0.3s backoff window
            with lock:
                self.assertNotIn("b", seen)  # the single slot is reserved by a's pending retry
            _wait_for(lambda: board.state_name("b") == "Done",
                      msg="b never claimed after a's retry resolved")
        finally:
            shutdown.set()
            th.join(timeout=3.0)

    def test_drain_abandons_pending_retry(self):
        # R9/D-81: a graceful shutdown does NOT wait out a pending retry's backoff — it
        # drains (futures empty) and exits, abandoning the retry (left In Progress).
        board = orch.MockBoard([_issue("a")])
        seen = []

        def fake(ticket, *, cancel_event=None, attempt=1, **kw):
            seen.append(attempt)
            if attempt == 1:
                return {"kind": "failed", "status": "failed", "turn_id": None, "turns": 1,
                        "telemetry": {}}
            return _DONE
        shutdown, force, th, result = self._run_bg(
            board, fake, backoff_base_s=5.0, backoff_cap_s=10.0)  # long backoff
        try:
            _wait_for(lambda: 1 in seen, msg="attempt 1 not dispatched")
            shutdown.set()
            th.join(timeout=2.0)
            self.assertFalse(th.is_alive())  # exited promptly — did NOT wait the 5s backoff
            self.assertNotIn(2, seen)        # the scheduled retry was abandoned
        finally:
            shutdown.set()
            th.join(timeout=2.0)

    # -- claim RE-ADMISSION (D) ----------------------------------------------
    def test_claim_failure_is_re_admitted_after_backoff(self):
        # D/D-79: a claim that fails is excluded only until its backoff elapses, then
        # re-admitted — a transient board rejection recovers (not a lifetime exclusion).
        class FlakyClaim(orch.MockBoard):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                self.claim_writes = 0

            def update_issue_state(self, issue_id, state_id):
                if state_id == "st_prog":  # the claim write (Todo → In Progress)
                    self.claim_writes += 1
                    if self.claim_writes <= 2:
                        return False  # transient claim rejection (twice)
                return super().update_issue_state(issue_id, state_id)

        board = FlakyClaim([_issue("a")])
        shutdown, force, th, result = self._run_bg(
            board, lambda *a, **k: _DONE, backoff_base_s=0.05, backoff_cap_s=2.0)
        try:
            _wait_for(lambda: board.state_name("a") == "Done",
                      msg="claim-failed ticket never re-admitted + claimed")
            self.assertGreaterEqual(board.claim_writes, 3)  # 2 rejected + 1 successful claim
        finally:
            shutdown.set()
            th.join(timeout=3.0)

    def test_force_drain_abandons_a_failed_workers_retry(self):
        # supersedes stage 2's `born_cancelled`: a worker that fails as a force-stop lands
        # cannot resurrect an (uncancellable) retry — the daemon SCHEDULES retries and the
        # drain abandons them (D-81), so attempt 2 never spawns and the force-stop is fast.
        board = orch.MockBoard([_issue("a")])
        seen = []

        def fake(ticket, *, cancel_event=None, attempt=1, **kw):
            seen.append(attempt)
            if attempt == 1:
                if cancel_event is not None:
                    cancel_event.wait(timeout=5.0)  # blocks until force-cancelled…
                return {"kind": "failed", "status": "failed", "turn_id": None, "turns": 1,
                        "telemetry": {}}            # …then "crashes" (failed, not cancelled)
            return _DONE
        shutdown, force, th, result = self._run_bg(
            board, fake, backoff_base_s=0.1, backoff_cap_s=10.0)
        try:
            _wait_for(lambda: 1 in seen, msg="attempt 1 not dispatched")
            shutdown.set()
            force.set()  # force-stop while attempt 1 runs
            th.join(timeout=2.0)
            self.assertFalse(th.is_alive())  # exited fast (running worker force-cancelled)
            self.assertNotIn(2, seen)        # the retry was abandoned, never spawned
        finally:
            shutdown.set()
            force.set()
            th.join(timeout=2.0)


class MergeReconcileTest(unittest.TestCase):
    """merge-gated-eligibility R3/R5: _reconcile_merges finalizes merging→done when a
    parked PR has landed, leaving pending/escalated merges in merging. board writes stay
    in the orchestrator; the merger stays board-free (we drive it via the queue)."""

    STATES = {"Todo": {"id": "st_todo", "type": "unstarted"},
              "In Progress": {"id": "st_prog", "type": "started"},
              "Done": {"id": "st_done", "type": "completed"},
              "Merging": {"id": "st_merge", "type": "started"}}

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.qbase = self.tmp / "q"
        # one ticket already parked in `merging` (its worker reported done with a PR)
        self.board = orch.MockBoard([{"id": "u1", "identifier": "D-1", "title": "t",
                                      "description": "d", "prompt": "p", "state_id": "st_merge"}],
                                    states=self.STATES)
        self.states = orch.resolve_states(self.board, "T", {"merging": "Merging"})

    def _sweep(self):
        orch._reconcile_merges(self.board, team="T", states=self.states, queue_base=self.qbase)

    def _answer(self, tid, attempt, result):
        dq.write_answer({"request_id": f"merge|{tid}|a{attempt}", "merge_result": result},
                        base=self.qbase)

    def test_landed_finalizes_to_done(self):
        dq.append_merge_request("u1", pr="p", attempt=1, base=self.qbase)
        self._answer("u1", 1, "merged")
        self._sweep()
        self.assertEqual(self.board._issues["u1"]["state_id"], "st_done")
        self.assertIn("st_done", self.board.transitions["u1"])

    def test_pending_merge_stays_merging(self):
        dq.append_merge_request("u1", pr="p", attempt=1, base=self.qbase)  # no answer → pending
        self._sweep()
        self.assertEqual(self.board._issues["u1"]["state_id"], "st_merge")
        self.assertNotIn("u1", self.board.transitions)  # no board write

    def test_abandoned_merge_stays_merging(self):
        dq.append_merge_request("u1", pr="p", attempt=1, base=self.qbase)
        self._answer("u1", 1, "escalated")  # land lane gave up; Director abandoned
        self._sweep()
        self.assertEqual(self.board._issues["u1"]["state_id"], "st_merge")  # children stay blocked

    def test_idempotent_double_sweep(self):
        dq.append_merge_request("u1", pr="p", attempt=1, base=self.qbase)
        self._answer("u1", 1, "merged")
        self._sweep()
        self._sweep()  # u1 is now `done`, no longer fetched as `merging` → no second write
        self.assertEqual(self.board.transitions["u1"].count("st_done"), 1)

    def test_unconfigured_merging_is_noop(self):
        # no `merging` state → the sweep never reads the board (pure inert)
        states = orch.resolve_states(orch.MockBoard.demo(), "T")  # merging=None
        called = []
        board = orch.MockBoard.demo()
        board.fetch_issues_by_states = lambda *a, **k: called.append(1) or []
        orch._reconcile_merges(board, team="T", states=states, queue_base=self.qbase)
        self.assertEqual(called, [])  # short-circuited before any board read

    def test_fetch_error_is_fail_soft(self):
        def boom(*a, **k):
            raise RuntimeError("board down")
        self.board.fetch_issues_by_states = boom
        self._sweep()  # must not raise — logged + skipped (§8.6)

    def test_per_ticket_error_skips_only_that_ticket(self):
        # u1 landed but its board write raises; u2 landed cleanly → u2 still finalizes.
        self.board._issues["u2"] = {"id": "u2", "identifier": "D-2", "state_id": "st_merge"}
        for t in ("u1", "u2"):
            dq.append_merge_request(t, pr="p", attempt=1, base=self.qbase)
            self._answer(t, 1, "merged")
        orig = self.board.update_issue_state
        def flaky(tid, sid):
            if tid == "u1":
                raise RuntimeError("write failed")
            return orig(tid, sid)
        self.board.update_issue_state = flaky
        self._sweep()
        self.assertEqual(self.board._issues["u2"]["state_id"], "st_done")  # u2 unaffected

    def test_run_forever_sweep_runs_under_saturation(self):
        # review fix: the sweep must run UNCONDITIONALLY each tick, not gated on free slots.
        # concurrency=0 forces free<=0 every tick, so a sweep nested inside `if free > 0`
        # would NEVER run — the landed `merging` ticket finalizing proves it is unconditional.
        dq.append_merge_request("u1", pr="p", attempt=1, base=self.qbase)
        self._answer("u1", 1, "merged")
        orch.run_forever(self.board, command=["x"], team="T", states=self.states,
                         queue_base=self.qbase, concurrency=0, max_ticks=2,
                         shutdown_event=threading.Event(), force_event=threading.Event(),
                         install_signals=False, poll_interval_s=0.01)
        self.assertEqual(self.board.state_name("u1"), "Done")  # finalized despite no free slot


class MergeGatedEligibilityE2ETest(unittest.TestCase):
    """Behavioral E2E (merge-gated-eligibility acceptance 6): a child does NOT dispatch
    until the parent's PR has LANDED on main — only the merge sweep finalizing the parent
    to Done unblocks it. Drives the real run_until_drained loop (poll → sweep → reconcile →
    eligibility); the merger is simulated by writing its merged answer to the queue."""

    STATES = {"Todo": {"id": "st_todo", "type": "unstarted"},
              "In Progress": {"id": "st_prog", "type": "started"},
              "Done": {"id": "st_done", "type": "completed"},
              "Merging": {"id": "st_merge", "type": "started"}}

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.qbase = self.tmp / "q"

    def _pr_done_dispatch(self, order, pr_ids):
        def fake(ticket, **kw):
            order.append(ticket["id"])
            if ticket["id"] in pr_ids:  # opens a PR → parks in merging
                return {"kind": "terminal", "turns": 1, "turn_id": "t",
                        "outcome": {"status": "done", "reason": "ok",
                                    "pr_url": f"http://pr/{ticket['id']}",
                                    "pr_branch": f"feat/{ticket['id']}"}}
            return _done()
        return fake

    def test_child_blocked_until_parent_pr_lands(self):
        board = orch.MockBoard([_issue("p"), _issue("c", ["p"])], states=self.STATES)
        states = orch.resolve_states(board, "T", {"merging": "Merging"})
        order = []
        # Run 1: P dispatches + opens a PR → parks in `merging`; C stays blocked → stuck.
        with mock.patch("director.orchestrator.dispatch", self._pr_done_dispatch(order, {"p"})):
            out1 = orch.run_until_drained(board, command=["x"], team="T", states=states,
                                          queue_base=self.qbase, workspace_root=self.tmp / "ws")
        self.assertEqual(order, ["p"])                      # C did NOT dispatch
        self.assertEqual(board.state_name("p"), "Merging")  # parent parked, NOT Done
        self.assertEqual(out1["stopped_reason"], "stuck")   # C blocked by a merging parent

        # Simulate the serialized merger landing P's PR (consume the request + merged answer).
        dq.write_answer({"request_id": "merge|p|a1", "merge_result": "merged"}, base=self.qbase)

        # Run 2: the sweep finalizes P→Done at the top of the pass → C becomes eligible NOW.
        with mock.patch("director.orchestrator.dispatch", self._pr_done_dispatch(order, {"p"})):
            out2 = orch.run_until_drained(board, command=["x"], team="T", states=states,
                                          queue_base=self.qbase, workspace_root=self.tmp / "ws")
        self.assertIn("c", order)                           # C dispatched only after the land
        self.assertEqual(board.state_name("p"), "Done")     # parent finalized by the sweep
        self.assertEqual(out2["stopped_reason"], "drained")


class BoardSnapshotWiringTest(unittest.TestCase):
    """M3: the poll loops persist the WHOLE board (every state, blocker DAG) to board.json
    via the injected BoardSnapshotter — and a Noop (visibility-off) run writes nothing."""

    def _board(self):
        # `a` is In Progress (not ready, not done), `b` is a Todo blocked by `a` (not done →
        # not eligible). So run_once dispatches NOTHING (fast, no worker), but the snapshot —
        # which fires BEFORE the eligibility check — still captures BOTH across their states.
        return orch.MockBoard([
            {"id": "a", "identifier": "A", "title": "design", "state_id": "st_prog"},
            {"id": "b", "identifier": "B", "title": "impl", "state_id": "st_todo",
             "blockers": ["a"]},
        ])

    def _snapshotter(self, board, board_dir):
        # built exactly as orchestrator.main does: fetch the whole board across all states.
        return bs.BoardSnapshotter(
            fetch=lambda: board.fetch_issues_by_states(
                "T", [v["id"] for v in board.workflow_states("T").values()]),
            writer=bs.BoardWriter(base=board_dir), interval_s=999)

    def test_run_once_persists_whole_board(self):
        board = self._board()
        states = orch.resolve_states(board, "T")
        with tempfile.TemporaryDirectory() as tmp:
            board_dir = Path(tmp) / "director-board"
            res = orch.run_once(board, command=["x"], team="T", states=states,
                                queue_base=Path(tmp) / "q", workspace_root=Path(tmp) / "ws",
                                board_snapshotter=self._snapshotter(board, board_dir))
            snap = bs.read_board(base=board_dir)
            assert snap is not None  # the snapshot fired before the eligibility check
            view = bs.build_board_view(snap["nodes"])
        self.assertEqual(res, [])                                   # nothing eligible → no dispatch
        self.assertEqual({n["id"] for n in view["nodes"]}, {"a", "b"})  # BOTH states captured
        self.assertEqual([(e["from"], e["to"]) for e in view["edges"]], [("a", "b")])
        self.assertEqual(next(n["layer"] for n in view["nodes"] if n["id"] == "b"), 1)

    def test_noop_snapshotter_writes_nothing(self):
        board = self._board()
        states = orch.resolve_states(board, "T")
        with tempfile.TemporaryDirectory() as tmp:
            board_dir = Path(tmp) / "director-board"
            # default board_snapshotter=None → NoopBoardSnapshotter (the off-path)
            orch.run_once(board, command=["x"], team="T", states=states,
                          queue_base=Path(tmp) / "q", workspace_root=Path(tmp) / "ws")
            self.assertIsNone(bs.read_board(base=board_dir))        # byte-identical off-path: no board.json

    def test_run_until_drained_snapshots_each_pass(self):
        board = self._board()
        states = orch.resolve_states(board, "T")
        with tempfile.TemporaryDirectory() as tmp:
            board_dir = Path(tmp) / "director-board"
            orch.run_until_drained(board, command=["x"], team="T", states=states,
                                   queue_base=Path(tmp) / "q", workspace_root=Path(tmp) / "ws",
                                   board_snapshotter=self._snapshotter(board, board_dir))
            snap = bs.read_board(base=board_dir)
            assert snap is not None
        self.assertEqual({n["id"] for n in snap["nodes"]}, {"a", "b"})

    def test_run_forever_snapshots_each_tick(self):
        # the daemon loop also persists the board (the `:950` call site, inside `if not
        # draining:`) — guards a refactor from silently dropping the daemon snapshot.
        board = self._board()
        states = orch.resolve_states(board, "T")
        with tempfile.TemporaryDirectory() as tmp:
            board_dir = Path(tmp) / "director-board"
            orch.run_forever(board, command=["x"], team="T", states=states,
                             queue_base=Path(tmp) / "q", workspace_root=Path(tmp) / "ws",
                             concurrency=0, max_ticks=1, install_signals=False,
                             board_snapshotter=self._snapshotter(board, board_dir))
            snap = bs.read_board(base=board_dir)
            assert snap is not None
        self.assertEqual({n["id"] for n in snap["nodes"]}, {"a", "b"})


if __name__ == "__main__":
    unittest.main()
