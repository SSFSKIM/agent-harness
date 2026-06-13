import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import dream_discover as dd
import harness_lib as hl
import memories_db as mdb

NOW = 1_000_000_000
DAY = 86400
HOUR = 3600


def _touch(tdir, tid, age_seconds, now=NOW):
    """Create `<tid>.jsonl` with mtime = now - age_seconds."""
    p = Path(tdir) / f"{tid}.jsonl"
    p.write_text("{}\n", encoding="utf-8")
    ts = now - age_seconds
    os.utime(p, (ts, ts))
    return p


class TestDiscover(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _ids(self, **kw):
        return [t for t, _p, _ts in dd.discover_rollouts(self.tdir, NOW, **kw)]

    def test_window_includes_idle_recent_excludes_active_and_stale(self):
        _touch(self.tdir, "active", 1 * HOUR)        # too warm (< 6h idle)
        _touch(self.tdir, "good", 2 * DAY)           # idle + recent -> in
        _touch(self.tdir, "stale", 20 * DAY)         # older than 10d -> out
        self.assertEqual(self._ids(), ["good"])

    def test_boundaries_are_inclusive(self):
        _touch(self.tdir, "edge_idle", 6 * HOUR)     # exactly the idle cutoff
        _touch(self.tdir, "edge_age", 10 * DAY)      # exactly the age cutoff
        self.assertEqual(set(self._ids()), {"edge_idle", "edge_age"})

    def test_excludes_current_thread(self):
        _touch(self.tdir, "keep", 2 * DAY)
        _touch(self.tdir, "current", 2 * DAY)
        self.assertEqual(self._ids(exclude=["current"]), ["keep"])

    def test_ignores_non_jsonl(self):
        _touch(self.tdir, "real", 2 * DAY)
        (self.tdir / "notes.md").write_text("x", encoding="utf-8")
        os.utime(self.tdir / "notes.md", (NOW - 2 * DAY, NOW - 2 * DAY))
        self.assertEqual(self._ids(), ["real"])

    def test_freshest_first_and_scan_limit(self):
        _touch(self.tdir, "old", 9 * DAY)
        _touch(self.tdir, "mid", 5 * DAY)
        _touch(self.tdir, "new", 1 * DAY)
        self.assertEqual(self._ids(), ["new", "mid", "old"])      # freshest-first
        self.assertEqual(self._ids(scan_limit=2), ["new", "mid"])  # bounded scan

    def test_missing_dir_is_empty(self):
        self.assertEqual(
            dd.discover_rollouts(self.tdir / "nope", NOW), [])


class TestClaim(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = mdb.connect(Path(self._tmp.name))

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def _rollouts(self, *specs):
        # specs: (thread_id, age_days) -> rollout tuples freshest-first
        rows = [(tid, Path(f"/x/{tid}.jsonl"), NOW - age * DAY)
                for tid, age in specs]
        rows.sort(key=lambda r: (r[2], r[0]), reverse=True)
        return rows

    def test_claims_up_to_max(self):
        rollouts = self._rollouts(("a", 1), ("b", 2), ("c", 3))
        claimed = dd.claim_rollouts(self.conn, rollouts, "w1", NOW, max_claimed=2)
        self.assertEqual([t for t, *_ in claimed], ["a", "b"])  # freshest two
        self.assertTrue(all(tok for *_, tok in claimed))

    def test_skips_up_to_date(self):
        # "done" already has a Phase-1 output at the same source ts -> not claimed
        mdb.upsert_stage1_output(self.conn, "done", NOW - 1 * DAY, "m", "s",
                                 "done", NOW)
        rollouts = self._rollouts(("done", 1), ("fresh", 2))
        claimed = dd.claim_rollouts(self.conn, rollouts, "w1", NOW, max_claimed=5)
        self.assertEqual([t for t, *_ in claimed], ["fresh"])

    def test_skips_already_leased(self):
        rollouts = self._rollouts(("a", 1))
        first = dd.claim_rollouts(self.conn, rollouts, "w1", NOW)
        self.assertEqual(len(first), 1)
        # a second pass while the lease is live claims nothing
        again = dd.claim_rollouts(self.conn, rollouts, "w2", NOW)
        self.assertEqual(again, [])


class TestTranscriptsDir(unittest.TestCase):
    def test_slug_encoding_and_home_override(self):
        with tempfile.TemporaryDirectory() as home:
            os.environ["CLAUDE_HOME"] = home
            try:
                d = hl.project_transcripts_dir("/Users/x/My Repo")
            finally:
                del os.environ["CLAUDE_HOME"]
            self.assertEqual(d, Path(home) / "projects" / "-Users-x-My-Repo")


if __name__ == "__main__":
    unittest.main()
