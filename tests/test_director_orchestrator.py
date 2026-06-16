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
import director.status as ds  # noqa: E402

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
                                  "done": "st_done", "failed": None, "blocked": None})

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
    if labels:
        d["labels"] = labels
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


class TypeRoutingTest(unittest.TestCase):
    """Phase 3b: dispatch composes the worker prompt from the ticket's dev-stage type."""

    def test_dispatch_composes_typed_prompt(self):
        captured = {}

        def fake_drive(ticket, **kw):
            captured["prompt"] = ticket["prompt"]
            return _done()

        with mock.patch("director.orchestrator.run.drive", fake_drive):
            orch.dispatch(_issue("a", labels=["spec"]), command=["x"])
        self.assertIn("product-design", captured["prompt"])  # spec template applied
        self.assertIn("p-a", captured["prompt"])              # original task preserved

    def test_dispatch_untyped_passes_raw_prompt(self):
        captured = {}

        def fake_drive(ticket, **kw):
            captured["prompt"] = ticket["prompt"]
            return _done()

        with mock.patch("director.orchestrator.run.drive", fake_drive):
            orch.dispatch(_issue("a"), command=["x"])  # no labels
        self.assertEqual(captured["prompt"], "p-a")  # unchanged (backward compat)

    def test_typed_pipeline_sequenced_with_per_type_prompts(self):
        board = orch.MockBoard([
            _issue("plan", labels=["planning"]),
            _issue("design", ["plan"], labels=["design"]),
            _issue("spec", ["design"], labels=["spec"]),
            _issue("impl", ["spec"], labels=["impl"])])
        states = orch.resolve_states(board, "T")
        seen = []

        def fake_drive(ticket, **kw):
            seen.append((ticket["id"], ticket["prompt"]))
            return _done()

        with mock.patch("director.orchestrator.run.drive", fake_drive):
            out = orch.run_until_drained(board, command=["x"], team="T", states=states)
        self.assertEqual([s[0] for s in seen], ["plan", "design", "spec", "impl"])
        prompts = dict(seen)
        self.assertIn("Decompose", prompts["plan"])         # planning template
        self.assertIn("design-docs", prompts["design"])     # design template
        self.assertIn("product-design", prompts["spec"])    # spec template
        self.assertIn("execplan", prompts["impl"])          # impl template
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

    def test_explicit_ticket_workspace_is_used(self):
        orch.reconcile(self.board, {"id": "u1", "workspace": "/custom/ws"},
                       self._done(pr_url="u", pr_branch="b"), 1, self.states, 1,
                       queue_base=self.qbase)
        self.assertEqual(self._merge_reqs()[0]["workspace_path"], "/custom/ws")


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
        self.assertEqual(row["final_state"], "released")
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


if __name__ == "__main__":
    unittest.main()
