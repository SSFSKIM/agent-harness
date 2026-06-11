import sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import feeder_sessionstart as fs
from fixtures import fm


class TestFeederFallback(unittest.TestCase):
    def test_fallback_pack_inlines_bootloader_and_progress(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            mem = root / "docs" / "memory" / "progress"
            mem.mkdir(parents=True)
            (root / "docs" / "memory" / "MEMORY.md").write_text("# boot\n")
            (mem / "current.md").write_text(fm() + "# Current\nnow\n")
            pack = fs.fallback_pack(root)
            self.assertIn("# boot", pack)
            self.assertIn("now", pack)

    def test_fallback_pack_empty_when_no_memory(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(fs.fallback_pack(Path(d)), "")


if __name__ == "__main__":
    unittest.main()
