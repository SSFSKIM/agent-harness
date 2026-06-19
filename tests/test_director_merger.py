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
import director.orchestrator as orch  # noqa: E402
import director.run as run  # noqa: E402
from director.decider import autonomous_decide  # noqa: E402

MOCK = str(Path(run.__file__).resolve().parent / "worker" / "_mock_app_server.py")

_DONE = {"kind": "terminal", "outcome": {"status": "done", "reason": "merged"}}


# merge-preservation M4: a land-lane `done` now means PREPARED, and the code gate (finalize)
# decides merged/escalated/deferred. Drain-MECHANICS tests stub the gate to "merged" so they
# keep exercising FIFO/serialization/consume; the gate's own behavior is tested separately.
def _merged_finalize(req, **kw):
    return {"result": "merged"}


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

    def test_attempt_discriminates_merge_request_ids(self):
        # The re-enqueue discriminant: same ticket, different attempt → distinct requests
        # (a guided retry is NOT swallowed by the one-open-per-ticket dedupe).
        self.assertTrue(dq.append_merge_request("T1", pr="p", attempt=1, base=self.base))
        self.assertTrue(dq.append_merge_request("T1", pr="p", attempt=2,
                                                guidance="rebase", base=self.base))
        pend = merger.pending_merges(base=self.base)
        self.assertEqual(len(pend), 2)
        self.assertEqual({p["payload"]["attempt"] for p in pend}, {1, 2})
        # …but a re-delivery of the SAME attempt still dedupes.
        self.assertFalse(dq.append_merge_request("T1", pr="p", attempt=2, base=self.base))

    def test_land_prompt_includes_director_guidance_on_retry(self):
        p1 = merger.land_prompt({"pr": "x", "branch": "b", "attempt": 1})
        self.assertNotIn("DIRECTOR GUIDANCE", p1)
        p2 = merger.land_prompt({"pr": "x", "branch": "b", "attempt": 2,
                                 "guidance": "rebase onto origin/main and re-run gate"})
        self.assertIn("DIRECTOR GUIDANCE", p2)
        self.assertIn("rebase onto origin/main", p2)

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

        results = merger.drain(base=self.base, driver=driver, finalize=_merged_finalize)
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

    def test_surface_failure_leaves_request_pending(self):
        # Review fix: surface BEFORE consume. If posting the mergeReview fails, the
        # mergeRequest must stay pending (re-surfaced next pass), never silently consumed.
        dq.append_merge_request("T1", base=self.base)

        def driver(ticket, *, decide, **kw):
            return {"kind": "escalate", "reason": "conflict", "turns": 1}

        orig = dq.append_merge_review
        dq.append_merge_review = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("io"))
        try:
            with self.assertRaises(RuntimeError):
                merger.drain(base=self.base, driver=driver)
        finally:
            dq.append_merge_review = orig
        self.assertEqual(len(merger.pending_merges(base=self.base)), 1)  # not consumed

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
                merger.drain(base=self.base, driver=lambda *a, **k: _DONE,
                             finalize=_merged_finalize)
        finally:
            os.close(held)  # release
        # lock free again → drain proceeds normally
        results = merger.drain(base=self.base, driver=lambda *a, **k: _DONE,
                               finalize=_merged_finalize)
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
            finalize=_merged_finalize,
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

    def test_escalation_review_carries_and_discriminates_by_attempt(self):
        dq.append_merge_request("T1", pr=7, attempt=2, guidance="g", base=self.base)

        def driver(ticket, *, decide, **kw):
            return {"kind": "escalate", "reason": "conflict", "turns": 1}

        merger.drain(base=self.base, driver=driver)
        rv = dmin.merge_reviews(base=self.base)[0]
        self.assertEqual(rv["payload"]["attempt"], 2)            # carried for requeue
        self.assertTrue(rv["request_id"].endswith("|a2"))        # distinct per attempt

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

        # stub the gate to merged — this asserts a MERGED result does not surface (the gate's
        # own escalate/defer behavior is covered by FinalizeGateTest/GateIntegrationTest).
        results = merger.drain(base=self.base, driver=driver, finalize=_merged_finalize)
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

    def test_select_decider_watched_by_default_autonomous_when_flagged(self):
        # R9/D-50: a watched merger routes land-lane turn-ends to the Director; only
        # --autonomous / --mock use the code decider (no live Director to answer).
        self.assertIs(merger.select_decider(autonomous=True, mock=False), autonomous_decide)
        self.assertIs(merger.select_decider(autonomous=False, mock=True), autonomous_decide)
        watched = merger.select_decider(autonomous=False, mock=False, queue_base=self.base)
        self.assertIsNot(watched, autonomous_decide)   # the queue (Director) decider
        self.assertTrue(callable(watched))

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


