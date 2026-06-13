import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import dream_phase2 as dp2
import memories_db as mdb
import memories_workspace as mw

NOW = 1_000_000_000
DAY = 86400


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True, text=True)


class _RepoCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        # a host repo with the dreaming workspace gitignored (so git-visible ==
        # outside-the-workspace, the scope check's invariant)
        (self.root / ".gitignore").write_text(".claude/harness/\n", encoding="utf-8")
        (self.root / "src").mkdir()
        (self.root / "src" / "app.py").write_text("print('original')\n", encoding="utf-8")
        _git(self.root, "init", "-q")
        _git(self.root, "config", "user.email", "t@t")
        _git(self.root, "config", "user.name", "t")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "--no-verify", "-m", "init")
        self.conn = mdb.connect(self.root)
        self.wdir = mw.workspace_dir(self.root)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def _seed(self, tid="aaa"):
        mdb.upsert_stage1_output(self.conn, tid, NOW - DAY, "raw-A",
                                 "summary-A", "slug-a", NOW)

    def _write_good_outputs(self):
        (self.wdir / "MEMORY.md").write_text("# Task Group: x\nscope: y\n", encoding="utf-8")
        (self.wdir / "memory_summary.md").write_text("v1\n\n## User Profile\nU\n", encoding="utf-8")


