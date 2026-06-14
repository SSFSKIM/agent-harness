import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.queue as dq  # noqa: E402
import director.worker.app_server as appsrv  # noqa: E402
from director.worker.approval import make_seam  # noqa: E402

MOCK = str(Path(appsrv.__file__).resolve().parent / "_mock_app_server.py")


def _wait_pending(base, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pending = dq.read_pending(base=base)
        if pending:
            return pending[0]
        time.sleep(0.02)
    return None


def _worker(scenario, seam, out):
    client = appsrv.AppServerClient([sys.executable, MOCK, scenario],
                                    cwd=tempfile.gettempdir(),
                                    on_server_request=seam, read_timeout_s=5.0)
    with client as c:
        c.initialize()
        tid = c.thread_start()
        out["res"] = c.run_turn(tid, "do a risky thing")


class SeamTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp()) / "q"

    def test_approval_routes_to_director_and_resumes_same_turn(self):
        # The novel core: worker pauses on approval, Director answers, SAME turn resumes.
        seam = make_seam("T-1", "/ws", base=self.base, timeout_s=5.0)
        out = {}
        th = threading.Thread(target=_worker, args=("approval", seam, out))
        th.start()

        req = _wait_pending(self.base)
        self.assertIsNotNone(req, "worker did not route a request to the Director")
        self.assertEqual(req["kind"], "commandApproval")
        self.assertEqual(req["payload"]["command"], ["rm", "-rf", "/tmp/cache"])
        # worker is blocked, not dead: still pending, turn not yet finished
        self.assertNotIn("res", out)

        dq.write_answer({"request_id": req["request_id"], "decision": "accept",
                         "answered_by": "director", "answered_at": "t"}, base=self.base)
        th.join(timeout=10)

        self.assertEqual(out["res"]["status"], "completed")
        # the approval was raised INSIDE the turn that then completed (same turn id)
        self.assertTrue(req["session_id"].endswith(out["res"]["turn_id"]))
        self.assertEqual(out["res"]["turn_id"], "turn_mock_1")

    def test_no_answer_declines_but_turn_still_completes(self):
        # plan R7: a missing answer must not hang the turn forever.
        seam = make_seam("T-2", "/ws", base=self.base, timeout_s=0.4)
        out = {}
        _worker("approval", seam, out)  # synchronous; no Director ever answers
        self.assertEqual(out["res"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
