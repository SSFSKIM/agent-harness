import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.ticket_events as te  # noqa: E402

# --- representative raw notifications, pinned against both adapters ----------------
# codex-cli 0.139.0: thread/tokenUsage/updated nests tokenUsage.total
_CODEX_USAGE = ("thread/tokenUsage/updated",
                {"tokenUsage": {"total": {"totalTokens": 100, "inputTokens": 60, "outputTokens": 40}}})
# claude adapter (worker-runtime/app-server translator.ts): same method, same nested shape
_CLAUDE_USAGE = ("thread/tokenUsage/updated",
                 {"threadId": "t", "turnId": "u",
                  "tokenUsage": {"total": {"totalTokens": 100, "inputTokens": 60, "outputTokens": 40}}})
_AGENT_MSG = ("item/completed", {"item": {"type": "agentMessage", "text": "working on it", "phase": "commentary"}})
_FINAL_MSG = ("item/completed", {"item": {"type": "agentMessage", "text": "all done", "phase": "final_answer"}})
# claude broker tool-call shape: item.type=="dynamicToolCall", item.tool, contentItems
_CLAUDE_TOOL = ("item/completed", {"item": {"type": "dynamicToolCall", "tool": "Bash",
                                            "arguments": {"command": "ls"}, "status": "completed",
                                            "contentItems": [{"type": "inputText", "text": "a\nb"}], "success": True}})
# codex exec item
_CODEX_TOOL = ("item/completed", {"item": {"type": "commandExecution", "command": ["echo", "hi"]}})


class NormalizeTest(unittest.TestCase):
    def test_turn_lifecycle(self):
        s = te.normalize_event("turn/started", {"turn": {"id": "u1"}}, seq=0, now=lambda: "T")
        self.assertEqual(s, {"seq": 0, "ts": "T", "kind": "turn_started", "turn_id": "u1"})
        for m, st in (("turn/completed", "completed"), ("turn/failed", "failed"), ("turn/cancelled", "cancelled")):
            e = te.normalize_event(m, {"turn": {"id": "u1"}}, seq=1, now=lambda: "T")
            self.assertEqual(e["kind"], "turn_ended")
            self.assertEqual(e["status"], st)

    def test_agent_message_commentary_and_final(self):
        c = te.normalize_event(*_AGENT_MSG, seq=0, now=lambda: "T")
        self.assertEqual(c, {"seq": 0, "ts": "T", "kind": "agent_message", "phase": "commentary", "text": "working on it"})
        f = te.normalize_event(*_FINAL_MSG, seq=0, now=lambda: "T")
        self.assertEqual(f["phase"], "final_answer")

    def test_empty_agent_message_dropped(self):
        e = te.normalize_event("item/completed", {"item": {"type": "agentMessage", "text": "", "phase": "commentary"}}, seq=0)
        self.assertIsNone(e)

    def test_token_usage_both_runtimes_identical(self):
        # R7: codex and claude usage notifications normalize to the SAME record.
        cod = te.normalize_event(*_CODEX_USAGE, seq=0, now=lambda: "T")
        cla = te.normalize_event(*_CLAUDE_USAGE, seq=0, now=lambda: "T")
        self.assertEqual(cod, {"seq": 0, "ts": "T", "kind": "token_usage",
                               "tokens": {"input": 60, "output": 40, "total": 100}})
        self.assertEqual(cod, cla)

    def test_tool_call_both_runtimes(self):
        cla = te.normalize_event(*_CLAUDE_TOOL, seq=0, now=lambda: "T")
        self.assertEqual(cla["kind"], "tool_call")
        self.assertEqual(cla["tool"], "Bash")
        self.assertIn("ls", cla["summary"])               # from arguments, not full output
        cod = te.normalize_event(*_CODEX_TOOL, seq=0, now=lambda: "T")
        self.assertEqual(cod["kind"], "tool_call")
        self.assertEqual(cod["tool"], "commandExecution")
        self.assertIn("echo", cod["summary"])

    def test_unknown_item_falls_back_to_generic(self):
        e = te.normalize_event("item/completed", {"item": {"type": "mysteryThing", "summary": "x"}}, seq=0)
        self.assertEqual(e["kind"], "item")
        self.assertEqual(e["item_type"], "mysteryThing")

    def test_drops_deltas_placeholders_and_noise(self):
        for m, p in (("item/agentMessage/delta", {"delta": "x"}),
                     ("item/started", {"item": {"type": "agentMessage", "text": ""}}),
                     ("some/unknown/method", {}),
                     ("item/completed", {})):           # no item
            self.assertIsNone(te.normalize_event(m, p, seq=0))

    def test_tool_summary_clipped_never_full_output(self):
        big = {"item": {"type": "dynamicToolCall", "tool": "X", "contentItems": [{"type": "t", "text": "z" * 5000}]}}
        e = te.normalize_event("item/completed", big, seq=0)
        self.assertLessEqual(len(e["summary"]), te.SUMMARY_CLIP)

    def test_non_dict_params_and_method_tolerated(self):
        self.assertIsNone(te.normalize_event(None, {}, seq=0))
        self.assertIsNone(te.normalize_event("item/completed", None, seq=0))


