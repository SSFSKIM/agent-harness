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


if __name__ == "__main__":
    unittest.main()
