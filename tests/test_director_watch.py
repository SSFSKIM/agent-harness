import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.queue as dq  # noqa: E402
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


class WatchMainTest(unittest.TestCase):
    def test_once_emits_pending_turn_reviews_as_json(self):
        import json
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


if __name__ == "__main__":
    unittest.main()
