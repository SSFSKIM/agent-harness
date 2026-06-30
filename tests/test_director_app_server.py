import inspect
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.worker.app_server as appsrv  # noqa: E402
from director import config  # noqa: E402

MOCK = str(Path(appsrv.__file__).resolve().parent / "_mock_app_server.py")


def _client(scenario, **kw):
    return appsrv.AppServerClient([sys.executable, MOCK, scenario],
                                  cwd=tempfile.gettempdir(), read_timeout_s=5.0, **kw)


class AppServerClientTest(unittest.TestCase):
    def test_cwd_is_absolutized(self):
        # A RELATIVE cwd is meaningless across the stdio boundary: it is both the worker
        # subprocess working dir AND sent as thread/start params.cwd, which a Claude worker
        # re-resolves against its OWN cwd (it's launched in that dir) -> a relative path
        # double-resolves to a nonexistent dir and the SDK spawn dies with ENOENT. The
        # client must store/send an ABSOLUTE cwd. (Host default workspace root is relative.)
        c = appsrv.AppServerClient([sys.executable, MOCK, "plain"],
                                   cwd=".claude/harness/director-workspaces/T-1")
        self.assertTrue(Path(c.cwd).is_absolute(), f"cwd must be absolute, got {c.cwd!r}")
        self.assertEqual(Path(c.cwd), (Path.cwd() / ".claude/harness/director-workspaces/T-1"))

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


class DefaultsDriftTest(unittest.TestCase):
    """R4.2 (Slice 4): app_server's FALLBACK worker posture must derive from the single
    source `config.DEFAULTS["worker"]`, never a second hardcoded copy that can silently
    drift. This FAILS on the pre-reconciliation code, where `thread_start` defaulted to
    `"untrusted"` while `config.DEFAULTS["worker"]["approval_policy"]` is `"on-request"`."""

    def test_thread_start_defaults_match_config(self):
        params = inspect.signature(appsrv.AppServerClient.thread_start).parameters
        worker = config.DEFAULTS["worker"]
        self.assertEqual(params["approval_policy"].default, worker["approval_policy"])
        self.assertEqual(params["sandbox"].default, worker["sandbox"])

    def test_run_turn_default_matches_config(self):
        params = inspect.signature(appsrv.AppServerClient.run_turn).parameters
        self.assertEqual(params["approval_policy"].default,
                         config.DEFAULTS["worker"]["approval_policy"])


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


class CancelTest(unittest.TestCase):
    """Reconciliation cancel plumbing (active-run-reconciliation M2)."""

    def test_turncancelled_is_not_appservererror(self):
        # drive must distinguish a cancel (release, no retry) from a failure
        # (retry-once), so the cancel exception is deliberately NOT an AppServerError.
        self.assertFalse(issubclass(appsrv.TurnCancelled, appsrv.AppServerError))

    def _sleeper(self, ev):
        # a subprocess that never emits output → the read wait blocks until cancel
        c = appsrv.AppServerClient([sys.executable, "-c", "import time; time.sleep(30)"],
                                   cwd=tempfile.gettempdir(), read_timeout_s=10.0,
                                   cancel_event=ev)
        return c.start()

    def test_wait_readable_raises_when_event_preset(self):
        import threading
        ev = threading.Event()
        ev.set()
        c = self._sleeper(ev)
        try:
            with self.assertRaises(appsrv.TurnCancelled):
                c._wait_readable()
        finally:
            c.stop()

    def test_wait_readable_interrupts_mid_wait(self):
        import threading
        import time
        ev = threading.Event()
        c = self._sleeper(ev)
        timer = threading.Timer(0.3, ev.set)
        timer.start()
        try:
            start = time.monotonic()
            with self.assertRaises(appsrv.TurnCancelled):
                c._wait_readable()
            # interrupted within ~poll+0.3s — well before the 10s read_timeout (R4)
            self.assertLess(time.monotonic() - start, 5.0)
        finally:
            timer.cancel()
            c.stop()


