import sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import memories_db as mdb

NOW = 1_000_000_000
DAY = 86400


class TestMemoriesDb(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = mdb.connect(Path(self._tmp.name))

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def _put(self, tid, src_age_days, raw="m", summ="s"):
        mdb.upsert_stage1_output(self.conn, tid, NOW - src_age_days * DAY,
                                 raw, summ, tid, NOW)

    def test_upsert_only_replaces_with_newer_source(self):
        self._put("t", 5, raw="old")
        # an older source must NOT overwrite
        mdb.upsert_stage1_output(self.conn, "t", NOW - 9 * DAY, "newer-but-older-src",
                                 "s", "t", NOW)
        row = self.conn.execute(
            "SELECT raw_memory FROM stage1_outputs WHERE thread_id='t'").fetchone()
        self.assertEqual(row["raw_memory"], "old")

    def test_selection_ranks_by_usage_then_recency(self):
        self._put("a", 1); self._put("b", 1); self._put("c", 2)
        mdb.record_usage(self.conn, ["a"], NOW)            # a: usage 1
        mdb.record_usage(self.conn, ["a"], NOW)            # a: usage 2
        mdb.record_usage(self.conn, ["c"], NOW)            # c: usage 1
        # rank: a(2) > c(1) > b(0). top-2 => {a, c}; returned thread_id-sorted.
        sel = mdb.select_phase2_inputs(self.conn, 2, 30, NOW)
        self.assertEqual([r["thread_id"] for r in sel], ["a", "c"])

    def test_never_used_uses_recency_fallback_and_window(self):
        self._put("fresh", 5)     # never used, within 30d
        self._put("stale", 40)    # never used, outside 30d
        ids = [r["thread_id"] for r in mdb.select_phase2_inputs(self.conn, 10, 30, NOW)]
        self.assertIn("fresh", ids)
        self.assertNotIn("stale", ids)

    def test_empty_output_is_not_selectable(self):
        mdb.upsert_stage1_output(self.conn, "noop", NOW - DAY, "", "", None, NOW)
        ids = [r["thread_id"] for r in mdb.select_phase2_inputs(self.conn, 10, 30, NOW)]
        self.assertNotIn("noop", ids)

    def test_prune_removes_dead_keeps_selected(self):
        self._put("dead", 40)      # stale, unselected -> prune target
        self._put("kept", 40)      # stale, but selected -> retained
        mdb.mark_phase2_selected(self.conn, [("kept", NOW - 40 * DAY)])
        n = mdb.prune_stage1_outputs(self.conn, 30, NOW)
        self.assertEqual(n, 1)
        rows = {r["thread_id"] for r in self.conn.execute(
            "SELECT thread_id FROM stage1_outputs").fetchall()}
        self.assertEqual(rows, {"kept"})

    def test_dropped_thread_ids_are_stale_and_unselected(self):
        self._put("dropped", 40)   # stale, unselected -> a forgetting candidate
        self._put("kept", 40)      # stale, but selected -> retained
        self._put("fresh", 1)      # unselected but inside the window -> not dropped
        mdb.mark_phase2_selected(self.conn, [("kept", NOW - 40 * DAY)])
        self.assertEqual(mdb.dropped_thread_ids(self.conn, 30, NOW), ["dropped"])
        # read-only: the rows still exist (unlike prune)
        rows = {r["thread_id"] for r in self.conn.execute(
            "SELECT thread_id FROM stage1_outputs").fetchall()}
        self.assertEqual(rows, {"dropped", "kept", "fresh"})

    def test_usage_bump_sets_count_and_timestamp(self):
        self._put("t", 1)
        mdb.record_usage(self.conn, ["t"], NOW)
        row = self.conn.execute(
            "SELECT usage_count, last_usage FROM stage1_outputs "
            "WHERE thread_id='t'").fetchone()
        self.assertEqual(row["usage_count"], 1)
        self.assertEqual(row["last_usage"], NOW)

    def test_stage1_claim_lease_and_needs_update(self):
        self.assertTrue(mdb.stage1_needs_update(self.conn, "t", NOW))
        tok = mdb.claim_stage1_job(self.conn, "t", "w1", NOW, 3600, NOW)
        self.assertIsNotNone(tok)
        # a second claim while leased is refused
        self.assertIsNone(mdb.claim_stage1_job(self.conn, "t", "w2", NOW, 3600, NOW))
        mdb.finish_stage1_job(self.conn, "t", tok, NOW, NOW, ok=True)
        # watermark advanced -> no longer needs update at the same source ts
        self.assertFalse(mdb.stage1_needs_update(self.conn, "t", NOW))

    def test_stage1_failure_backs_off_then_retries(self):
        tok = mdb.claim_stage1_job(self.conn, "t", "w1", NOW, 3600, NOW)
        mdb.finish_stage1_job(self.conn, "t", tok, NOW, NOW, ok=False,
                              error="boom", retry_delay=3600)
        # within backoff window -> refused
        self.assertIsNone(mdb.claim_stage1_job(self.conn, "t", "w1", NOW, 3600, NOW))
        # after backoff -> claimable again
        self.assertIsNotNone(
            mdb.claim_stage1_job(self.conn, "t", "w1", NOW, 3600, NOW + 3601))

    def test_phase2_lock_cooldown_and_heartbeat(self):
        tok = mdb.claim_phase2(self.conn, "w1", 3600, NOW)
        self.assertIsNotNone(tok)
        self.assertIsNone(mdb.claim_phase2(self.conn, "w2", 3600, NOW))  # running
        self.assertTrue(mdb.heartbeat_phase2(self.conn, tok, 3600, NOW + 90))
        mdb.finish_phase2(self.conn, tok, NOW + 100, ok=True)
        # within the 6h cooldown -> refused
        self.assertIsNone(mdb.claim_phase2(self.conn, "w1", 3600, NOW + 200))
        # after cooldown -> claimable
        self.assertIsNotNone(
            mdb.claim_phase2(self.conn, "w1", 3600, NOW + 100 + mdb.PHASE2_COOLDOWN + 1))


if __name__ == "__main__":
    unittest.main()