class ReenqueueLoopTest(unittest.TestCase):
    """M2 (merge-reenqueue-loop): the Director requeues an escalated PR with guidance."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.base = self.tmp / "q"

    def _escalate(self, attempt=1):
        dq.append_merge_request("T1", pr=7, branch="feat/x", workspace_path="/ws",
                                attempt=attempt, base=self.base)

        def driver(ticket, *, decide, **kw):
            return {"kind": "escalate", "reason": "conflict", "turns": 1}

        merger.drain(base=self.base, driver=driver)
        return dmin.merge_reviews(base=self.base)[0]

    def test_requeue_reenqueues_attempt2_with_guidance(self):
        review = self._escalate(attempt=1)
        res = dmin.requeue_merge(review, note="rebase onto origin/main", base=self.base)
        self.assertTrue(res["requeued"])
        self.assertEqual(res["attempt"], 2)
        self.assertEqual(dmin.merge_reviews(base=self.base), [])  # review handled
        pend = merger.pending_merges(base=self.base)
        self.assertEqual(len(pend), 1)
        self.assertEqual(pend[0]["payload"]["attempt"], 2)
        self.assertEqual(pend[0]["payload"]["guidance"], "rebase onto origin/main")
        self.assertEqual(pend[0]["payload"]["pr"], 7)          # carried from the review
        self.assertEqual(pend[0]["payload"]["branch"], "feat/x")
        self.assertEqual(pend[0]["workspace_path"], "/ws")

    def test_requeue_refuses_beyond_max_attempts_and_leaves_review_open(self):
        review = self._escalate(attempt=3)  # next would be 4 > max 3
        res = dmin.requeue_merge(review, note="x", base=self.base, max_attempts=3)
        self.assertFalse(res["requeued"])
        self.assertEqual(res["reason"], "max_attempts")
        self.assertEqual(len(dmin.merge_reviews(base=self.base)), 1)   # still open → abandon/human
        self.assertEqual(merger.pending_merges(base=self.base), [])    # nothing re-queued

    def test_requeue_enqueue_failure_leaves_review_open(self):
        # Review fix (P1): enqueue BEFORE answering. If the re-enqueue raises, the review
        # must stay open (retryable), never consumed-without-a-retry.
        review = self._escalate(attempt=1)
        orig = dq.append_merge_request
        dq.append_merge_request = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("io"))
        try:
            with self.assertRaises(RuntimeError):
                dmin.requeue_merge(review, note="x", base=self.base)
        finally:
            dq.append_merge_request = orig
        self.assertEqual(len(dmin.merge_reviews(base=self.base)), 1)  # review NOT consumed

    def test_requeue_is_idempotent_on_double_call(self):
        # Review fix (P2): a 2nd requeue with a different note is a no-op — the already-
        # queued retry's guidance stands (audit can't diverge from what was queued).
        review = self._escalate(attempt=1)
        r1 = dmin.requeue_merge(review, note="first directive", base=self.base)
        self.assertTrue(r1["requeued"])
        r2 = dmin.requeue_merge(review, note="second directive", base=self.base)
        self.assertFalse(r2["requeued"])
        self.assertEqual(r2["reason"], "already_queued")
        pend = merger.pending_merges(base=self.base)
        self.assertEqual(len(pend), 1)
        self.assertEqual(pend[0]["payload"]["guidance"], "first directive")  # not overwritten

    def test_full_guided_retry_loop_converges(self):
        # M3: the whole loop — attempt 1 escalates; the Director requeues with guidance;
        # attempt 2 (guidance now in the land prompt) merges. The driver merges ONLY when
        # the directive is present, so a green result proves the guidance actually drove it.
        dq.append_merge_request("T1", pr=7, branch="feat/x", workspace_path="/ws",
                                base=self.base)

        def driver(ticket, *, decide, **kw):
            if "DIRECTOR GUIDANCE" in ticket["prompt"]:
                return {"kind": "terminal",
                        "outcome": {"status": "done", "reason": "landed with guidance"},
                        "turns": 1}
            return {"kind": "escalate", "reason": "conflict", "turns": 1}

        # round 1 escalates on the land-lane disposition (no gate reached); round 2's done
        # reaches the gate, stubbed to merged — the loop converges via the guidance.
        r1 = merger.drain(base=self.base, driver=driver, finalize=_merged_finalize)  # → escalate
        self.assertEqual(r1[0]["result"], "escalated")
        review = dmin.merge_reviews(base=self.base)[0]
        dmin.requeue_merge(review, note="rebase onto origin/main, then merge", base=self.base)
        r2 = merger.drain(base=self.base, driver=driver, finalize=_merged_finalize)  # → merged
        self.assertEqual(r2[0]["result"], "merged")
        self.assertEqual(merger.pending_merges(base=self.base), [])   # converged, queue empty
        self.assertEqual(dmin.merge_reviews(base=self.base), [])      # no open escalation


class EndToEndPipelineTest(unittest.TestCase):
    """M3 (activate-serialized-merge-pipeline): R4 end-to-end with mocks — a done worker
    that opened a PR flows through reconcile (enqueue) → the standalone merger (land) →
    merged. Fails before M1 (reconcile wouldn't enqueue) and M2 (no merger.main)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.base = self.tmp / "q"

    def test_done_with_pr_flows_reconcile_to_merged(self):
        board = orch.MockBoard([{"id": "u1", "identifier": "D-1", "title": "t",
                                 "description": "d", "prompt": "p", "state_id": "st_todo"}])
        states = orch.resolve_states(board, "T")
        disp = {"kind": "terminal",
                "outcome": {"status": "done", "reason": "ok",
                            "pr_url": "http://pr/7", "pr_branch": "feat/x"},
                "turns": 1, "turn_id": "t"}
        # 1) orchestrator EXECUTES the enqueue from the worker's proposed PR (D-40).
        out = orch.reconcile(board, {"id": "u1", "workspace": str(self.tmp / "ws")},
                             disp, 1, states, 1, queue_base=self.base)
        self.assertTrue(out["summary"]["merge_enqueued"])
        self.assertEqual(len(merger.pending_merges(base=self.base)), 1)
        # 2) the standalone merger drains it (mock land worker → prepared done → code gate).
        #    With no live gh the gate withholds (escalates), but the request is CONSUMED
        #    either way — this proves the reconcile→enqueue→merger-drain flow end-to-end;
        #    the gate's merged/escalated verdict is covered by GateIntegrationTest.
        rc = merger.main(["--once", "--mock", "--mock-scenario", "report",
                          "--queue-dir", str(self.base)])
        self.assertEqual(rc, 0)
        # 3) end-to-end: the merge request was drained/consumed → no mergeRequest left queued.
        self.assertEqual(merger.pending_merges(base=self.base), [])


class MergeOutcomeTest(unittest.TestCase):
    """merge-gated-eligibility R3: merge_outcome reads a ticket's merge standing from the
    queue (the signal the orchestrator's merge sweep uses to finalize merging→done — the
    merger never writes the board)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.base = self.tmp / "q"

    def _answer(self, ticket_id, attempt, result):
        # mirror merger._consume: writing an answer for a request removes it from pending.
        dq.write_answer({"request_id": f"merge|{ticket_id}|a{attempt}", "answered_by": "merger",
                         "merge_result": result}, base=self.base)

    def test_no_record_is_unresolved(self):
        self.assertEqual(merger.merge_outcome("T1", base=self.base), "unresolved")

    def test_pending_request_is_pending(self):
        dq.append_merge_request("T1", pr="p", attempt=1, base=self.base)
        self.assertEqual(merger.merge_outcome("T1", base=self.base), "pending")

    def test_consumed_merged_is_landed(self):
        dq.append_merge_request("T1", pr="p", attempt=1, base=self.base)
        self._answer("T1", 1, "merged")               # merger landed + consumed
        self.assertEqual(merger.merge_outcome("T1", base=self.base), "landed")

    def test_consumed_escalated_is_unresolved(self):
        dq.append_merge_request("T1", pr="p", attempt=1, base=self.base)
        self._answer("T1", 1, "escalated")            # land lane gave up → abandon/human
        self.assertEqual(merger.merge_outcome("T1", base=self.base), "unresolved")

    def test_latest_attempt_wins_requeue_then_land(self):
        # a1 escalated → Director requeued → a2 landed: the highest-attempt answer is authoritative.
        dq.append_merge_request("T1", pr="p", attempt=1, base=self.base)
        self._answer("T1", 1, "escalated")
        dq.append_merge_request("T1", pr="p", attempt=2, guidance="rebase", base=self.base)
        self._answer("T1", 2, "merged")
        self.assertEqual(merger.merge_outcome("T1", base=self.base), "landed")

    def test_pending_retry_outranks_a_prior_escalation(self):
        # a1 escalated, a2 still in flight → pending (not yet landed, don't unblock children).
        dq.append_merge_request("T1", pr="p", attempt=1, base=self.base)
        self._answer("T1", 1, "escalated")
        dq.append_merge_request("T1", pr="p", attempt=2, base=self.base)
        self.assertEqual(merger.merge_outcome("T1", base=self.base), "pending")


# ── merge-preservation-hardening M4: code owns the merge ─────────────────────────────

import json as _json  # noqa: E402


class _Proc:
    def __init__(self, rc, out=""):
        self.returncode = rc
        self.stdout = out


def _files_json(d):
    return _json.dumps({"files": [{"path": p, "additions": a, "deletions": dl}
                                  for p, (a, dl) in (d or {}).items()]})


def _gate_sh(*, intended_files=None, actual_files=None, rollup=None,
             threads_resolved=True, merge_rc=0):
    """Fake subprocess.run for the merger's gh gate calls, dispatched by argv. The two
    `gh pr view --json files` calls return intended_files then actual_files (the
    pre-rebase vs post-rebase diff the preservation tripwire compares)."""
    if rollup is None:
        rollup = [{"state": "SUCCESS"}]
    files_seq = [intended_files if intended_files is not None else {},
                 actual_files if actual_files is not None else intended_files or {}]
    state = {"files": 0}

    def run(argv, **kw):
        if "graphql" in argv:
            node = {"isResolved": threads_resolved}
            return _Proc(0, _json.dumps({"data": {"repository": {"pullRequest": {
                "reviewThreads": {"nodes": [node]}}}}}))
        if "merge" in argv:
            return _Proc(merge_rc)
        if "statusCheckRollup" in argv:
            return _Proc(0, _json.dumps({"statusCheckRollup": rollup}))
        if "files" in argv:
            d = files_seq[min(state["files"], len(files_seq) - 1)]
            state["files"] += 1
            return _Proc(0, _files_json(d))
        return _Proc(1)
    return run


def _merge_req(pr="https://github.com/o/r/pull/5", **payload):
    return {"request_id": "merge|T1|a1", "ticket_id": "T1",
            "workspace_path": "/ws", "payload": {"pr": pr, **payload}}


class FinalizeGateTest(unittest.TestCase):
    """The code gate (_finalize_merge): preservation tripwire → hygiene → code merge."""

    def _fin(self, *, intended, actual_files=None, **sh_kw):
        # _finalize_merge captures only the ACTUAL diff (intended is passed in), so the
        # single `gh pr view --json files` call must return actual_files — feed it as the
        # fake's first files response.
        return merger._finalize_merge(_merge_req(**sh_kw.pop("payload", {})),
                                      intended=intended, require_resolved_threads=True,
                                      run=_gate_sh(intended_files=actual_files, **sh_kw))

    def test_clean_pr_merges(self):
        fin = self._fin(intended={"a.py": (5, 0)}, actual_files={"a.py": (5, 0)})
        self.assertEqual(fin["result"], "merged")

    def test_dropped_path_escalates_and_names_it(self):
        fin = self._fin(intended={"a.py": (5, 0)}, actual_files={})   # a.py vanished
        self.assertEqual(fin["result"], "escalated")
        self.assertIn("preservation tripwire", fin["gate_reason"])
        self.assertIn("a.py", fin["gate_reason"])

    def test_red_check_escalates(self):
        fin = self._fin(intended={"a.py": (5, 0)}, actual_files={"a.py": (5, 0)},
                        rollup=[{"state": "FAILURE"}])
        self.assertEqual(fin["result"], "escalated")
        self.assertIn("hygiene", fin["gate_reason"])

    def test_pending_ci_defers(self):
        fin = self._fin(intended={"a.py": (5, 0)}, actual_files={"a.py": (5, 0)},
                        rollup=[{"status": "IN_PROGRESS"}])
        self.assertEqual(fin["result"], "deferred")

    def test_unresolved_thread_escalates(self):
        fin = self._fin(intended={"a.py": (5, 0)}, actual_files={"a.py": (5, 0)},
                        threads_resolved=False)
        self.assertEqual(fin["result"], "escalated")

    def test_override_skips_preservation(self):
        # actual drops a.py, but the Director approved (override) → tripwire skipped; the
        # hygiene gate still runs, and clean → merged.
        fin = merger._finalize_merge(
            _merge_req(preservation_override=True), intended={"a.py": (5, 0)},
            require_resolved_threads=True,
            run=_gate_sh(intended_files={"a.py": (5, 0)}, actual_files={}))
        self.assertEqual(fin["result"], "merged")

    def test_fail_closed_when_intended_unreadable(self):
        fin = merger._finalize_merge(_merge_req(), intended=None,
                                     require_resolved_threads=True, run=_gate_sh())
        self.assertEqual(fin["result"], "escalated")

    def test_fail_closed_when_merge_command_fails(self):
        fin = self._fin(intended={"a.py": (5, 0)}, actual_files={"a.py": (5, 0)}, merge_rc=1)
        self.assertEqual(fin["result"], "escalated")
        self.assertIn("gh pr merge failed", fin["gate_reason"])


class GateIntegrationTest(unittest.TestCase):
    """process_request/drain end-to-end with the real gate (fake gh) — the spine wiring."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.base = self.tmp / "q"

    def _reviews(self):
        return [r for r in dq.read_pending(base=self.base) if r["kind"] == "mergeReview"]

    def test_clean_pr_lands_via_code_merge(self):
        dq.append_merge_request("T1", pr="https://github.com/o/r/pull/5",
                                workspace_path="/ws", base=self.base)
        sh = _gate_sh(intended_files={"a.py": (5, 0)}, actual_files={"a.py": (5, 0)})
        results = merger.drain(base=self.base, driver=lambda *a, **k: _DONE, sh=sh)
        self.assertEqual(results[0]["result"], "merged")
        self.assertEqual(merger.pending_merges(base=self.base), [])

    def test_dropped_hunk_does_not_land_and_surfaces_review(self):
        dq.append_merge_request("T1", pr="https://github.com/o/r/pull/5",
                                workspace_path="/ws", base=self.base)
        sh = _gate_sh(intended_files={"a.py": (5, 0)}, actual_files={})  # rebase dropped a.py
        results = merger.drain(base=self.base, driver=lambda *a, **k: _DONE, sh=sh)
        self.assertEqual(results[0]["result"], "escalated")
        self.assertIn("a.py", results[0]["gate_reason"])
        self.assertEqual(len(self._reviews()), 1)            # surfaced to the Director
        self.assertEqual(merger.pending_merges(base=self.base), [])  # consumed (not retried)

    def test_pending_ci_defers_unsurfaced_and_stays_pending(self):
        dq.append_merge_request("T1", pr="https://github.com/o/r/pull/5",
                                workspace_path="/ws", base=self.base)
        sh = _gate_sh(intended_files={"a.py": (5, 0)}, actual_files={"a.py": (5, 0)},
                      rollup=[{"status": "IN_PROGRESS"}])
        results = merger.drain(base=self.base, driver=lambda *a, **k: _DONE, sh=sh)
        self.assertEqual(results[0]["result"], "deferred")
        self.assertEqual(len(merger.pending_merges(base=self.base)), 1)  # left for retry
        self.assertEqual(self._reviews(), [])                            # NOT surfaced

    def test_deferred_pr_does_not_block_others_no_head_of_line(self):
        # T1's CI is pending (defer), T2's is green (land) — T2 must still drain this pass.
        dq.append_merge_request("T1", pr="https://github.com/o/r/pull/1",
                                workspace_path="/ws", base=self.base)
        dq.append_merge_request("T2", pr="https://github.com/o/r/pull/2",
                                workspace_path="/ws", base=self.base)

        def sh(argv, **kw):
            pr1 = any("pull/1" in str(x) for x in argv)
            if "graphql" in argv:
                return _Proc(0, _json.dumps({"data": {"repository": {"pullRequest": {
                    "reviewThreads": {"nodes": []}}}}}))
            if "merge" in argv:
                return _Proc(0)
            if "statusCheckRollup" in argv:
                st = [{"status": "IN_PROGRESS"}] if pr1 else [{"state": "SUCCESS"}]
                return _Proc(0, _json.dumps({"statusCheckRollup": st}))
            if "files" in argv:
                return _Proc(0, _files_json({"a.py": (5, 0)}))
            return _Proc(1)

        results = merger.drain(base=self.base, driver=lambda *a, **k: _DONE, sh=sh)
        by = {r["ticket_id"]: r["result"] for r in results}
        self.assertEqual(by["T2"], "merged")        # not blocked behind the deferred T1
        self.assertEqual(by["T1"], "deferred")
        # only T1 remains pending (T2 consumed)
        pend = merger.pending_merges(base=self.base)
        self.assertEqual([p["ticket_id"] for p in pend], ["T1"])

    def test_protocol_misfire_logged_when_claim_contradicts_gate(self):
        import contextlib
        import io
        dq.append_merge_request("T1", pr="https://github.com/o/r/pull/5",
                                workspace_path="/ws",
                                evidence={"checks_state": "green", "unresolved_threads": 0},
                                base=self.base)
        sh = _gate_sh(intended_files={"a.py": (5, 0)}, actual_files={})  # gate withholds
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            merger.drain(base=self.base, driver=lambda *a, **k: _DONE, sh=sh)
        self.assertIn("protocol_misfire", buf.getvalue())

    def test_merger_module_has_no_board_import(self):
        # R6: the merger stays board-free — the queue is its only hand-off.
        src = Path(merger.__file__).read_text()
        self.assertNotIn("import director.board", src)
        self.assertNotIn("from director.board", src)
        self.assertNotIn("from director import board", src)


class LandSkillPreparesTest(unittest.TestCase):
    """R2: the land skill prepares (does not merge) and carries the preservation check."""

    def test_land_skill_no_longer_self_merges_and_checks_preservation(self):
        src = (Path(merger.__file__).resolve().parent / "workspace_skills" / "land"
               / "SKILL.md").read_text()
        low = src.lower()
        self.assertNotIn("gh pr merge --squash --subject", src)  # the self-merge command is gone
        self.assertIn("do not", low)                             # do NOT merge yourself
        self.assertIn("preservation", low)                       # R2 faithfulness check
        self.assertIn("the merger", low)                         # merger finalizes


if __name__ == "__main__":
    unittest.main()