class SanitizeIdTest(unittest.TestCase):
    def test_accepts_safe_ids(self):
        for ok in ("LIN-28", "u1", "a.b_c-9", "ABC"):
            self.assertEqual(te.sanitize_id(ok), ok)

    def test_rejects_traversal_and_empty(self):
        for bad in ("", ".", "..", "a/b", "../etc", "a\\b", "a b", "a:b", None, "a/../b"):
            self.assertIsNone(te.sanitize_id(bad), bad)


class WriterReadTest(unittest.TestCase):
    def _writer(self, **kw):
        d = tempfile.mkdtemp(prefix="te_")
        return te.TicketEventWriter(d, now=lambda: "T", **kw), d

    def test_round_trip_in_order_with_monotonic_seq(self):
        w, d = self._writer()
        w.record("LIN-1", *_AGENT_MSG)
        w.record("LIN-1", *_CLAUDE_TOOL)
        w.record("LIN-1", *_CODEX_USAGE)
        evs = te.read_events("LIN-1", base=d)
        self.assertEqual([e["kind"] for e in evs], ["agent_message", "tool_call", "token_usage"])
        self.assertEqual([e["seq"] for e in evs], [0, 1, 2])

    def test_dropped_event_consumes_no_seq(self):
        w, d = self._writer()
        w.record("t", *_AGENT_MSG)                    # seq 0
        w.record("t", "item/agentMessage/delta", {})  # dropped — no seq
        w.record("t", *_FINAL_MSG)                    # seq 1, not 2
        self.assertEqual([e["seq"] for e in te.read_events("t", base=d)], [0, 1])

    def test_seq_seeded_from_existing_file_across_restart(self):
        w, d = self._writer()
        w.record("t", *_AGENT_MSG)                    # seq 0
        w2 = te.TicketEventWriter(d, now=lambda: "T")  # fresh process: counter reset, file persists
        w2.record("t", *_FINAL_MSG)
        self.assertEqual([e["seq"] for e in te.read_events("t", base=d)], [0, 1])

    def test_torn_final_line_tolerated_on_read(self):
        w, d = self._writer()
        w.record("t", *_AGENT_MSG)
        with open(Path(d) / "t.jsonl", "a", encoding="utf-8") as f:
            f.write('{"seq": 1, "kind": "agent_mess')   # crash mid-append
        evs = te.read_events("t", base=d)
        self.assertEqual(len(evs), 1)                  # torn line skipped, prior survives

    def test_soft_cap_writes_one_sentinel_then_stops(self):
        w, d = self._writer(soft_cap=2)
        for _ in range(5):
            w.record("t", *_AGENT_MSG)
        kinds = [e["kind"] for e in te.read_events("t", base=d)]
        self.assertEqual(kinds.count("truncated"), 1)
        self.assertEqual(kinds, ["agent_message", "agent_message", "truncated"])

    def test_bad_id_is_noop(self):
        w, d = self._writer()
        w.record("../etc", *_AGENT_MSG)
        self.assertEqual(te.read_events("../etc", base=d), [])

    def test_write_failure_swallowed_not_raised(self):
        # point the writer at a path whose parent is a FILE → mkdir/open fails; record must not raise.
        f = tempfile.NamedTemporaryFile(prefix="te_file_", delete=False)
        w = te.TicketEventWriter(Path(f.name) / "sub", now=lambda: "T")
        w.record("t", *_AGENT_MSG)
        self.assertIsNotNone(w.last_error)

    def test_noop_writer_writes_nothing(self):
        d = tempfile.mkdtemp(prefix="te_noop_")
        n = te.NoopTicketEventWriter()
        n.record("t", *_AGENT_MSG)
        self.assertEqual(te.read_events("t", base=d), [])
        self.assertIsNone(n.last_error)

    def test_read_missing_and_bounded(self):
        w, d = self._writer()
        self.assertEqual(te.read_events("absent", base=d), [])
        for _ in range(10):
            w.record("t", *_AGENT_MSG)
        self.assertEqual(len(te.read_events("t", base=d, limit=3)), 3)


class DeriveTimeseriesTest(unittest.TestCase):
    def test_cumulative_tokens_tool_and_turn_counts(self):
        events = [
            {"kind": "turn_started", "seq": 0, "ts": "T0", "turn_id": "u1"},
            {"kind": "tool_call", "seq": 1, "ts": "T1", "tool": "Bash"},
            {"kind": "token_usage", "seq": 2, "ts": "T2", "tokens": {"input": 10, "output": 5, "total": 15}},
            {"kind": "tool_call", "seq": 3, "ts": "T3", "tool": "Bash"},
            {"kind": "token_usage", "seq": 4, "ts": "T4", "tokens": {"input": 30, "output": 12, "total": 42}},
            {"kind": "turn_ended", "seq": 5, "ts": "T5", "status": "completed"},
        ]
        ts = te.derive_timeseries(events)
        self.assertEqual(ts["turns"], 1)
        self.assertEqual(ts["tool_calls"], 2)
        self.assertEqual(ts["tools"], {"Bash": 2})
        self.assertEqual(ts["tokens"], {"input": 30, "output": 12, "total": 42})  # latest cumulative
        self.assertEqual([p["total"] for p in ts["token_series"]], [15, 42])      # the timeseries

    def test_tolerates_empty_and_garbage(self):
        for bad in (None, [], "x", [1, "y", None]):
            ts = te.derive_timeseries(bad)
            self.assertEqual(ts["turns"], 0)
            self.assertEqual(ts["token_series"], [])


if __name__ == "__main__":
    unittest.main()
