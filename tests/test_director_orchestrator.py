import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.director_min as dmin  # noqa: E402
import director.orchestrator as orch  # noqa: E402
import director.queue as dq  # noqa: E402
import director.run as run  # noqa: E402

MOCK = str(Path(run.__file__).resolve().parent / "worker" / "_mock_app_server.py")


class ResolveStatesTest(unittest.TestCase):
    def test_resolves_defaults_to_ids(self):
        states = orch.resolve_states(orch.MockBoard.demo(), "T")
        self.assertEqual(states, {"ready": "st_todo", "started": "st_prog",
                                  "done": "st_done", "failed": None})

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
                    board, command=[sys.executable, MOCK, "approval"],
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
            return {"status": "completed", "turn_id": "t"}

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
            return {"status": "failed", "turn_id": None}

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
                        lambda ticket, **kw: {"status": "failed", "turn_id": None}):
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
                        lambda ticket, **kw: {"status": "completed", "turn_id": "t"}):
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
                        lambda ticket, **kw: {"status": "completed", "turn_id": "t"}):
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
            return {"status": "completed", "turn_id": "t"}

        with mock.patch("director.orchestrator.dispatch", fake):
            res = orch.run_once(board, command=["x"], team="T", states=states)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(len(res), 1)


class MainCliTest(unittest.TestCase):
    def test_main_mock_runs_and_reconciles(self):
        board = orch.MockBoard.demo()
        with tempfile.TemporaryDirectory() as q, tempfile.TemporaryDirectory() as ws:
            rc = orch.main(["--team", "T", "--mock", "--mock-scenario", "plain",
                            "--queue-dir", q, "--workspace-root", ws,
                            "--concurrency", "2"], board=board)
        self.assertEqual(rc, 0)
        self.assertEqual(board.state_name("u1"), "Done")
        self.assertEqual(board.state_name("u2"), "Done")


if __name__ == "__main__":
    unittest.main()