class WorkerStderrCaptureTest(unittest.TestCase):
    """A worker that dies/closes the stream must be self-diagnosing: the harness drains the
    worker subprocess stderr and appends its tail to the "app-server closed" error. Before
    this, stderr was piped to DEVNULL, so the F11 codex crash surfaced only as an opaque
    "app-server closed during turn" and root-cause required mining the codex rollout."""

    def _dying_server(self, body: str):
        # A fake app-server: runs `body` (e.g. writes to stderr), consumes the initialize
        # request line so the client's _send doesn't BrokenPipe, then exits WITHOUT writing
        # stdout -> the client reads stdout EOF and raises "app-server closed during ...".
        script = f"import sys, os\n{body}\nsys.stdin.readline()\nos._exit(0)\n"
        return appsrv.AppServerClient([sys.executable, "-c", script],
                                      cwd=tempfile.gettempdir(), read_timeout_s=5.0)

    def test_stderr_tail_surfaced_on_close(self):
        c = self._dying_server("sys.stderr.write('DIAG_BOOM_SENTINEL\\n'); sys.stderr.flush()")
        with c:
            with self.assertRaises(appsrv.AppServerError) as cm:
                c.initialize()
        msg = str(cm.exception)
        self.assertIn("app-server closed during initialize", msg)
        self.assertIn("worker stderr tail", msg)
        self.assertIn("DIAG_BOOM_SENTINEL", msg)  # the actual reason, no longer discarded

    def test_no_stderr_keeps_message_clean(self):
        # A close with NO stderr must not append an empty "tail" noise suffix.
        c = self._dying_server("pass")
        with c:
            with self.assertRaises(appsrv.AppServerError) as cm:
                c.initialize()
        self.assertNotIn("worker stderr tail", str(cm.exception))

    def test_stderr_tail_is_bounded(self):
        # A chatty/panicking worker can't grow the buffer without limit: only the last
        # _STDERR_TAIL_LINES survive (oldest dropped), so the tail shows the final state.
        body = f"[sys.stderr.write('L%d\\n' % i) for i in range({appsrv._STDERR_TAIL_LINES + 150})]; sys.stderr.flush()"
        c = self._dying_server(body)
        with c:
            with self.assertRaises(appsrv.AppServerError):
                c.initialize()
        tail = list(c._stderr_tail)
        self.assertLessEqual(len(tail), appsrv._STDERR_TAIL_LINES)
        self.assertIn(f"L{appsrv._STDERR_TAIL_LINES + 149}", tail)  # newest kept
        self.assertNotIn("L0", tail)                                # oldest dropped

    def test_stderr_no_newline_flood_is_bounded(self):
        # P1 (reliability review): a no-newline flood must not grow the in-flight drain
        # accumulator without bound (that would just move the unbounded growth from the
        # kernel pipe into the daemon heap). The drain caps the unframed remainder, so every
        # captured line stays <= the per-line cap even with zero newlines in the stream.
        n = appsrv._STDERR_LINE_CAP * 4
        c = self._dying_server(f"sys.stderr.write('x' * {n}); sys.stderr.flush()")
        with c:
            with self.assertRaises(appsrv.AppServerError):
                c.initialize()
        tail = list(c._stderr_tail)
        self.assertTrue(tail)  # the flood was captured (not dropped wholesale)
        self.assertTrue(all(len(ln) <= appsrv._STDERR_LINE_CAP for ln in tail),
                        "every captured stderr line must be bounded by _STDERR_LINE_CAP")


class ProtocolTailTest(unittest.TestCase):
    """For a SILENT close (the F11 class: codex exits mid-turn with empty stderr, no JSON-RPC
    error), the last received protocol messages are the actual diagnostic — they show the close
    happened mid-stream, not that the harness mishandled a request. They are appended to the
    'app-server closed' error so the next such failure is self-diagnosing from the disposition."""

    def _server_that_streams_then_closes(self, lines: str):
        # Fake app-server: consume the initialize request, emit `lines` (raw stdout JSON-RPC),
        # then exit WITHOUT the initialize result -> the client reads those messages then EOF.
        script = ("import sys, json, os\n"
                  "sys.stdin.readline()\n"
                  f"{lines}\n"
                  "sys.stdout.flush()\n"
                  "os._exit(0)\n")
        return appsrv.AppServerClient([sys.executable, "-c", script],
                                      cwd=tempfile.gettempdir(), read_timeout_s=5.0)

    def test_close_error_lists_last_protocol_messages(self):
        lines = (r"sys.stdout.write(json.dumps({'method':'thread/started','params':{}})+'\n')" "\n"
                 r"sys.stdout.write(json.dumps({'method':'item/completed','params':{'item':{'type':'agentMessage'}}})+'\n')")
        c = self._server_that_streams_then_closes(lines)
        with c:
            with self.assertRaises(appsrv.AppServerError) as cm:
                c.initialize()
        msg = str(cm.exception)
        self.assertIn("last app-server messages", msg)
        self.assertIn("thread/started", msg)
        self.assertIn("item/completed[agentMessage]", msg)  # item TYPE surfaced (the F11 signal)

    def test_clean_message_when_nothing_received(self):
        # A close with no received messages must not append an empty tail suffix.
        c = appsrv.AppServerClient(
            [sys.executable, "-c", "import sys, os; sys.stdin.readline(); os._exit(0)"],
            cwd=tempfile.gettempdir(), read_timeout_s=5.0)
        with c:
            with self.assertRaises(appsrv.AppServerError) as cm:
                c.initialize()
        self.assertNotIn("last app-server messages", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
