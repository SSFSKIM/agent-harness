import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import dream_run as dr
import harness_lib as hl
import memories_db as mdb
import memories_workspace as mw

NOW = 1_000_000_000
DAY = 86400


class TestLock(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.lock = Path(self._tmp.name) / "dream.lock"

    def tearDown(self):
        self._tmp.cleanup()

    def test_single_flight(self):
        fd = dr.acquire_lock(self.lock)
        self.assertIsNotNone(fd)
        self.assertIsNone(dr.acquire_lock(self.lock))      # held → refused
        os.close(fd)
        self.lock.unlink()
        fd2 = dr.acquire_lock(self.lock)                   # released → acquirable
        self.assertIsNotNone(fd2)
        os.close(fd2)

    def test_stale_lock_reclaimed(self):
        fd = dr.acquire_lock(self.lock)
        os.close(fd)
        old = time.time() - dr.LOCK_STALE - 10
        os.utime(self.lock, (old, old))                    # simulate a crashed run
        fd2 = dr.acquire_lock(self.lock)
        self.assertIsNotNone(fd2)                          # reclaimed
        os.close(fd2)


class TestRunWiring(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._home = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / ".gitignore").write_text(".claude/harness/\n", encoding="utf-8")
        (self.root / "f.txt").write_text("x", encoding="utf-8")
        for a in (["init", "-q"], ["config", "user.email", "t@t"],
                  ["config", "user.name", "t"], ["add", "-A"],
                  ["commit", "-q", "--no-verify", "-m", "i"]):
            subprocess.run(["git", "-C", str(self.root), *a], check=True, capture_output=True)
        os.environ["CLAUDE_HOME"] = self._home.name
        tdir = hl.project_transcripts_dir(self.root)
        tdir.mkdir(parents=True)
        tp = tdir / "tid1.jsonl"
        tp.write_text(json.dumps(
            {"type": "user", "message": {"role": "user", "content": "do X"}}) + "\n",
            encoding="utf-8")
        ts = NOW - 2 * DAY                                  # idle 2d → inside the window
        os.utime(tp, (ts, ts))
        self.conn = mdb.connect(self.root)

    def tearDown(self):
        self.conn.close()
        os.environ.pop("CLAUDE_HOME", None)
        self._tmp.cleanup()
        self._home.cleanup()

    def test_phase1_to_phase2_chain(self):
        def p1spawn(prompt, model):
            return json.dumps({"rollout_summary": "s", "rollout_slug": "sl",
                               "raw_memory": "m"})

        wdir = mw.workspace_dir(self.root)

        def p2spawn(workspace, model):
            (Path(workspace) / "MEMORY.md").write_text("# Task Group: x\nscope: y\n",
                                                       encoding="utf-8")
            (Path(workspace) / "memory_summary.md").write_text("v1\n\n## User Profile\nU\n",
                                                               encoding="utf-8")
            return ""

        res = dr.run(self.conn, self.root, NOW,
                     phase1_spawn=p1spawn, phase2_spawn=p2spawn)
        self.assertEqual(res["phase1"]["claimed"], 1)              # discovered+claimed the rollout
        self.assertEqual(res["phase1"]["results"][0]["outcome"], "saved")
        self.assertEqual(res["phase2"]["status"], "consolidated")  # P2 ran on P1's output
        self.assertTrue((wdir / "MEMORY.md").exists())
        sel = self.conn.execute(
            "SELECT selected_for_phase2 FROM stage1_outputs WHERE thread_id='tid1'"
        ).fetchone()
        self.assertEqual(sel["selected_for_phase2"], 1)

    def test_no_eligible_rollouts_skips_consolidation(self):
        # remove the only transcript → nothing to extract → no inputs + no existing
        # handbook → P2 skips the (pointless) empty consolidation without a model
        for f in hl.project_transcripts_dir(self.root).glob("*.jsonl"):
            f.unlink()
        called = []
        res = dr.run(self.conn, self.root, NOW,
                     phase1_spawn=lambda p, m: "{}",
                     phase2_spawn=lambda w, m: called.append(1) or "")
        self.assertEqual(res["phase1"]["claimed"], 0)
        self.assertEqual(res["phase2"]["status"], "empty")
        self.assertEqual(called, [])                        # no model spawned


if __name__ == "__main__":
    unittest.main()
