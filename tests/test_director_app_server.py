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

    def test_run_turn_captures_usage_and_rate_limits(self):
        # M1: a turn that emits a thread/tokenUsage/updated surfaces absolute totals
        # (and any rate-limit payload) on run_turn's result.
        with _client("usage") as c:
            c.initialize()
            tid = c.thread_start()
            res = c.run_turn(tid, "do work")
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["usage"], {"input": 60, "output": 40, "total": 100})

    def test_run_turn_usage_none_when_no_usage_event(self):
        # A plain turn emits no usage notification → usage/rate_limits are None,
        # never fabricated (R6 tolerance).
        with _client("plain") as c:
            c.initialize()
            tid = c.thread_start()
            res = c.run_turn(tid, "x")
        self.assertIsNone(res["usage"])
        self.assertIsNone(res["rate_limits"])

    def test_run_turn_survives_malformed_usage_event(self):
        # R6: a malformed usage notification yields usage None and the turn STILL
        # completes — telemetry is instrumentation, never a gate on the turn.
        with _client("usage_bad") as c:
            c.initialize()
            tid = c.thread_start()
            res = c.run_turn(tid, "x")
        self.assertEqual(res["status"], "completed")
        self.assertIsNone(res["usage"])


class ExtractUsageTest(unittest.TestCase):
    def test_absolute_wrapper_any_event(self):
        # total_token_usage rides on any event type → absolute totals.
        u = appsrv.extract_usage("something/else",
                                 {"total_token_usage": {"input_tokens": 10,
                                                        "output_tokens": 5,
                                                        "total_tokens": 15}})
        self.assertEqual(u, {"input": 10, "output": 5, "total": 15})

    def test_dedicated_notification_flat_totals(self):
        u = appsrv.extract_usage("thread/tokenUsage/updated",
                                 {"input_tokens": 7, "output_tokens": 3})
        self.assertEqual(u, {"input": 7, "output": 3, "total": 10})  # total derived

    def test_lenient_field_names(self):
        # camelCase + prompt/completion synonyms are accepted (§13.5 lenient).
        u = appsrv.extract_usage("thread/tokenUsage/updated",
                                 {"usage": {"promptTokens": 12, "completionTokens": 8,
                                            "totalTokens": 20}})
        self.assertEqual(u, {"input": 12, "output": 8, "total": 20})

    def test_real_codex_0139_nested_shape(self):
        # The EXACT live-pinned codex-cli 0.139.0 payload: absolute totals nested under
        # tokenUsage.total; tokenUsage.last (the per-turn delta) MUST be ignored — if it
        # weren't, total would be the bogus 999, not 26420.
        params = {"threadId": "t", "turnId": "u",
                  "tokenUsage": {
                      "total": {"totalTokens": 26420, "inputTokens": 26391,
                                "cachedInputTokens": 4480, "outputTokens": 29,
                                "reasoningOutputTokens": 22},
                      "last": {"totalTokens": 999, "inputTokens": 999, "outputTokens": 999},
                      "modelContextWindow": 258400}}
        u = appsrv.extract_usage("thread/tokenUsage/updated", params)
        self.assertEqual(u, {"input": 26391, "output": 29, "total": 26420})

    def test_delta_only_payload_ignored(self):
        # A lone last_token_usage (per-turn delta) is NOT a cumulative total → None,
        # so the run aggregate never double-counts.
        self.assertIsNone(appsrv.extract_usage(
            "thread/tokenUsage/updated",
            {"last_token_usage": {"input_tokens": 4, "output_tokens": 1, "total_tokens": 5}}))

    def test_missing_or_nonusage_is_none(self):
        self.assertIsNone(appsrv.extract_usage("turn/completed", {"turn": {"id": "t"}}))
        self.assertIsNone(appsrv.extract_usage("thread/tokenUsage/updated", {}))
        self.assertIsNone(appsrv.extract_usage("x", "not a dict"))  # type: ignore[arg-type]

    def test_rate_limits_latest_payload(self):
        self.assertEqual(appsrv.extract_rate_limits({"rate_limits": {"remaining": 9}}),
                         {"remaining": 9})
        self.assertEqual(appsrv.extract_rate_limits({"rateLimits": {"remaining": 8}}),
                         {"remaining": 8})
        self.assertIsNone(appsrv.extract_rate_limits({"other": 1}))


if __name__ == "__main__":
    unittest.main()
