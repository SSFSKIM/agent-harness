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
        cases = [{"kind": "terminal", "outcome": {"status": "done"}},
                 {"kind": "reply", "reply": "do A"},
                 {"kind": "escalate", "reason": "taste"}]
        for disp_in in cases:
            disp = decider.disposition_from_answer({"disposition": disp_in})
            self.assertEqual(disp["kind"], disp_in["kind"])

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
        dmin.answer_turn("T-1|turn|0|a1", {"kind": "reply", "reply": "do A"}, base=base)
        th.join(timeout=5)

        self.assertEqual(out["disp"], {"kind": "reply", "reply": "do A"})
        req = dq.read_requests(base=base)[0]
        self.assertEqual(req["kind"], "turnReview")
        self.assertEqual(req["payload"]["final_message"], "could be A or B")
        self.assertEqual(req["ticket_id"], "T-1")
        self.assertEqual(req["request_id"], "T-1|turn|0|a1")  # carries the attempt

    def test_timeout_escalates(self):
        decide = decider.make_queue_decider(base=self.tmp / "q2", timeout_s=0.1)
        disp = decide({"ticket": {"id": "T-2"}, "turn_index": 0})
        self.assertEqual(disp["kind"], "escalate")

    def test_empty_reply_disposition_escalates(self):
        self.assertEqual(
            decider.disposition_from_answer(
                {"disposition": {"kind": "reply", "reply": "   "}})["kind"],
            "escalate")

    def test_retry_does_not_collide_with_prior_attempt_answer(self):
        # The attempt discriminant keeps a retried ticket's turn-0 review distinct from
        # attempt 1's queue entry — else append_request dedupe would feed back the stale
        # attempt-1 answer (review fix). Attempt 1's turn-0 answer must NOT satisfy
        # attempt 2's turn-0 review.
        base = self.tmp / "qr"
        decide = decider.make_queue_decider(base=base, timeout_s=0.3)
        # attempt 1, turn 0: answer it terminal
        ctx1 = {"ticket": {"id": "RT"}, "turn_index": 0, "attempt": 1}
        out1 = {}
        t1 = threading.Thread(target=lambda: out1.update(d=decide(ctx1)))
        t1.start()
        for _ in range(200):
            if dq.read_requests(base=base):
                break
            time.sleep(0.01)
        dmin.answer_turn("RT|turn|0|a1", {"kind": "reply", "reply": "attempt-1 answer"},
                         base=base)
        t1.join(timeout=5)
        self.assertEqual(out1["d"]["reply"], "attempt-1 answer")
        # attempt 2, turn 0: must NOT reuse attempt 1's answer → it posts a fresh request
        # (distinct rid) and, unanswered, times out to escalate.
        disp2 = decide({"ticket": {"id": "RT"}, "turn_index": 0, "attempt": 2})
        self.assertEqual(disp2["kind"], "escalate")
        rids = {r["request_id"] for r in dq.read_requests(base=base)}
        self.assertEqual(rids, {"RT|turn|0|a1", "RT|turn|0|a2"})  # distinct, not deduped

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


class BackfillPrFieldsTest(unittest.TestCase):
    """Merge-gate-bypass fix (LIN-27 dogfood): the watched decider backfills the worker's
    authoritative pr_url/pr_branch (+evidence) into a terminal-done disposition the Director
    omitted, so a PR-bearing done can never silently skip the merge gate."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_backfills_when_director_omits_pr_fields(self):
        disp = {"kind": "terminal", "outcome": {"status": "done", "reason": "shipped"}}
        worker = {"status": "done", "pr_url": "http://x/pull/1", "pr_branch": "feat",
                  "evidence": {"unresolved_threads": 0}}
        out = decider._backfill_pr_fields(disp, worker)
        self.assertEqual(out["outcome"]["pr_url"], "http://x/pull/1")
        self.assertEqual(out["outcome"]["pr_branch"], "feat")
        self.assertEqual(out["outcome"]["evidence"], {"unresolved_threads": 0})
        self.assertEqual(out["outcome"]["reason"], "shipped")  # director's fields preserved

    def test_director_pr_value_wins_when_present(self):
        disp = {"kind": "terminal",
                "outcome": {"status": "done", "pr_url": "http://dir/pull/9"}}
        worker = {"status": "done", "pr_url": "http://worker/pull/1", "pr_branch": "wb"}
        out = decider._backfill_pr_fields(disp, worker)
        self.assertEqual(out["outcome"]["pr_url"], "http://dir/pull/9")  # not overwritten
        self.assertEqual(out["outcome"]["pr_branch"], "wb")              # absent → backfilled

    def test_pass_through_non_terminal_blocked_and_no_worker(self):
        worker = {"status": "done", "pr_url": "http://x/1", "pr_branch": "b"}
        reply = {"kind": "reply", "reply": "go"}
        self.assertIs(decider._backfill_pr_fields(reply, worker), reply)
        blocked = {"kind": "terminal", "outcome": {"status": "blocked", "reason": "x"}}
        self.assertIs(decider._backfill_pr_fields(blocked, worker), blocked)
        done = {"kind": "terminal", "outcome": {"status": "done"}}
        self.assertIs(decider._backfill_pr_fields(done, None), done)  # no worker outcome

    def test_queue_decider_backfills_worker_pr_end_to_end(self):
        # The dogfood scenario: Director confirms terminal done WITHOUT echoing the PR;
        # the worker's report_outcome (ctx) carried it → the returned disposition has it.
        base = self.tmp / "qpr"
        ctx = {"ticket": {"id": "T-PR", "workspace": "/ws"}, "turn_index": 0, "attempt": 1,
               "final_message": "done",
               "outcome": {"status": "done", "pr_url": "http://x/pull/7",
                           "pr_branch": "feat-7"}}
        decide = decider.make_queue_decider(base=base, timeout_s=5)
        out = {}
        th = threading.Thread(target=lambda: out.update(disp=decide(ctx)))
        th.start()
        for _ in range(200):
            if dq.read_requests(base=base):
                break
            time.sleep(0.01)
        dmin.answer_turn("T-PR|turn|0|a1",
                         {"kind": "terminal", "outcome": {"status": "done", "reason": "ok"}},
                         base=base)
        th.join(timeout=5)
        oc = out["disp"]["outcome"]
        self.assertEqual(oc["pr_url"], "http://x/pull/7")   # backfilled from worker
        self.assertEqual(oc["pr_branch"], "feat-7")
        self.assertEqual(oc["reason"], "ok")                # director's reason kept


if __name__ == "__main__":
    unittest.main()