class TestScopeCheck(_RepoCase):
    def test_reverts_create_modify_delete_preserving_others(self):
        (self.root / "keep.txt").write_text("KEEP", encoding="utf-8")  # untracked, untouched
        before = dp2.snapshot_outside_workspace(self.root)
        # simulate an escaping agent
        (self.root / "evil.txt").write_text("EVIL", encoding="utf-8")          # create
        (self.root / "src" / "app.py").write_text("HACKED", encoding="utf-8")  # modify tracked
        (self.root / "keep.txt").unlink()                                      # delete
        escaped = dp2.enforce_workspace_scope(self.root, before)
        self.assertEqual(set(escaped), {"evil.txt", "src/app.py", "keep.txt"})
        self.assertFalse((self.root / "evil.txt").exists())                    # created → removed
        self.assertEqual((self.root / "src" / "app.py").read_text(), "print('original')\n")
        self.assertEqual((self.root / "keep.txt").read_text(), "KEEP")         # restored

    def test_workspace_writes_are_not_escapes(self):
        mw.ensure_baseline(self.wdir)
        before = dp2.snapshot_outside_workspace(self.root)
        self._write_good_outputs()                            # writes inside the workspace
        self.assertEqual(dp2.enforce_workspace_scope(self.root, before), [])

    def test_gitignored_and_dotgit_escapes_are_caught(self):
        # codex P1: the boundary is the filesystem, not git-visibility. A write
        # into a gitignored path or .git/hooks (code-exec) must be reverted.
        (self.root / ".gitignore").write_text(".claude/harness/\nsecret.env\n", encoding="utf-8")
        (self.root / ".git" / "hooks").mkdir(exist_ok=True)
        before = dp2.snapshot_outside_workspace(self.root)
        (self.root / "secret.env").write_text("KEY=1", encoding="utf-8")            # gitignored
        (self.root / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh\nevil\n", encoding="utf-8")
        escaped = dp2.enforce_workspace_scope(self.root, before)
        self.assertIn("secret.env", escaped)
        self.assertIn(os.path.join(".git", "hooks", "pre-commit"), escaped)
        self.assertFalse((self.root / "secret.env").exists())                       # reverted
        self.assertFalse((self.root / ".git" / "hooks" / "pre-commit").exists())

    def _outside_dir(self):
        # an isolated location OUTSIDE the repo (not the shared system temp)
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        return Path(t.name)

    def test_symlink_swap_does_not_write_through(self):
        # codex P1: replacing a file with a symlink must restore the original file,
        # never write the saved bytes THROUGH the link into an outside target.
        outside = self._outside_dir() / "outside_target.txt"
        outside.write_text("ORIGINAL_OUTSIDE", encoding="utf-8")
        before = dp2.snapshot_outside_workspace(self.root)
        (self.root / "src" / "app.py").unlink()
        os.symlink(outside, self.root / "src" / "app.py")          # swap file → symlink
        dp2.enforce_workspace_scope(self.root, before)
        self.assertFalse((self.root / "src" / "app.py").is_symlink())   # link removed
        self.assertEqual((self.root / "src" / "app.py").read_text(), "print('original')\n")
        self.assertEqual(outside.read_text(), "ORIGINAL_OUTSIDE")   # NOT written through

    def test_parent_dir_symlink_swap_does_not_write_through(self):
        # codex P1 (2nd pass): agent turns a parent DIR into a symlink to outside;
        # restoring src/app.py must NOT write through to outside/app.py.
        outside = self._outside_dir() / "outside_dir"
        outside.mkdir()
        (outside / "app.py").write_text("OUTSIDE_ORIGINAL", encoding="utf-8")
        before = dp2.snapshot_outside_workspace(self.root)
        shutil.rmtree(self.root / "src")
        os.symlink(outside, self.root / "src")                  # src → symlink to outside
        dp2.enforce_workspace_scope(self.root, before)
        self.assertFalse((self.root / "src").is_symlink())      # symlink removed
        self.assertTrue((self.root / "src").is_dir())           # real dir restored
        self.assertEqual((self.root / "src" / "app.py").read_text(), "print('original')\n")
        self.assertEqual((outside / "app.py").read_text(), "OUTSIDE_ORIGINAL")  # not written through

    def test_overcap_new_file_reverted_preexisting_kept(self):
        orig = dp2.SNAPSHOT_FILE_CAP
        dp2.SNAPSHOT_FILE_CAP = 8                              # tiny cap → small files are "over-cap"
        try:
            (self.root / "big_pre.bin").write_text("X" * 100, encoding="utf-8")  # pre-existing over-cap
            before = dp2.snapshot_outside_workspace(self.root)
            (self.root / "big_new.bin").write_text("Y" * 100, encoding="utf-8")  # NEW over-cap escape
            escaped = dp2.enforce_workspace_scope(self.root, before)
            self.assertIn("big_new.bin", escaped)
            self.assertFalse((self.root / "big_new.bin").exists())   # new over-cap reverted (any size)
            self.assertTrue((self.root / "big_pre.bin").exists())    # pre-existing untouched
            self.assertNotIn("big_pre.bin", escaped)
        finally:
            dp2.SNAPSHOT_FILE_CAP = orig


class TestConsolidate(_RepoCase):
    def _spy(self, agent):
        calls = []

        def spawn(workspace, model):
            calls.append((workspace, model))
            agent(Path(workspace))
            return ""
        return spawn, calls

    def test_happy_init_consolidates_and_marks_selection(self):
        self._seed()
        spawn, calls = self._spy(lambda w: self._write_good_outputs())
        res = dp2.consolidate(self.conn, self.root, NOW, spawn=spawn)
        self.assertEqual(res["status"], "consolidated")
        self.assertEqual(len(calls), 1)                       # agent ran (dirty)
        self.assertTrue((self.wdir / "MEMORY.md").exists())
        sel = self.conn.execute(
            "SELECT selected_for_phase2 FROM stage1_outputs WHERE thread_id='aaa'"
        ).fetchone()
        self.assertEqual(sel["selected_for_phase2"], 1)       # selection marked

    def test_escape_is_reverted_and_run_rejected(self):
        self._seed()

        def agent(w):
            self._write_good_outputs()                        # plausible-looking output
            (self.root / "POISON.md").write_text("injected", encoding="utf-8")  # escape!
            (self.root / "src" / "app.py").write_text("HACKED", encoding="utf-8")
        spawn, _ = self._spy(agent)
        res = dp2.consolidate(self.conn, self.root, NOW, spawn=spawn)
        self.assertEqual(res["status"], "rejected")
        self.assertEqual(set(res["escaped"]), {"POISON.md", "src/app.py"})
        self.assertFalse((self.root / "POISON.md").exists())  # reverted
        self.assertEqual((self.root / "src" / "app.py").read_text(), "print('original')\n")
        # workspace rolled back; selection NOT marked; job failed (backoff)
        self.assertFalse((self.wdir / "MEMORY.md").exists())
        sel = self.conn.execute(
            "SELECT selected_for_phase2 FROM stage1_outputs WHERE thread_id='aaa'"
        ).fetchone()
        self.assertEqual(sel["selected_for_phase2"], 0)

    def test_invalid_output_rejected(self):
        self._seed()

        def agent(w):
            (w / "MEMORY.md").write_text("# Task Group: x\n", encoding="utf-8")
            (w / "memory_summary.md").write_text("NOT-v1\n", encoding="utf-8")  # bad header
        spawn, _ = self._spy(agent)
        res = dp2.consolidate(self.conn, self.root, NOW, spawn=spawn)
        self.assertEqual(res["status"], "rejected")
        self.assertTrue(any("v1" in p for p in res["problems"]))

    def test_clean_skips_agent(self):
        self._seed()
        # pre-bake the baseline to already contain the synced inputs
        mw.ensure_baseline(self.wdir)
        rows = mdb.select_phase2_inputs(self.conn, 256, 30, NOW)
        mw.sync_inputs(self.wdir, self.root, rows)
        mw.reset_baseline(self.wdir)
        spawn, calls = self._spy(lambda w: None)
        res = dp2.consolidate(self.conn, self.root, NOW, spawn=spawn)
        self.assertEqual(res["status"], "clean")
        self.assertEqual(calls, [])                            # no model spawned

    def test_lock_held_skips(self):
        self._seed()
        mdb.claim_phase2(self.conn, "other", 3600, NOW)        # someone holds the lock
        spawn, calls = self._spy(lambda w: self._write_good_outputs())
        res = dp2.consolidate(self.conn, self.root, NOW, spawn=spawn)
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
