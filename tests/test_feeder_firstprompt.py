import sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import feeder_firstprompt as fp


class TestFirstPromptState(unittest.TestCase):
    def test_first_session_is_new_then_seen(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.assertTrue(fp.mark_if_new(root, "sess-1"))
            self.assertFalse(fp.mark_if_new(root, "sess-1"))
            self.assertTrue(fp.mark_if_new(root, "sess-2"))


if __name__ == "__main__":
    unittest.main()
