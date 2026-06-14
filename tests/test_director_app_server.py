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

    def test_turn_start_error_raises_not_timeout(self):
        # P2-4 fix: a turn/start error response surfaces as AppServerError, not ReadTimeout.
        with _client("turn_error") as c:
            c.initialize()
            tid = c.thread_start()
            with self.assertRaises(appsrv.AppServerError):
                c.run_turn(tid, "x")

    def test_no_server_request_in_plain_turn(self):
        seen = []
        with _client("plain", on_server_request=lambda m, p: seen.append(m) or "accept") as c:
            c.initialize()
            tid = c.thread_start()
            c.run_turn(tid, "x")
        self.assertEqual(seen, [])  # plain turn never asks for a decision

    def test_tool_call_routes_to_tool_executor(self):
        # W1: a Codex item/tool/call is routed to tool_executor, not the approval seam.
        calls = []

        def tool_exec(name, args):
            calls.append((name, args))
            return {"success": True, "output": "ok"}

        with _client("tool", tool_executor=tool_exec) as c:
            c.initialize()
            tid = c.thread_start(tools=[{"name": "linear_graphql", "description": "d",
                                         "inputSchema": {"type": "object"}}])
            res = c.run_turn(tid, "use the tool")
        self.assertEqual(res["status"], "completed")
        self.assertEqual(calls, [("linear_graphql", {"query": "query { viewer { id } }"})])

    def test_normalize_tool_result_shape(self):
        n = appsrv.normalize_tool_result({"success": True, "output": "x"})
        self.assertEqual(n, {"success": True, "output": "x",
                             "contentItems": [{"type": "inputText", "text": "x"}]})
        n2 = appsrv.normalize_tool_result({"success": False})  # no output -> JSON-encoded
        self.assertIsInstance(n2["output"], str)
        self.assertEqual(n2["contentItems"][0]["type"], "inputText")


if __name__ == "__main__":
    unittest.main()
