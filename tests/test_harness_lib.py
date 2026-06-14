import os, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import harness_lib as hl


class TestHarnessLib(unittest.TestCase):
    def test_frontmatter_parses_flat_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.md"
            p.write_text("---\nstatus: draft\nlast_verified: 2026-06-12\nowner: a\n---\n# hi\n")
            fm = hl.read_frontmatter(p)
            self.assertEqual(fm["status"], "draft")
            self.assertEqual(fm["owner"], "a")

    def test_frontmatter_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.md"
            p.write_text("# no frontmatter\n")
            self.assertIsNone(hl.read_frontmatter(p))

    def test_frontmatter_unterminated_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.md"
            p.write_text("---\nstatus: draft\n# body without closing fence\n")
            self.assertIsNone(hl.read_frontmatter(p))

    def test_is_headless_reads_env(self):
        import os
        os.environ.pop(hl.HEADLESS_ENV, None)
        self.assertFalse(hl.is_headless())
        os.environ[hl.HEADLESS_ENV] = "1"
        try:
            self.assertTrue(hl.is_headless())
        finally:
            del os.environ[hl.HEADLESS_ENV]

    def test_state_dir_creates_under_root(self):
        with tempfile.TemporaryDirectory() as d:
            sd = hl.state_dir(Path(d))
            self.assertTrue(sd.is_dir())
            self.assertEqual(sd, Path(d) / ".claude" / "harness")

    def test_gate_config_absent_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(hl.gate_config(Path(d)), {})

    def test_gate_config_parses_valid_object(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".harness.json").write_text(
                '{"lint_cmd": "make lint", "stale_days": 60}', encoding="utf-8")
            cfg = hl.gate_config(Path(d))
            self.assertEqual(cfg["lint_cmd"], "make lint")
            self.assertEqual(cfg["stale_days"], 60)

    def test_gate_config_malformed_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".harness.json").write_text("not json{{{", encoding="utf-8")
            self.assertEqual(hl.gate_config(Path(d)), {})

    def test_gate_config_non_object_returns_empty(self):
        # a top-level array/scalar is not a config object — fail open to {}
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".harness.json").write_text("[1, 2, 3]", encoding="utf-8")
            self.assertEqual(hl.gate_config(Path(d)), {})

    def test_gate_config_non_utf8_returns_empty(self):
        # a non-UTF8 byte must fail open, not be silently repaired into config
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".harness.json").write_bytes(b'{"lint_cmd": "echo \xff"}')
            self.assertEqual(hl.gate_config(Path(d)), {})

    def test_gate_command_absent_is_none(self):
        os.environ.pop("HARNESS_LINT_CMD", None)
        self.assertIsNone(hl.gate_command({}, "lint_cmd", "HARNESS_LINT_CMD"))

    def test_gate_command_splits_argv(self):
        os.environ.pop("HARNESS_LINT_CMD", None)
        self.assertEqual(
            hl.gate_command({"lint_cmd": "python3 .claude/lints/check.py"},
                            "lint_cmd", "HARNESS_LINT_CMD"),
            ["python3", ".claude/lints/check.py"])

    def test_gate_command_env_wins_over_config(self):
        os.environ["HARNESS_LINT_CMD"] = "env-cmd --flag"
        try:
            self.assertEqual(
                hl.gate_command({"lint_cmd": "cfg"}, "lint_cmd", "HARNESS_LINT_CMD"),
                ["env-cmd", "--flag"])
        finally:
            del os.environ["HARNESS_LINT_CMD"]

    def test_gate_command_non_string_and_blank_are_none(self):
        os.environ.pop("HARNESS_LINT_CMD", None)
        self.assertIsNone(hl.gate_command({"lint_cmd": 5}, "lint_cmd", "HARNESS_LINT_CMD"))
        self.assertIsNone(hl.gate_command({"lint_cmd": True}, "lint_cmd", "HARNESS_LINT_CMD"))
        self.assertIsNone(hl.gate_command({"lint_cmd": "  "}, "lint_cmd", "HARNESS_LINT_CMD"))

    def test_gate_command_unparseable_raises(self):
        # present but broken (unbalanced quote) must be LOUD, not a silent skip
        os.environ.pop("HARNESS_LINT_CMD", None)
        with self.assertRaises(ValueError):
            hl.gate_command({"lint_cmd": "foo '"}, "lint_cmd", "HARNESS_LINT_CMD")

    def test_within_repo_no_symlink_allows_plain_path(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "docs").mkdir()
            (root / "docs" / "x.md").write_text("hi")
            self.assertEqual(hl.within_repo_no_symlink(root, "docs/x.md"),
                             root / "docs" / "x.md")

    def test_within_repo_no_symlink_refuses_symlinked_component(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
            root = Path(d)
            decoy = Path(out) / "evil.md"
            decoy.write_text("outside")
            os.symlink(decoy, root / "x.md")             # the target itself is a symlink
            self.assertIsNone(hl.within_repo_no_symlink(root, "x.md"))

    def test_within_repo_no_symlink_refuses_dotdot_escape(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            root.mkdir()
            self.assertIsNone(hl.within_repo_no_symlink(root, "../escape.md"))


if __name__ == "__main__":
    unittest.main()
