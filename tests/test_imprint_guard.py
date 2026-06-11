import sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import imprint_guard as guard


class TestImprintGuard(unittest.TestCase):
    def test_key_formats(self):
        self.assertEqual(guard.key("s1", "session_end"), "s1:session_end")
        self.assertEqual(guard.key("s1", "pre_compact", "123"), "s1:pre_compact:123")

    def test_mark_and_check(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            k = guard.key("s1", "session_end")
            self.assertFalse(guard.already_processed(root, k))
            guard.mark_processed(root, k)
            self.assertTrue(guard.already_processed(root, k))
            self.assertFalse(guard.already_processed(root, guard.key("s2", "session_end")))


if __name__ == "__main__":
    unittest.main()
