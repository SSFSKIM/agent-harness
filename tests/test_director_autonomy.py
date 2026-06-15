import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.orchestrator as orch  # noqa: E402
import director.run as run  # noqa: E402
from director.worker import autonomy  # noqa: E402


class CodexCommandTest(unittest.TestCase):
    def test_appends_both_overrides(self):
        out = autonomy.codex_command("codex app-server")
        self.assertEqual(
            out,
            "codex app-server -c approvals_reviewer=auto_review "
            "-c sandbox_workspace_write.network_access=true")

    def test_preset_constants(self):
        self.assertEqual(autonomy.APPROVAL_POLICY, "on-request")
        self.assertEqual(autonomy.SANDBOX, "workspace-write")


class _FakeClient:
    """Records the posture run_ticket passes to thread_start / run_turn."""
    seen: dict = {}

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def initialize(self):
        pass

    def thread_start(self, model=None, tools=None,
                     approval_policy="untrusted", sandbox="workspace-write"):
        _FakeClient.seen["thread"] = (approval_policy, sandbox)
        return "thr_1"

    def run_turn(self, thread_id, text, approval_policy="untrusted", sandbox_policy=None):
        _FakeClient.seen["turn"] = approval_policy
        return {"status": "completed", "turn_id": "t1"}


class RunTicketPostureTest(unittest.TestCase):
    def setUp(self):
        _FakeClient.seen = {}

    def _run(self, **kw):
        with tempfile.TemporaryDirectory() as ws:
            ticket = {"id": "T-1", "prompt": "do it", "workspace": ws}
            with mock.patch("director.run.AppServerClient", _FakeClient):
                run.run_ticket(ticket, command=["x"], **kw)
        return _FakeClient.seen

    def test_autonomous_posture_reaches_thread_and_turn(self):
        seen = self._run(approval_policy="on-request", sandbox="workspace-write")
        self.assertEqual(seen["thread"], ("on-request", "workspace-write"))
        self.assertEqual(seen["turn"], "on-request")

    def test_default_posture_is_untrusted(self):
        seen = self._run()
        self.assertEqual(seen["thread"], ("untrusted", "workspace-write"))
        self.assertEqual(seen["turn"], "untrusted")


class CommandWrapTest(unittest.TestCase):
    def _ns(self, autonomous):
        return argparse.Namespace(mock=False, autonomous=autonomous, codex="codex app-server")

    def test_run_command_wrapped_only_when_autonomous(self):
        self.assertEqual(run._command(self._ns(True)),
                         ["bash", "-lc", autonomy.codex_command("codex app-server")])
        self.assertEqual(run._command(self._ns(False)),
                         ["bash", "-lc", "codex app-server"])

    def test_orchestrator_command_wrapped_only_when_autonomous(self):
        self.assertEqual(orch._command(self._ns(True)),
                         ["bash", "-lc", autonomy.codex_command("codex app-server")])
        self.assertEqual(orch._command(self._ns(False)),
                         ["bash", "-lc", "codex app-server"])

    def test_mock_command_never_wrapped(self):
        ns = argparse.Namespace(mock=True, mock_scenario="plain",
                                autonomous=True, codex="codex app-server")
        cmd = run._command(ns)
        self.assertNotIn("approvals_reviewer", " ".join(cmd))


class OrchestratorThreadsPostureTest(unittest.TestCase):
    def test_run_until_drained_threads_posture_to_drive(self):
        board = orch.MockBoard([{"id": "a", "identifier": "A", "title": "t",
                                 "description": "d", "prompt": "p", "state_id": "st_todo"}])
        states = orch.resolve_states(board, "T")
        captured = {}

        def fake_drive(ticket, **kw):
            captured["approval_policy"] = kw.get("approval_policy")
            captured["sandbox"] = kw.get("sandbox")
            return {"kind": "terminal", "outcome": {"status": "done"}, "turns": 1}

        with mock.patch("director.orchestrator.run.drive", fake_drive):
            orch.run_until_drained(board, command=["x"], team="T", states=states,
                                   approval_policy="on-request", sandbox="workspace-write")
        self.assertEqual(captured["approval_policy"], "on-request")
        self.assertEqual(captured["sandbox"], "workspace-write")


if __name__ == "__main__":
    unittest.main()
