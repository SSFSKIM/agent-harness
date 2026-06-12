import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import scaffold

PLUGIN = Path(__file__).resolve().parent.parent / "plugin"
TIDY = PLUGIN / "scripts" / "tidy_stop.py"


def run_tidy(root, extra_env=None):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(root)
    env.update(extra_env or {})
    return subprocess.run([sys.executable, str(TIDY)], input="{}",
                          cwd=root, env=env, capture_output=True, text=True)


def git(root, *args):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
                   cwd=root, check=True, capture_output=True)


class TestTidyStop(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        scaffold.scaffold(self.root, PLUGIN, lambda _: None)
        git(self.root, "init", "-q")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "--no-verify", "-m", "seed")

    def tearDown(self):
        self._tmp.cleanup()

    def test_headless_guard_exits_zero(self):
        r = run_tidy(self.root, {"HARNESS_HEADLESS": "1"})
        self.assertEqual(r.returncode, 0)

    def test_green_tree_passes_and_caches(self):
        r = run_tidy(self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        state = self.root / ".claude" / "harness" / "tidy-fingerprint.txt"
        self.assertTrue(state.exists())
        self.assertEqual(run_tidy(self.root).returncode, 0)

    def test_lint_fail_blocks_once_then_never_again(self):
        bad = self.root / "docs" / "design-docs" / "core-beliefs.md"
        bad.write_text("# no frontmatter\n", encoding="utf-8")
        first = run_tidy(self.root)
        self.assertEqual(first.returncode, 2)
        self.assertIn("FAIL", first.stderr)
        self.assertIn("FIX", first.stderr)
        second = run_tidy(self.root)  # same dirty state — must not block again
        self.assertEqual(second.returncode, 0)

    def test_fixing_the_tree_returns_green(self):
        bad = self.root / "docs" / "design-docs" / "core-beliefs.md"
        original = bad.read_text(encoding="utf-8")
        bad.write_text("# no frontmatter\n", encoding="utf-8")
        self.assertEqual(run_tidy(self.root).returncode, 2)
        bad.write_text(original, encoding="utf-8")
        r = run_tidy(self.root)  # changed state — rechecks, now green
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_non_harness_repo_is_ignored(self):
        (self.root / "docs" / "memory" / "MEMORY.md").unlink()
        r = run_tidy(self.root)  # activation sentinel gone — must no-op
        self.assertEqual(r.returncode, 0)

    def test_non_git_root_fails_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scaffold.scaffold(root, PLUGIN, lambda _: None)
            self.assertEqual(run_tidy(root).returncode, 0)


if __name__ == "__main__":
    unittest.main()
