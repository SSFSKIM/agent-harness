import os, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import check


class TestHostStep(unittest.TestCase):
    """_host_step turns a host gate command into (argv, error): absent is a
    no-op, a valid command becomes argv, a present-but-broken one fails CLOSED
    (an error string the gate surfaces) rather than skipping silently."""

    def setUp(self):
        os.environ.pop("HARNESS_LINT_CMD", None)

    def tearDown(self):
        os.environ.pop("HARNESS_LINT_CMD", None)

    def test_absent_is_noop(self):
        self.assertEqual(check._host_step({}, "lint_cmd", "HARNESS_LINT_CMD"),
                         (None, None))

    def test_valid_returns_argv(self):
        argv, err = check._host_step({"lint_cmd": "python3 .claude/lints/check.py"},
                                     "lint_cmd", "HARNESS_LINT_CMD")
        self.assertEqual(argv, ["python3", ".claude/lints/check.py"])
        self.assertIsNone(err)

    def test_unparseable_fails_closed(self):
        argv, err = check._host_step({"lint_cmd": "foo '"},
                                     "lint_cmd", "HARNESS_LINT_CMD")
        self.assertIsNone(argv)
        self.assertIsNotNone(err)
        self.assertIn("FAIL gate lint_cmd", err)


if __name__ == "__main__":
    unittest.main()
