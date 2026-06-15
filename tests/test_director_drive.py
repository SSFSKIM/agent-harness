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
        self.assertEqual(calls[0][1], "first prompt")        # turn 0 = the ticket prompt
        self.assertEqual(calls[1][1], "DO_APPROACH_A")       # turn 1 = the Director's reply
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
