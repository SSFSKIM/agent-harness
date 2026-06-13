import sys, tempfile, unittest
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


if __name__ == "__main__":
    unittest.main()
