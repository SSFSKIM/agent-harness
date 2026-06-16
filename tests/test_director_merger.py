import fcntl
import inspect
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.queue as dq  # noqa: E402
import director.director_min as dmin  # noqa: E402
import director.merger as merger  # noqa: E402
import director.run as run  # noqa: E402
from director.decider import autonomous_decide  # noqa: E402

MOCK = str(Path(run.__file__).resolve().parent / "worker" / "_mock_app_server.py")

_DONE = {"kind": "terminal", "outcome": {"status": "done", "reason": "merged"}}


class MergeQueueTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.base = self.tmp / "q"

    def test_enqueue_is_idempotent_per_ticket(self):
        # One impl ticket → one PR → one merge request; re-enqueue dedupes (R1/R4).
        self.assertTrue(dq.append_merge_request("T1", pr=7, base=self.base))
        self.assertFalse(dq.append_merge_request("T1", pr=7, base=self.base))
        self.assertEqual(len(merger.pending_merges(base=self.base)), 1)

    def test_enqueue_payload_carries_pr_branch_and_self_description(self):
        dq.append_merge_request("T1", pr=7, branch="feat/x",
                                self_description="## What\nbuilt X", base=self.base)
        req = merger.pending_merges(base=self.base)[0]
        self.assertEqual(req["kind"], "mergeRequest")
        self.assertEqual(req["payload"]["pr"], 7)
        self.assertEqual(req["payload"]["branch"], "feat/x")
        self.assertIn("built X", merger.land_prompt(req["payload"]))

    def test_auto_respond_does_not_consume_merge_requests(self):
        # The fixed-policy approval responder must never answer (and thereby silently
        # consume) a merge request — only the serialized merger may drain it.
        dq.append_merge_request("T1", base=self.base)
        stop = threading.Event()
        th = threading.Thread(target=dmin.auto_respond,
                              kwargs={"base": self.base, "stop": stop})
        th.start()
        time.sleep(0.1)
        stop.set()
        th.join(timeout=2)
        self.assertEqual(len(merger.pending_merges(base=self.base)), 1)


class DrainSerializationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.base = self.tmp / "q"

    def test_drains_serially_in_fifo_order_one_at_a_time(self):
        for t in ("T1", "T2", "T3"):
            dq.append_merge_request(t, base=self.base)
        order = []
        state = {"inflight": 0, "max": 0}

        def driver(ticket, *, decide, **kw):
            state["inflight"] += 1
            state["max"] = max(state["max"], state["inflight"])
            order.append(ticket["id"])
            state["inflight"] -= 1
            return _DONE

        results = merger.drain(base=self.base, driver=driver)
        self.assertEqual([r["result"] for r in results], ["merged", "merged", "merged"])
        self.assertEqual(order, ["merge-T1", "merge-T2", "merge-T3"])  # FIFO
        self.assertEqual(state["max"], 1)                              # never >1 in flight
        self.assertEqual(merger.pending_merges(base=self.base), [])    # all consumed

    def test_conflict_escalates_and_is_consumed(self):
        # A disposition that is not a clean terminal(done) → escalated, surfaced to the
        # human (M3), and CONSUMED so the drain never re-processes it (no infinite loop).
        dq.append_merge_request("T1", base=self.base)

        def driver(ticket, *, decide, **kw):
            return {"kind": "escalate", "reason": "merge conflict in foo.py", "turns": 2}

        results = merger.drain(base=self.base, driver=driver)
        self.assertEqual(results[0]["result"], "escalated")
        self.assertEqual(results[0]["disposition"]["reason"], "merge conflict in foo.py")
        self.assertEqual(merger.pending_merges(base=self.base), [])

    def test_stuck_and_nondone_terminal_also_escalate(self):
        dq.append_merge_request("T1", base=self.base)
        dq.append_merge_request("T2", base=self.base)
        scripted = {"merge-T1": {"kind": "stuck", "reason": "max_turns"},
                    "merge-T2": {"kind": "terminal", "outcome": {"status": "blocked"}}}

        def driver(ticket, *, decide, **kw):
            return scripted[ticket["id"]]

        results = merger.drain(base=self.base, driver=driver)
        self.assertEqual([r["result"] for r in results], ["escalated", "escalated"])

    def test_driver_crash_is_failed_and_terminates(self):
        dq.append_merge_request("T1", base=self.base)

        def driver(ticket, *, decide, **kw):
            raise RuntimeError("boom")

        results = merger.drain(base=self.base, driver=driver)
        self.assertEqual(results[0]["result"], "failed")
        self.assertIn("boom", results[0]["error"])
        self.assertEqual(merger.pending_merges(base=self.base), [])  # consumed → no loop

    def test_concurrent_drain_is_refused(self):
        # R4 (completion-gate fix): a second drain while one holds the single-consumer
        # lock must fail loud, not race read-then-drive on the same PR.
        dq.append_merge_request("T1", base=self.base)
        root = dq._root(self.base)
        root.mkdir(parents=True, exist_ok=True)
        held = os.open(str(root / "merger.lock"), os.O_CREAT | os.O_WRONLY, 0o600)
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)  # simulate another live merger
        try:
            with self.assertRaises(RuntimeError):
                merger.drain(base=self.base, driver=lambda *a, **k: _DONE)
        finally:
            os.close(held)  # release
        # lock free again → drain proceeds normally
        results = merger.drain(base=self.base, driver=lambda *a, **k: _DONE)
        self.assertEqual(results[0]["result"], "merged")

    def test_max_merges_bounds_one_pass(self):
        for i in range(5):
            dq.append_merge_request(f"T{i}", base=self.base)
        calls = []

        def driver(ticket, *, decide, **kw):
            calls.append(ticket["id"])
            return _DONE

        results = merger.drain(base=self.base, driver=driver, max_merges=2)
        self.assertEqual(len(results), 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(merger.pending_merges(base=self.base)), 3)  # rest left queued


class DrainWithRealDriveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.base = self.tmp / "q"

    def test_drain_with_real_drive_and_mock_worker_merges(self):
        # End-to-end through run.drive + the mock app-server: the land lane's worker
        # calls report_outcome(done) → autonomous decider → terminal(done) → merged.
        dq.append_merge_request("T1", pr=7, branch="feat/x",
                                workspace_path=str(self.tmp / "ws"), base=self.base)
        results = merger.drain(
            base=self.base, driver=run.drive, decide=autonomous_decide,
            command=[sys.executable, MOCK, "report"],
            queue_base=str(self.tmp / "landq"), workspace_root=self.tmp / "wsr")
        self.assertEqual(results[0]["result"], "merged")
        self.assertEqual(results[0]["disposition"]["outcome"]["status"], "done")
        self.assertEqual(merger.pending_merges(base=self.base), [])


class MergeEscalationToDirectorTest(unittest.TestCase):
    """M3: a PR that can't cleanly land surfaces to the Director via a mergeReview on
    the SAME queue — the merger's only escalation channel (R6/R7)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.base = self.tmp / "q"

    def test_escalated_pr_surfaces_a_mergereview(self):
        dq.append_merge_request("T1", pr=7, branch="feat/x", base=self.base)

        def driver(ticket, *, decide, **kw):
            return {"kind": "escalate", "reason": "merge conflict in foo.py", "turns": 2}

        results = merger.drain(base=self.base, driver=driver)
        self.assertEqual(results[0]["result"], "escalated")
        self.assertTrue(results[0]["escalated_to_director"])
        reviews = dmin.merge_reviews(base=self.base)
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["kind"], "mergeReview")
        self.assertEqual(reviews[0]["ticket_id"], "T1")
        self.assertEqual(reviews[0]["payload"]["pr"], 7)
        self.assertEqual(reviews[0]["payload"]["result"], "escalated")
        self.assertIn("conflict", reviews[0]["payload"]["reason"])

    def test_failed_pr_also_surfaces_with_failed_result(self):
        dq.append_merge_request("T1", base=self.base)

        def driver(ticket, *, decide, **kw):
            raise RuntimeError("land lane crashed")

        merger.drain(base=self.base, driver=driver)
        reviews = dmin.merge_reviews(base=self.base)
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["payload"]["result"], "failed")
        self.assertIn("crashed", reviews[0]["payload"]["reason"])

    def test_merged_pr_does_not_surface(self):
        dq.append_merge_request("T1", base=self.base)

        def driver(ticket, *, decide, **kw):
            return _DONE

        results = merger.drain(base=self.base, driver=driver)
        self.assertFalse(results[0]["escalated_to_director"])
        self.assertEqual(dmin.merge_reviews(base=self.base), [])  # nothing to surface

    def test_merger_has_no_direct_human_path(self):
        # R7 (structural): the merger talks to the human only THROUGH the Director queue.
        # It takes no board/human handle, and an escalation's sole observable effect is
        # the mergeReview queue write (verified above) — there is no other output channel.
        params = set(inspect.signature(merger.drain).parameters)
        self.assertNotIn("board", params)
        self.assertNotIn("notify", params)
        # the escalation surface IS the queue helper — assert that linkage exists
        src = inspect.getsource(merger._surface_escalation)
        self.assertIn("append_merge_review", src)

    def test_director_answers_a_merge_review(self):
        dq.append_merge_request("T1", pr=7, base=self.base)

        def driver(ticket, *, decide, **kw):
            return {"kind": "escalate", "reason": "red integration gate", "turns": 1}

        merger.drain(base=self.base, driver=driver)
        review = dmin.merge_reviews(base=self.base)[0]
        dmin.answer_merge_review(review["request_id"],
                                 {"action": "abandon", "note": "spin a fix ticket"},
                                 base=self.base)
        self.assertEqual(dmin.merge_reviews(base=self.base), [])  # handled → out of inbox
        ans = dq.read_answer(review["request_id"], base=self.base)
        self.assertEqual(ans["merge_review_disposition"]["action"], "abandon")

    def test_auto_respond_does_not_consume_merge_reviews(self):
        dq.append_merge_request("T1", base=self.base)

        def driver(ticket, *, decide, **kw):
            return {"kind": "escalate", "reason": "conflict", "turns": 1}

        merger.drain(base=self.base, driver=driver)
        stop = threading.Event()
        th = threading.Thread(target=dmin.auto_respond,
                              kwargs={"base": self.base, "stop": stop})
        th.start()
        time.sleep(0.1)
        stop.set()
        th.join(timeout=2)
        # the fixed-policy responder must leave merge escalations for the live Director
        self.assertEqual(len(dmin.merge_reviews(base=self.base)), 1)


class MergerCliTest(unittest.TestCase):
    """M2 (activate-serialized-merge-pipeline): the standalone `python3 -m director.merger`
    process drains the queue (the drain-runner; separate component from the Director)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.base = self.tmp / "q"

    def test_main_once_drains_seeded_queue_via_mock_worker(self):
        # End-to-end through the real CLI + run.drive + mock land worker: a seeded PR is
        # landed (report scenario → terminal done → merged) and the queue drains.
        dq.append_merge_request("T1", pr="p", branch="b",
                                workspace_path=str(self.tmp / "ws"), base=self.base)
        rc = merger.main(["--once", "--mock", "--mock-scenario", "report",
                          "--queue-dir", str(self.base)])
        self.assertEqual(rc, 0)
        self.assertEqual(merger.pending_merges(base=self.base), [])  # drained + consumed

    def test_main_once_empty_queue_is_noop(self):
        rc = merger.main(["--once", "--mock", "--queue-dir", str(self.tmp / "empty")])
        self.assertEqual(rc, 0)

    def test_run_loop_once_drains_with_injected_driver(self):
        # run_loop(once=True) is the loop body: one drain pass then return 0.
        dq.append_merge_request("T1", base=self.base)
        dq.append_merge_request("T2", base=self.base)
        seen = []

        def driver(ticket, *, decide, **kw):
            seen.append(ticket["id"])
            return _DONE

        rc = merger.run_loop(base=self.base, command=["x"], once=True, driver=driver)
        self.assertEqual(rc, 0)
        self.assertEqual(seen, ["merge-T1", "merge-T2"])      # serial, FIFO
        self.assertEqual(merger.pending_merges(base=self.base), [])


if __name__ == "__main__":
    unittest.main()
