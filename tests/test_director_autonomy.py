import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.orchestrator as orch  # noqa: E402
import director.run as run  # noqa: E402
from director import config  # noqa: E402
from director.worker import autonomy  # noqa: E402


class CodexCommandTest(unittest.TestCase):
    def test_wraps_auto_review_and_network_for_both_modes(self):
        # auto_review AND network are shared by both modes (the only difference is the
        # turn-end decider, not the command). Exfil deferred to a one-shot mitigation.
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
        return argparse.Namespace(mock=False, autonomous=autonomous)

    def test_command_wraps_auto_review_and_network_for_both_modes(self):
        # both modes wrap auto_review AND network — identical command; the only
        # watched/un-watched difference is the turn-end decider (not this command).
        # codex_command + posture now come from the resolved config (default = both on).
        posture = config.defaults().posture
        for build in (run._command, orch._command):
            auton = build(self._ns(True), "codex app-server", posture)
            watched = build(self._ns(False), "codex app-server", posture)
            # `-c` not `-lc`: a login shell would re-inject host profile env past the
            # deny-by-default worker-env boundary (worker-secret-boundary M1, T11).
            expected = ["bash", "-c", autonomy.codex_command("codex app-server")]
            self.assertEqual(auton, expected)
            self.assertEqual(watched, expected)               # identical now
            self.assertIn("approvals_reviewer=auto_review", watched[2])
            self.assertIn("network_access", watched[2])       # network shared (exfil deferred)

    def test_command_omits_overrides_when_posture_tightened(self):
        # a host that tightens director.worker (network/auto_review off) → the `-c`
        # overrides are OMITTED (the fail-safe direction; declarative-config slice).
        tight = config.Posture("untrusted", "workspace-write", auto_review=False, network=False)
        cmd = run._command(self._ns(False), "codex app-server", tight)
        self.assertEqual(cmd, ["bash", "-c", "codex app-server"])

    def test_mock_command_never_wrapped(self):
        ns = argparse.Namespace(mock=True, mock_scenario="plain", autonomous=True)
        cmd = run._command(ns, "codex app-server", config.defaults().posture)
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
