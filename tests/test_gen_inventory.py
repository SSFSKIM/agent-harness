import json, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import gen_inventory
from fixtures import make_plugin


class TestGenInventory(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.plugin = make_plugin(Path(self._tmp.name))
        sk = self.plugin / "skills" / "execplan"
        sk.mkdir()
        (sk / "SKILL.md").write_text("---\nname: execplan\ndescription: Living ExecPlans\n---\n")
        (self.plugin / "agents" / "dreamer.md").write_text(
            "---\nname: dreamer\ndescription: Consolidates memory\n---\nbody\n")
        hooks = {"hooks": {"SessionStart": [{"hooks": [{"type": "command",
                 "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/feeder_sessionstart.py\""}]}]}}
        (self.plugin / "hooks" / "hooks.json").write_text(json.dumps(hooks))
        self.out = Path(self._tmp.name) / "docs" / "generated" / "component-inventory.md"
        self.out.parent.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_build_lists_all_components(self):
        text = gen_inventory.build(self.plugin)
        for token in ("GENERATED", "execplan", "dreamer", "SessionStart",
                      "feeder_sessionstart.py"):
            self.assertIn(token, text)

    def test_check_detects_drift(self):
        self.out.write_text(gen_inventory.build(self.plugin))
        self.assertTrue(gen_inventory.check(self.plugin, self.out))
        self.out.write_text("hand edited\n")
        self.assertFalse(gen_inventory.check(self.plugin, self.out))

    def test_check_fails_when_missing(self):
        self.assertFalse(gen_inventory.check(self.plugin, self.out))

    def test_inventory_check_required_for_self_host(self):
        self.assertTrue(gen_inventory.check_required(Path(self._tmp.name), self.plugin))

    def test_inventory_check_advisory_for_external_plugin_by_default(self):
        repo = Path(self._tmp.name) / "host"
        repo.mkdir()
        self.assertFalse(gen_inventory.check_required(repo, self.plugin))

    def test_inventory_check_strict_for_external_plugin_when_opted_in(self):
        repo = Path(self._tmp.name) / "host"
        repo.mkdir()
        self.assertTrue(gen_inventory.check_required(
            repo, self.plugin, {"component_inventory": "strict"}))


if __name__ == "__main__":
    unittest.main()
