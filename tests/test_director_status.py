import io
import json
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.status as ds  # noqa: E402


def _ticket(tid="u1", ident="DEMO-1"):
    return {"id": tid, "identifier": ident, "title": "t"}


def _req(ticket_id="u1"):
    return {"request_id": "r1", "ticket_id": ticket_id, "kind": "commandApproval"}


class StatusWriterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.base = Path(self.tmp) / "director-status"

    def _snap(self) -> dict:
        snap = ds.read_status(base=self.base)
        assert snap is not None, "expected a snapshot to exist"
        return snap

    def test_claimed_then_dispatched_shows_in_flight(self):
        w = ds.StatusWriter(base=self.base)
        w.claimed(_ticket(), wave=1, attempt=1)
        w.dispatched(_ticket())
        snap = self._snap()
        self.assertEqual(len(snap["in_flight"]), 1)
        e = snap["in_flight"][0]
        self.assertEqual(e["ticket_id"], "u1")
        self.assertEqual(e["identifier"], "DEMO-1")
        self.assertEqual(e["phase"], "running")
        self.assertEqual(e["attempt"], 1)
        self.assertEqual(e["wave"], 1)
        self.assertIsNotNone(snap["run"]["started_at"])

    def test_retrying_bumps_attempt_and_phase(self):
        w = ds.StatusWriter(base=self.base)
        w.claimed(_ticket(), wave=1, attempt=1)
        w.retrying(_ticket(), attempt=2)
        e = self._snap()["in_flight"][0]
        self.assertEqual(e["attempt"], 2)
        self.assertEqual(e["phase"], "retrying")

    def test_terminal_moves_to_recent_and_clears_in_flight(self):
        w = ds.StatusWriter(base=self.base)
        w.claimed(_ticket(), wave=1, attempt=1)
        w.terminal(_ticket(), {"ticket": "DEMO-1", "status": "completed",
                               "final_state": "done", "attempts": 1})
        snap = self._snap()
        self.assertEqual(snap["in_flight"], [])
        self.assertEqual(len(snap["recent"]), 1)
        r = snap["recent"][0]
        self.assertEqual(r["ticket_id"], "u1")
        self.assertEqual(r["status"], "completed")
        self.assertEqual(r["final_state"], "done")

    def test_recent_is_bounded(self):
        w = ds.StatusWriter(base=self.base, recent_max=3)
        for i in range(5):
            t = _ticket(tid=f"u{i}", ident=f"DEMO-{i}")
            w.claimed(t, wave=1, attempt=1)
            w.terminal(t, {"ticket": f"DEMO-{i}", "status": "completed",
                           "final_state": "done", "attempts": 1})
        recent = self._snap()["recent"]
        self.assertEqual(len(recent), 3)
        self.assertEqual([r["ticket_id"] for r in recent], ["u2", "u3", "u4"])

    def _tel_summary(self, total, *, ident="DEMO-1", rate=None):
        return {"ticket": ident, "status": "completed", "final_state": "done",
                "attempts": 1, "turns": 2,
                "telemetry": {"tokens": {"input": total // 2, "output": total // 2,
                                         "total": total},
                              "turn_count": 2, "session_id": "thr-turn",
                              "last_message": "done", "rate_limits": rate}}

    def test_terminal_records_telemetry_and_aggregates(self):
        # M3: the recent[] row carries the ticket's tokens/session_id/last_message;
        # the run aggregate gains codex_totals (+ live seconds_running) and the latest
        # rate-limit payload.
        w = ds.StatusWriter(base=self.base)
        w.claimed(_ticket("u1", "DEMO-1"), wave=1, attempt=1)
        w.terminal(_ticket("u1", "DEMO-1"), self._tel_summary(200, rate={"remaining": 5}))
        snap = self._snap()
        r = snap["recent"][0]
        self.assertEqual(r["tokens"], {"input": 100, "output": 100, "total": 200})
        self.assertEqual(r["session_id"], "thr-turn")
        self.assertEqual(r["last_message"], "done")
        ct = snap["run"]["codex_totals"]
        self.assertEqual((ct["input"], ct["output"], ct["total"]), (100, 100, 200))
        self.assertGreaterEqual(ct["seconds_running"], 0.0)
        self.assertEqual(snap["run"]["rate_limits"], {"remaining": 5})

    def test_codex_totals_sum_across_tickets_no_double_count(self):
        # Each ticket contributes its absolute total ONCE → 100 + 200 = 300 (drive
        # already collapsed each thread's stream to its latest absolute, §13.5).
        w = ds.StatusWriter(base=self.base)
        for tid, tot in (("u1", 100), ("u2", 200)):
            t = _ticket(tid, f"D-{tid}")
            w.claimed(t, wave=1, attempt=1)
            w.terminal(t, self._tel_summary(tot, ident=tid))
        self.assertEqual(self._snap()["run"]["codex_totals"]["total"], 300)

    def test_partial_tokens_not_folded_into_aggregate(self):
        # review-reliability P2: a partial/garbage tokens payload must not leave
        # codex_totals internally inconsistent — the fold is all-or-nothing.
        w = ds.StatusWriter(base=self.base)
        w.claimed(_ticket("u1", "D-1"), wave=1, attempt=1)
        w.terminal(_ticket("u1", "D-1"),
                   {"ticket": "D-1", "status": "completed", "final_state": "done",
                    "attempts": 1, "turns": 1,
                    "telemetry": {"tokens": {"input": 5},  # missing output/total
                                  "turn_count": 1, "session_id": "s",
                                  "last_message": "m", "rate_limits": None}})
        ct = self._snap()["run"]["codex_totals"]
        self.assertEqual((ct["input"], ct["output"], ct["total"]), (0, 0, 0))

    def test_terminal_without_telemetry_is_backward_compatible(self):
        # A terminal with no telemetry (claim_failed / crash-path failed) → tokens
        # None, aggregate untouched, snapshot still valid (R6 / additive).
        w = ds.StatusWriter(base=self.base)
        w.claimed(_ticket("u1"), wave=1, attempt=1)
        w.terminal(_ticket("u1"), {"ticket": "DEMO-1", "status": "completed",
                                   "final_state": "done", "attempts": 1, "turns": 1})
        snap = self._snap()
        self.assertIsNone(snap["recent"][0]["tokens"])
        self.assertEqual(snap["run"]["codex_totals"]["total"], 0)
        self.assertIsNone(snap["run"]["rate_limits"])

    def test_flush_swallows_serialize_error_never_raises(self):
        # R3 contract: a status-write failure (here a non-serializable timestamp)
        # is recorded, never raised — visibility must never break dispatch.
        w = ds.StatusWriter(base=self.base, now=lambda: object())  # type: ignore[arg-type]
        w.claimed(_ticket(), wave=1, attempt=1)  # must not raise
        self.assertIsNotNone(w.last_error)
        self.assertIsNone(ds.read_status(base=self.base))  # nothing valid written

    def test_wave_stuck_finished(self):
        w = ds.StatusWriter(base=self.base)
        w.wave(2)
        w.stuck([{"ticket": "DEMO-9",
                  "blocked_by": [{"id": "u8", "state_type": "started"}]}])
        w.finished("stuck")
        snap = self._snap()
        self.assertEqual(snap["run"]["pass"], 2)
        self.assertEqual(snap["run"]["stopped_reason"], "stuck")
        self.assertEqual(snap["stuck"][0]["ticket"], "DEMO-9")
        self.assertEqual(snap["stuck"][0]["blocked_by"][0]["state_type"], "started")
        # review fix: a no-claim run (wave→stuck→finished, never claimed) still gets a
        # run identity (started_at set at first wave), so two such runs don't collide in
        # the runReport dedupe and a real stuck-from-start pull is never swallowed.
        self.assertIsNotNone(snap["run"]["started_at"])

    def test_snapshot_is_always_valid_json_under_interleaved_reads(self):
        # A reader concurrent with a writer never parses a torn snapshot (R2) —
        # atomic temp+os.replace guarantees the file is whole or absent.
        w = ds.StatusWriter(base=self.base)
        w.claimed(_ticket(), wave=1, attempt=1)  # ensure the file exists
        stop = threading.Event()
        errors: list = []

        def writer():
            i = 0
            while not stop.is_set():
                i += 1
                t = _ticket(tid=f"u{i % 5}", ident=f"DEMO-{i % 5}")
                w.claimed(t, wave=1, attempt=1)
                w.terminal(t, {"ticket": f"DEMO-{i % 5}", "status": "completed",
                               "final_state": "done", "attempts": 1})

        def reader():
            p = ds._status_path(self.base)
            for _ in range(400):
                try:
                    json.loads(p.read_text(encoding="utf-8"))
                except FileNotFoundError:
                    pass
                except json.JSONDecodeError as exc:  # a torn read — the bug we guard
                    errors.append(str(exc))
                    return

        wt = threading.Thread(target=writer)
        wt.start()
        reader()
        stop.set()
        wt.join()
        self.assertEqual(errors, [])


class NoopWriterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.base = Path(self.tmp) / "director-status"

    def test_noop_writes_nothing(self):
        w = ds.NoopStatusWriter()
        # Every transition is a no-op and touches no disk.
        w.claimed(_ticket(), wave=1, attempt=1)
        w.dispatched(_ticket())
        w.terminal(_ticket(), {"ticket": "DEMO-1", "status": "completed",
                               "final_state": "done", "attempts": 1})
        w.wave(1)
        w.stuck([])
        w.finished("drained")
        self.assertFalse(ds._status_path(self.base).exists())
        self.assertIsNone(ds.read_status(base=self.base))


class ReadAndContextTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.base = Path(self.tmp) / "director-status"

    def test_read_status_absent_is_none(self):
        self.assertIsNone(ds.read_status(base=self.base))

    def test_read_status_unparseable_is_none(self):
        self.base.mkdir(parents=True)
        ds._status_path(self.base).write_text("{ not json", encoding="utf-8")
        self.assertIsNone(ds.read_status(base=self.base))

    def test_context_for_no_run_is_graceful(self):
        ctx = ds.context_for(_req(), base=self.base)
        self.assertIsNone(ctx["ticket"])
        self.assertEqual(ctx["siblings_in_flight"], [])
        self.assertEqual(ctx["recent_for_ticket"], [])
        self.assertEqual(ctx["stuck"], [])
        self.assertEqual(ctx["run"], {})  # safe default, not None (R4)

    def test_context_for_joins_ticket_siblings_prior_fail_and_stuck(self):
        w = ds.StatusWriter(base=self.base)
        # target ticket is on its retry (already failed once → attempt 2)
        w.claimed(_ticket("u1", "DEMO-1"), wave=2, attempt=2)
        # a sibling running concurrently
        w.claimed(_ticket("u2", "DEMO-2"), wave=2, attempt=1)
        # a prior terminal failure of the SAME ticket id (systemic signal)
        tprev = _ticket("u1", "DEMO-1")
        w.terminal(tprev, {"ticket": "DEMO-1", "status": "failed",
                           "final_state": "failed", "attempts": 1})
        # re-claim it (back in flight) so both an in_flight entry and a recent fail exist
        w.claimed(_ticket("u1", "DEMO-1"), wave=2, attempt=2)
        w.stuck([{"ticket": "DEMO-3", "blocked_by": [{"id": "u9", "state_type": None}]}])

        ctx = ds.context_for(_req(ticket_id="u1"), base=self.base)
        self.assertIsNotNone(ctx["ticket"])
        self.assertEqual(ctx["ticket"]["ticket_id"], "u1")
        self.assertEqual(ctx["ticket"]["attempt"], 2)
        self.assertEqual(ctx["ticket"]["wave"], 2)
        sib_ids = [s["ticket_id"] for s in ctx["siblings_in_flight"]]
        self.assertEqual(sib_ids, ["u2"])
        self.assertEqual([r["status"] for r in ctx["recent_for_ticket"]], ["failed"])
        self.assertEqual(ctx["stuck"][0]["ticket"], "DEMO-3")

    def test_cli_dumps_snapshot_and_joins_request(self):
        # The skill's communication surface: `python3 -m director.status` and
        # `--request <json>` are the Director's read commands (R6).
        w = ds.StatusWriter(base=self.base)
        w.claimed(_ticket("u1", "DEMO-1"), wave=1, attempt=2)

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = ds.main(["--status-dir", str(self.base)])
        self.assertEqual(rc, 0)
        snap = json.loads(buf.getvalue())
        self.assertEqual(snap["in_flight"][0]["ticket_id"], "u1")

        buf = io.StringIO()
        with redirect_stdout(buf):
            ds.main(["--status-dir", str(self.base),
                     "--request", json.dumps(_req(ticket_id="u1"))])
        ctx = json.loads(buf.getvalue())
        self.assertEqual(ctx["ticket"]["attempt"], 2)


if __name__ == "__main__":
    unittest.main()
