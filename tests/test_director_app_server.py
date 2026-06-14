import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.worker.app_server as appsrv  # noqa: E402

MOCK = str(Path(appsrv.__file__).resolve().parent / "_mock_app_server.py")


def _client(scenario, **kw):
    return appsrv.AppServerClient([sys.executable, MOCK, scenario],
                                  cwd=tempfile.gettempdir(), read_timeout_s=5.0, **kw)


class AppServerClientTest(unittest.TestCase):
    def test_plain_turn_completes(self):
        events = []
        with _client("plain", on_event=lambda ev: events.append(ev["method"])) as c:
            c.initialize()
            thread_id = c.thread_start()
            self.assertEqual(thread_id, "thr_mock_1")
            result = c.run_turn(thread_id, "do a harmless thing")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["turn_id"], "turn_mock_1")
        self.assertIn("turn/started", events)
        self.assertIn("turn/completed", events)

    def test_no_server_request_in_plain_turn(self):
        seen = []
        with _client("plain", on_server_request=lambda m, p: seen.append(m) or "accept") as c:
            c.initialize()
            tid = c.thread_start()
            c.run_turn(tid, "x")
        self.assertEqual(seen, [])  # plain turn never asks for a decision


if __name__ == "__main__":
    unittest.main()
