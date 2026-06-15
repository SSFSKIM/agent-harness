import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.decider as decider  # noqa: E402
import director.director_min as dmin  # noqa: E402
import director.queue as dq  # noqa: E402


class DispositionFromAnswerTest(unittest.TestCase):
    def test_valid_disposition_passes_through(self):
        for kind in ("terminal", "reply", "escalate"):
            disp = decider.disposition_from_answer({"disposition": {"kind": kind, "x": 1}})
            self.assertEqual(disp["kind"], kind)

    def test_none_answer_escalates(self):
        self.assertEqual(decider.disposition_from_answer(None)["kind"], "escalate")

    def test_malformed_answer_escalates(self):
        self.assertEqual(decider.disposition_from_answer({"foo": 1})["kind"], "escalate")
        self.assertEqual(
            decider.disposition_from_answer({"disposition": {"kind": "bogus"}})["kind"],
            "escalate")


class QueueDeciderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_posts_turn_review_and_returns_answered_disposition(self):
        base = self.tmp / "q"
        ctx = {"ticket": {"id": "T-1", "workspace": "/ws"}, "turn_index": 0,
               "final_message": "could be A or B", "outcome": None}
        decide = decider.make_queue_decider(base=base, timeout_s=5)
        out = {}
        th = threading.Thread(target=lambda: out.update(disp=decide(ctx)))
        th.start()
        # wait for the turn-review request, then answer it with a content-bearing reply
        for _ in range(200):
            if dq.read_requests(base=base):
                break
            time.sleep(0.01)
        dmin.answer_turn("T-1|turn|0", {"kind": "reply", "reply": "do A"}, base=base)
        th.join(timeout=5)

        self.assertEqual(out["disp"], {"kind": "reply", "reply": "do A"})
        req = dq.read_requests(base=base)[0]
        self.assertEqual(req["kind"], "turnReview")
        self.assertEqual(req["payload"]["final_message"], "could be A or B")
        self.assertEqual(req["ticket_id"], "T-1")

    def test_timeout_escalates(self):
        decide = decider.make_queue_decider(base=self.tmp / "q2", timeout_s=0.1)
        disp = decide({"ticket": {"id": "T-2"}, "turn_index": 0})
        self.assertEqual(disp["kind"], "escalate")

    def test_answer_turn_writes_disposition(self):
        base = self.tmp / "q3"
        dq.append_request({"request_id": "R|turn|0", "ticket_id": "R", "kind": "turnReview",
                           "payload": {}}, base=base)
        dmin.answer_turn("R|turn|0", {"kind": "terminal", "outcome": {"status": "done"}},
                         base=base)
        ans = dq.read_answer("R|turn|0", base=base)
        self.assertEqual(ans["disposition"]["kind"], "terminal")
        self.assertEqual(ans["answered_by"], "director")

    def test_auto_respond_skips_turn_reviews(self):
        # the fixed-policy approval responder must NOT answer a turnReview (needs a
        # free-form disposition, not a decision string).
        base = self.tmp / "q4"
        dq.append_request({"request_id": "X|turn|0", "ticket_id": "X", "kind": "turnReview",
                           "payload": {}}, base=base)
        stop = threading.Event()
        th = threading.Thread(target=dmin.auto_respond, kwargs={"base": base, "stop": stop})
        th.start()
        time.sleep(0.1)
        stop.set()
        th.join(timeout=5)
        self.assertIsNone(dq.read_answer("X|turn|0", base=base))  # left for the Director


if __name__ == "__main__":
    unittest.main()
