import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import lint_base  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugin"
REAL_BASE = REPO / "base"


class LintBaseTest(unittest.TestCase):
    """packaging Slice 6 R6.2: the base/ drift-check must pass on the in-sync base
    and FAIL on each drift class, and be a no-op when base/ is absent (ported host)."""

    def _tmp_root_with_base(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        shutil.copytree(REAL_BASE, d / "base")
        return d

    def _errors(self, root):
        errors = []
        lint_base.check_base(root, PLUGIN, errors)
        return errors

    def test_real_base_in_sync(self):
        self.assertEqual(self._errors(REPO), [],
                         "the committed base/ must be in sync with the seed templates")

    def test_missing_seed_file_fails_b1(self):
        root = self._tmp_root_with_base()
        (root / "base" / "docs" / "PLANS.md").unlink()
        self.assertTrue(any(e.startswith("B1") for e in self._errors(root)))

    def test_edited_file_fails_b2(self):
        root = self._tmp_root_with_base()
        f = root / "base" / "docs" / "CHARTER.md"
        f.write_text(f.read_text(encoding="utf-8") + "\nDRIFT\n", encoding="utf-8")
        self.assertTrue(any(e.startswith("B2") for e in self._errors(root)))

    def test_stale_component_table_fails_b2(self):
        # The base's machine index (agent-harness.md's COMPONENTS table) going stale
        # vs. the live plugin is the component-list drift R6.2 must catch.
        root = self._tmp_root_with_base()
        f = root / "base" / "docs" / "design-docs" / "agent-harness.md"
        f.write_text(f.read_text(encoding="utf-8").replace("| skill |", "| stale |", 1),
                     encoding="utf-8")
        errs = self._errors(root)
        self.assertTrue(any(e.startswith("B2") and "agent-harness.md" in e for e in errs))

    def test_extra_file_fails_b3(self):
        root = self._tmp_root_with_base()
        (root / "base" / "docs" / "STRAY.md").write_text("legacy", encoding="utf-8")
        self.assertTrue(any(e.startswith("B3") for e in self._errors(root)))

    def test_generated_present_fails_b4(self):
        root = self._tmp_root_with_base()
        g = root / "base" / "docs" / "generated"
        g.mkdir(parents=True)
        (g / "component-inventory.md").write_text("x", encoding="utf-8")
        self.assertTrue(any(e.startswith("B4") for e in self._errors(root)))

    def test_missing_setup_fails_b5(self):
        root = self._tmp_root_with_base()
        (root / "base" / "SETUP.md").unlink()
        self.assertTrue(any(e.startswith("B5") for e in self._errors(root)))

    def test_non_utf8_base_file_fails_not_raises(self):
        # R22 totality: a non-UTF8 base file degrades to a coded FAIL, never a traceback.
        root = self._tmp_root_with_base()
        (root / "base" / "docs" / "PLANS.md").write_bytes(b"\xff\xfe not utf-8")
        errs = self._errors(root)  # must not raise
        self.assertTrue(any(e.startswith("B2") for e in errs))

    def test_read_helper_is_total(self):
        # R22: _read never raises — a missing path returns (None, reason).
        text, err = lint_base._read(Path(tempfile.gettempdir()) / "definitely-not-here-xyz.md")
        self.assertIsNone(text)
        self.assertIsNotNone(err)

    def test_no_base_is_noop_exit0(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(d)}
        r = subprocess.run([sys.executable, str(PLUGIN / "scripts" / "lint_base.py")],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0)
        self.assertIn("SKIP", r.stdout)


if __name__ == "__main__":
    unittest.main()
