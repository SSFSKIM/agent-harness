import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.run as run  # noqa: E402
from director.decider import CONTINUE_REPLY, autonomous_decide  # noqa: E402
from director.worker.app_server import AppServerClient  # noqa: E402

MOCK = str(Path(run.__file__).resolve().parent / "worker" / "_mock_app_server.py")


def _cmd(scenario):
    return [sys.executable, MOCK, scenario]


def _spy_run_turn():
    """Patch AppServerClient.run_turn to record (thread_id, input_text) per call,
    delegating to the real method. Returns (patcher, calls-list)."""
    calls = []
    orig = AppServerClient.run_turn

    def spy(self, thread_id, text, **kw):
        calls.append((thread_id, text))
        return orig(self, thread_id, text, **kw)

    return mock.patch.object(AppServerClient, "run_turn", spy), calls


class DriveLoopTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _ticket(self, prompt="do the work"):
        return {"id": "DRV-1", "prompt": prompt, "workspace": str(self.tmp / "ws")}

    def test_multi_turn_same_thread_until_terminal(self):
        # Scripted decider: reply, reply, then terminal — proves a ticket spans ≥2
        # turns on ONE thread (R1) and the board would move only at terminal (R3/R4).
        seq = iter(["reply", "reply", "terminal"])

        def decider(ctx):
            kind = next(seq)
            if kind == "terminal":
                return {"kind": "terminal",
                        "outcome": {"status": "done", "reason": "scripted",
                                    "spawned_ticket_ids": []}}
            return {"kind": "reply", "reply": "keep going"}

        patcher, calls = _spy_run_turn()
        with patcher:
            disp = run.drive(self._ticket(), command=_cmd("plain"), decide=decider,
                             workspace_root=self.tmp / "wsr", max_turns=8)

        self.assertEqual(disp["kind"], "terminal")
        self.assertEqual(disp["turns"], 3)
        self.assertEqual(disp["outcome"]["status"], "done")
        self.assertEqual(len(calls), 3)
        # every turn ran on the SAME thread id (R1)
        self.assertEqual({tid for tid, _ in calls}, {disp["thread_id"]})

    def test_first_turn_carries_terminal_contract(self):
        # The worker must be TOLD (where it reads it) to call report_outcome at terminal,
        # else un-watched a finished worker loops to stuck. drive injects the contract on
        # turn 0; the decider's reply (not the contract) drives later turns.
        def decider(ctx):
            if ctx["turn_index"] == 0:
                return {"kind": "reply", "reply": "go on"}
            return {"kind": "terminal", "outcome": {"status": "done"}}

        patcher, calls = _spy_run_turn()
        with patcher:
            run.drive(self._ticket("BUILD THING"), command=_cmd("plain"),
                      decide=decider, workspace_root=self.tmp / "wsc")
        self.assertIn("BUILD THING", calls[0][1])        # the task is there
        self.assertIn("report_outcome", calls[0][1])     # …plus the terminal contract
        self.assertNotIn("report_outcome", calls[1][1])  # turn 1 = just the reply

    def test_reply_is_fed_as_next_turn_input(self):
        # A non-terminal disposition's free-form reply becomes the NEXT turn's input
        # verbatim (D-45: content-bearing, not a fixed "continue").
        seen_ctx = []

        def decider(ctx):
            seen_ctx.append(ctx)
            if ctx["turn_index"] == 0:
                return {"kind": "reply", "reply": "DO_APPROACH_A"}
            return {"kind": "terminal",
                    "outcome": {"status": "done", "reason": "ok", "spawned_ticket_ids": []}}

        patcher, calls = _spy_run_turn()
        with patcher:
            disp = run.drive(self._ticket("first prompt"), command=_cmd("plain"),
                             decide=decider, workspace_root=self.tmp / "wsr2")

        self.assertEqual(disp["kind"], "terminal")
        self.assertIn("first prompt", calls[0][1])           # turn 0 = ticket prompt (+contract)
        self.assertEqual(calls[1][1], "DO_APPROACH_A")       # turn 1 = the Director's reply (verbatim)
        self.assertEqual(seen_ctx[0]["final_message"], "done")  # captured turn-end message

    def test_report_outcome_done_drives_autonomous_terminal(self):
        # The worker calls report_outcome(done) → the sink captures it → the autonomous
        # decider returns terminal on turn 1 (D-44 structured terminal signal).
        disp = run.drive(self._ticket(), command=_cmd("report"),
                         decide=autonomous_decide, workspace_root=self.tmp / "wsr3")
        self.assertEqual(disp["kind"], "terminal")
        self.assertEqual(disp["turns"], 1)
        self.assertEqual(disp["outcome"]["status"], "done")
        self.assertEqual(disp["outcome"]["reason"], "mock done")

    def test_autonomous_no_signal_loops_to_stuck(self):
        # No terminal signal (plain scenario) → autonomous decider keeps replying →
        # the run hits the max_turns bound and reports stuck (R6).
        disp = run.drive(self._ticket(), command=_cmd("plain"),
                         decide=autonomous_decide, workspace_root=self.tmp / "wsr4",
                         max_turns=3)
        self.assertEqual(disp["kind"], "stuck")
        self.assertEqual(disp["reason"], "max_turns")
        self.assertEqual(disp["turns"], 3)

    def test_turn_failure_is_failed_disposition(self):
        disp = run.drive(self._ticket(), command=_cmd("turn_failed"),
                         decide=autonomous_decide, workspace_root=self.tmp / "wsr5")
        self.assertEqual(disp["kind"], "failed")
        self.assertEqual(disp["status"], "failed")
        self.assertEqual(disp["turns"], 1)

    def test_telemetry_keeps_latest_absolute_across_turns(self):
        # M2: the `usage` scenario emits rising CUMULATIVE totals (turn n → n*100).
        # Over 2 turns drive keeps the LATEST absolute (200), NOT the sum (300) —
        # §13.5 anti-double-count. session_id/turn_count/last_message also captured.
        seq = iter(["reply", "terminal"])

        def decider(ctx):
            if next(seq) == "terminal":
                return {"kind": "terminal", "outcome": {"status": "done", "reason": "ok"}}
            return {"kind": "reply", "reply": "go"}

        disp = run.drive(self._ticket(), command=_cmd("usage"), decide=decider,
                         workspace_root=self.tmp / "wstel", max_turns=8)
        self.assertEqual(disp["kind"], "terminal")
        tel = disp["telemetry"]
        self.assertEqual(tel["tokens"], {"input": 120, "output": 80, "total": 200})
        self.assertEqual(tel["turn_count"], 2)
        self.assertEqual(tel["session_id"], f"{disp['thread_id']}-{disp['turn_id']}")
        self.assertEqual(tel["last_message"], "done")

    def test_telemetry_present_without_usage_events(self):
        # No usage notifications (report scenario) → tokens None, but the rest of the
        # telemetry block is still populated (R6: absent ≠ broken).
        disp = run.drive(self._ticket(), command=_cmd("report"),
                         decide=autonomous_decide, workspace_root=self.tmp / "wstel2")
        tel = disp["telemetry"]
        self.assertIsNone(tel["tokens"])
        self.assertEqual(tel["turn_count"], 1)
        self.assertEqual(tel["session_id"], f"{disp['thread_id']}-{disp['turn_id']}")


class AutonomousDeciderUnitTest(unittest.TestCase):
    def test_done_and_blocked_are_terminal(self):
        for status in ("done", "blocked"):
            disp = autonomous_decide({"outcome": {"status": status, "reason": "r"}})
            self.assertEqual(disp["kind"], "terminal")
            self.assertEqual(disp["outcome"]["status"], status)

    def test_needs_human_escalates(self):
        disp = autonomous_decide({"outcome": {"status": "needs_human", "reason": "taste"}})
        self.assertEqual(disp["kind"], "escalate")
        self.assertEqual(disp["reason"], "taste")

    def test_no_outcome_replies_self_resolve(self):
        disp = autonomous_decide({"outcome": None, "final_message": "A or B?"})
        self.assertEqual(disp["kind"], "reply")
        self.assertEqual(disp["reply"], CONTINUE_REPLY)


if __name__ == "__main__":
    unittest.main()
