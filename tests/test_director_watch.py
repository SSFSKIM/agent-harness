import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from unittest import mock  # noqa: E402
import director.orchestrator as orch  # noqa: E402
import director.queue as dq  # noqa: E402
import director.status as ds  # noqa: E402
import director.watch as watch  # noqa: E402


class NewPendingTest(unittest.TestCase):
    def _reqs(self, *ids_kinds):
        return [{"request_id": rid, "kind": k} for rid, k in ids_kinds]

    def test_emits_each_id_once(self):
        seen: set = set()
        reqs = self._reqs(("a", "turnReview"), ("b", "turnReview"))
        first = watch.new_pending(reqs, seen)
        self.assertEqual([r["request_id"] for r in first], ["a", "b"])
        # same pending set next poll → nothing new (deduped)
        self.assertEqual(watch.new_pending(reqs, seen), [])
        # a newly-appearing request is emitted
        reqs2 = reqs + self._reqs(("c", "turnReview"))
        self.assertEqual([r["request_id"] for r in watch.new_pending(reqs2, seen)], ["c"])

    def test_kind_filter(self):
        seen: set = set()
        reqs = self._reqs(("a", "turnReview"), ("b", "commandApproval"))
        out = watch.new_pending(reqs, seen, kinds={"turnReview"})
        self.assertEqual([r["request_id"] for r in out], ["a"])
        self.assertIn("a", seen)
        self.assertNotIn("b", seen)  # filtered-out kind is not marked seen


class NewRunReportTest(unittest.TestCase):
    def _snap(self, started_at, reason, recent=None, stuck=None):
        return {"run": {"started_at": started_at, "pass": 1, "stopped_reason": reason},
                "recent": recent or [], "stuck": stuck or [], "in_flight": []}

    def test_emits_once_per_run_terminal(self):
        seen: set = set()
        snap = self._snap("t0", "drained",
                          recent=[{"status": "completed"}, {"status": "completed"},
                                  {"status": "failed"}], stuck=[])
        ev = watch.new_run_report(snap, seen)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["kind"], "runReport")
        self.assertEqual(ev["reason"], "drained")
        self.assertEqual(ev["summary"]["by_status"], {"completed": 2, "failed": 1})
        # same terminal next poll → nothing (deduped per run)
        self.assertIsNone(watch.new_run_report(snap, seen))
        # a NEW run (new started_at) re-emits
        self.assertIsNotNone(watch.new_run_report(self._snap("t1", "stuck"), seen))

    def test_no_emit_until_terminal(self):
        seen: set = set()
        self.assertIsNone(watch.new_run_report(self._snap("t0", None), seen))  # mid-run

    def test_tolerant_of_missing_or_empty_snapshot(self):
        seen: set = set()
        self.assertIsNone(watch.new_run_report(None, seen))
        self.assertIsNone(watch.new_run_report({}, seen))

    def test_kind_filter_excludes_run_report(self):
        seen: set = set()
        self.assertIsNone(watch.new_run_report(self._snap("t0", "drained"), seen,
                                               kinds={"turnReview"}))
        self.assertNotIn(("t0", "drained"), seen)  # filtered-out → not marked seen
        # included → emits + marked
        self.assertIsNotNone(watch.new_run_report(self._snap("t0", "drained"), seen,
                                                  kinds={"runReport"}))


class WatchMainTest(unittest.TestCase):
    def test_once_emits_pending_turn_reviews_as_json(self):
        tmp = Path(tempfile.mkdtemp()) / "q"
        dq.append_request({"request_id": "u1|turn|0|a1", "ticket_id": "u1",
                           "kind": "turnReview",
                           "payload": {"final_message": "A or B?", "turn_index": 0}}, base=tmp)
        dq.append_request({"request_id": "u1|cmd", "ticket_id": "u1",
                           "kind": "commandApproval", "payload": {}}, base=tmp)
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            watch.main(["--once", "--queue-dir", str(tmp), "--kinds", "turnReview"])
        finally:
            sys.stdout = old
        lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1)  # only the turnReview, not the approval
        ev = json.loads(lines[0])
        self.assertEqual(ev["request_id"], "u1|turn|0|a1")
        self.assertEqual(ev["kind"], "turnReview")
        self.assertEqual(ev["payload"]["final_message"], "A or B?")

    def test_once_emits_run_report_from_status_snapshot(self):
        # M1: watch tails a real StatusWriter snapshot and emits a runReport at the terminal.
        sdir = Path(tempfile.mkdtemp()) / "s"
        w = ds.StatusWriter(base=sdir)
        w.claimed({"id": "u1", "identifier": "U-1"}, wave=1, attempt=1)
        w.terminal({"id": "u1"}, {"ticket": "U-1", "status": "completed",
                                  "final_state": "done"})
        w.finished("drained")
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            watch.main(["--once", "--queue-dir", str(Path(tempfile.mkdtemp()) / "q"),
                        "--status-dir", str(sdir), "--kinds", "runReport"])
        finally:
            sys.stdout = old
        lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1)
        ev = json.loads(lines[0])
        self.assertEqual(ev["kind"], "runReport")
        self.assertEqual(ev["reason"], "drained")
        self.assertEqual(ev["run"]["stopped_reason"], "drained")
        self.assertEqual(ev["summary"]["by_status"], {"completed": 1})


class OrchestratorToWatchIntegrationTest(unittest.TestCase):
    def test_run_terminal_emits_runreport(self):
        # M2: a real orchestrator run (finished() → status.json) makes watch emit a
        # runReport whose reason matches the run's stopped_reason — the whole signal path.
        sdir = Path(tempfile.mkdtemp()) / "s"
        board = orch.MockBoard.demo()
        states = orch.resolve_states(board, "T")

        def fake_dispatch(ticket, **kw):
            return {"kind": "terminal", "outcome": {"status": "done", "reason": "ok"},
                    "turns": 1, "turn_id": "t"}

        with mock.patch("director.orchestrator.dispatch", fake_dispatch):
            result = orch.run_until_drained(board, ["x"], team="T", states=states,
                                            status=ds.StatusWriter(base=sdir))
        self.assertEqual(result["stopped_reason"], "drained")

        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            watch.main(["--once", "--queue-dir", str(Path(tempfile.mkdtemp()) / "q"),
                        "--status-dir", str(sdir), "--kinds", "runReport"])
        finally:
            sys.stdout = old
        lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1)
        ev = json.loads(lines[0])
        self.assertEqual(ev["kind"], "runReport")
        self.assertEqual(ev["reason"], "drained")


if __name__ == "__main__":
    unittest.main()
