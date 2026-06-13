import os, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import check


class TestResolveCmd(unittest.TestCase):
    """resolve_cmd picks a gate-step command from env (ad-hoc) over the
    versioned .harness.json, ignoring malformed values."""

    def setUp(self):
        os.environ.pop("HARNESS_LINT_CMD", None)

    def tearDown(self):
        os.environ.pop("HARNESS_LINT_CMD", None)

    def test_absent_everywhere_is_none(self):
        self.assertIsNone(check.resolve_cmd({}, "lint_cmd", "HARNESS_LINT_CMD"))

    def test_config_value_used_when_no_env(self):
        self.assertEqual(
            check.resolve_cmd({"lint_cmd": "make lint"}, "lint_cmd", "HARNESS_LINT_CMD"),
            "make lint")

    def test_env_overrides_config(self):
        os.environ["HARNESS_LINT_CMD"] = "env-cmd"
        self.assertEqual(
            check.resolve_cmd({"lint_cmd": "cfg-cmd"}, "lint_cmd", "HARNESS_LINT_CMD"),
            "env-cmd")

    def test_non_string_config_ignored(self):
        # JSON number/bool/list for lint_cmd is not a command — ignore, don't crash.
        self.assertIsNone(check.resolve_cmd({"lint_cmd": 5}, "lint_cmd", "HARNESS_LINT_CMD"))
        self.assertIsNone(check.resolve_cmd({"lint_cmd": True}, "lint_cmd", "HARNESS_LINT_CMD"))

    def test_blank_string_ignored(self):
        self.assertIsNone(check.resolve_cmd({"lint_cmd": "   "}, "lint_cmd", "HARNESS_LINT_CMD"))


if __name__ == "__main__":
    unittest.main()
