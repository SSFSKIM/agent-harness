import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import memories_db as mdb
import memories_workspace as mw

NOW = 1_000_000_000
DAY = 86400


class TestStem(unittest.TestCase):
    def test_deterministic_sortable_with_and_without_slug(self):
        a = mw.summary_stem("de8dd75b-df88-40a2-8cc4-28a077775542", NOW, "My Slug!")
        b = mw.summary_stem("de8dd75b-df88-40a2-8cc4-28a077775542", NOW, "My Slug!")
        self.assertEqual(a, b)                                  # deterministic
        self.assertTrue(a.endswith("-my_slug"))                # sanitized, trailing _ stripped
        self.assertIn("de8dd75b", a)                           # short id from thread hex
        noslug = mw.summary_stem("de8dd75b-df88-40a2-8cc4-28a077775542", NOW, "")
        self.assertFalse(noslug.endswith("-"))


class TestWorkspace(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.conn = mdb.connect(self.root)
        self.wdir = mw.workspace_dir(self.root)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def _put(self, tid, raw, summ, slug, age_days=1):
        mdb.upsert_stage1_output(self.conn, tid, NOW - age_days * DAY,
                                 raw, summ, slug, NOW)

    def test_ensure_baseline_idempotent(self):
        mw.ensure_baseline(self.wdir)
        self.assertTrue((self.wdir / ".git").is_dir())
        head1 = mw._git(self.wdir, ["rev-parse", "HEAD"]).stdout.strip()
        mw.ensure_baseline(self.wdir)                           # keeps existing
        head2 = mw._git(self.wdir, ["rev-parse", "HEAD"]).stdout.strip()
        self.assertEqual(head1, head2)

    def test_sync_writes_faithful_format_in_thread_order(self):
        self._put("bbb", "raw-B", "summary-B", "slug-b")
        self._put("aaa", "raw-A", "summary-A", "slug-a")
        mw.ensure_baseline(self.wdir)
        rows = mdb.select_phase2_inputs(self.conn, 256, 30, NOW)
        mw.sync_inputs(self.wdir, self.root, rows)
        raw = (self.wdir / mw.RAW_MEMORIES_FILE).read_text()
        self.assertTrue(raw.startswith("# Raw Memories"))
        self.assertIn("## Thread `aaa`", raw)
        self.assertIn("raw-A", raw)
        self.assertLess(raw.index("Thread `aaa`"), raw.index("Thread `bbb`"))  # stable order
        # one rollout_summaries file per thread, carrying the summary body
        files = sorted((self.wdir / mw.ROLLOUT_SUMMARIES_DIR).glob("*.md"))
        self.assertEqual(len(files), 2)
        self.assertIn("summary-A", (self.wdir / mw.ROLLOUT_SUMMARIES_DIR /
                                    (mw.summary_stem("aaa", NOW - DAY, "slug-a") + ".md")).read_text())

    def test_empty_selection_writes_placeholder(self):
        mw.ensure_baseline(self.wdir)
        mw.sync_inputs(self.wdir, self.root, [])
        self.assertIn("No raw memories yet.",
                      (self.wdir / mw.RAW_MEMORIES_FILE).read_text())

    def test_diff_is_the_dirty_check_init_then_skip(self):
        self._put("aaa", "raw-A", "summary-A", "slug-a")
        res1 = mw.select_and_sync(self.conn, self.root, NOW)
        self.assertTrue(res1["dirty"])                         # INIT: files added
        statuses = {s for s, _p in res1["changes"]}
        self.assertIn("A", statuses)
        self.assertTrue((self.wdir / mw.WORKSPACE_DIFF_FILE).exists())
        mw.reset_baseline(self.wdir)
        # nothing changed since the new baseline -> not dirty (agent must skip)
        res2 = mw.select_and_sync(self.conn, self.root, NOW)
        self.assertFalse(res2["dirty"])
        self.assertEqual(res2["changes"], [])

    def test_add_and_forget_show_as_changes(self):
        self._put("aaa", "raw-A", "summary-A", "slug-a")
        mw.select_and_sync(self.conn, self.root, NOW)
        mw.reset_baseline(self.wdir)
        # add a new rollout AND remove the old one from the selection
        self.conn.execute("DELETE FROM stage1_outputs WHERE thread_id='aaa'")
        self.conn.commit()
        self._put("zzz", "raw-Z", "summary-Z", "slug-z")
        res = mw.select_and_sync(self.conn, self.root, NOW)
        self.assertTrue(res["dirty"])
        statuses = {s for s, _p in res["changes"]}
        self.assertTrue({"A"} & statuses)                      # zzz summary added
        self.assertTrue({"D"} & statuses)                      # aaa summary deleted (forget)
        # raw_memories.md modified to drop aaa, add zzz
        raw = (self.wdir / mw.RAW_MEMORIES_FILE).read_text()
        self.assertIn("Thread `zzz`", raw)
        self.assertNotIn("Thread `aaa`", raw)

    def test_resync_same_rows_is_not_dirty(self):
        self._put("aaa", "raw-A", "summary-A", "slug-a")
        mw.select_and_sync(self.conn, self.root, NOW)
        mw.reset_baseline(self.wdir)
        res = mw.select_and_sync(self.conn, self.root, NOW)    # identical content
        self.assertFalse(res["dirty"])                         # determinism: no churn

    def test_diff_artifact_never_in_git(self):
        self._put("aaa", "raw-A", "summary-A", "slug-a")
        mw.select_and_sync(self.conn, self.root, NOW)          # writes the diff file
        mw.reset_baseline(self.wdir)
        tracked = mw._git(self.wdir, ["ls-files"]).stdout
        self.assertNotIn(mw.WORKSPACE_DIFF_FILE, tracked)      # gitignored


if __name__ == "__main__":
    unittest.main()
