import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.history as dh  # noqa: E402

_SNAP = {
    "run": {"started_at": "2026-06-19T00:00:00+00:00", "pass": 2, "stopped_reason": "drained",
            "codex_totals": {"input": 120, "output": 80, "total": 200, "seconds_running": 4.5},
            "rate_limits": None},
    "recent": [{"ticket_id": "u1", "status": "completed"},
               {"ticket_id": "u2", "status": "completed"},
               {"ticket_id": "u3", "status": "blocked"}],
    "in_flight": [], "stuck": [], "updated_at": "2026-06-19T00:01:00+00:00",
}


class SummarizeTest(unittest.TestCase):
    def test_maps_run_fields_and_counts_outcomes(self):
        rec = dh.summarize(_SNAP)
        self.assertEqual(rec["started_at"], "2026-06-19T00:00:00+00:00")
        self.assertEqual(rec["ended_at"], "2026-06-19T00:01:00+00:00")  # default = updated_at
        self.assertEqual(rec["stopped_reason"], "drained")
        self.assertEqual(rec["passes"], 2)
        self.assertEqual(rec["codex_totals"],
                         {"input": 120, "output": 80, "total": 200, "seconds_running": 4.5})
        self.assertEqual(rec["ticket_count"], 3)
        self.assertEqual(rec["outcomes"], {"completed": 2, "blocked": 1})

    def test_explicit_ended_at_overrides(self):
        rec = dh.summarize(_SNAP, ended_at="2026-06-19T09:09:09+00:00")
        self.assertEqual(rec["ended_at"], "2026-06-19T09:09:09+00:00")

    def test_tolerates_empty_or_none_snapshot(self):
        for snap in (None, {}, {"run": None, "recent": None}):
            rec = dh.summarize(snap)
            self.assertEqual(rec["ticket_count"], 0)
            self.assertEqual(rec["outcomes"], {})
            self.assertIsNone(rec["stopped_reason"])


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp()) / "history"

    def test_append_then_read_roundtrip(self):
        dh.append_run({"total": 1}, base=self.base)
        dh.append_run({"total": 2}, base=self.base)
        self.assertEqual([r["total"] for r in dh.read_history(base=self.base)], [1, 2])

    def test_read_limit_returns_last_n(self):
        for i in range(5):
            dh.append_run({"i": i}, base=self.base)
        self.assertEqual([r["i"] for r in dh.read_history(base=self.base, limit=2)], [3, 4])

    def test_read_missing_is_empty(self):
        self.assertEqual(dh.read_history(base=self.base), [])

    def test_read_skips_torn_final_line(self):
        dh.append_run({"ok": 1}, base=self.base)
        with open(self.base / "runs.jsonl", "a", encoding="utf-8") as f:
            f.write('{"partial": ')  # a torn line (crash mid-append) — must be skipped
        self.assertEqual(dh.read_history(base=self.base), [{"ok": 1}])

    def test_append_bad_base_is_best_effort_no_raise(self):
        # history is instrumentation, never a gate — an un-writable path is swallowed.
        dh.append_run({"x": 1}, base="/proc/nonexistent/cannot/write")  # must NOT raise

    def test_read_skips_torn_multibyte_tail_without_raising(self):
        # R12: append_run writes ensure_ascii=False, so a crash mid-append can leave a
        # partial multibyte sequence. The whole-file decode must NOT raise UnicodeDecodeError
        # (which is a ValueError, not OSError) and discard every prior run — the valid lines
        # survive and the torn tail is skipped like any malformed line.
        dh.append_run({"ok": 1}, base=self.base)
        with open(self.base / "runs.jsonl", "ab") as f:
            f.write(b'{"partial": "\xe2\x82')  # torn UTF-8: first 2 bytes of a 3-byte char
        self.assertEqual(dh.read_history(base=self.base), [{"ok": 1}])  # valid run kept, no raise


if __name__ == "__main__":
    unittest.main()
