import json, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import lint_structure
from fixtures import make_plugin


def run_all(plugin):
    errors = []
    lint_structure.check_imports(plugin, errors)
    lint_structure.check_path_discipline(plugin, errors)
    lint_structure.check_no_abs_paths(plugin, errors)
    lint_structure.check_hooks(plugin, errors)
    lint_structure.check_agents(plugin, errors)
    lint_structure.check_skills(plugin, errors)
    lint_structure.check_self_host_paths(plugin, errors)
    return errors


class TestLintStructure(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.plugin = make_plugin(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_empty_plugin_is_green(self):
        self.assertEqual(run_all(self.plugin), [])

    def test_s1_third_party_import(self):
        (self.plugin / "scripts" / "bad.py").write_text("import requests\n")
        self.assertTrue(any("S1" in e for e in run_all(self.plugin)))

    def test_s2_cwd_outside_lib(self):
        (self.plugin / "scripts" / "bad.py").write_text("import os\nx = os.getcwd()\n")
        self.assertTrue(any("S2" in e for e in run_all(self.plugin)))

    def test_s3_absolute_path(self):
        (self.plugin / "scripts" / "bad.py").write_text("P = '/Users/someone/repo'\n")
        self.assertTrue(any("S3" in e for e in run_all(self.plugin)))

    def test_s4_hooks_must_use_plugin_root_var(self):
        hooks = {"hooks": {"SessionStart": [{"hooks": [
            {"type": "command", "command": "python3 scripts/x.py"}]}]}}
        (self.plugin / "hooks" / "hooks.json").write_text(json.dumps(hooks))
        self.assertTrue(any("S4" in e for e in run_all(self.plugin)))

    def test_s4_unknown_event(self):
        hooks = {"hooks": {"OnTeleport": []}}
        (self.plugin / "hooks" / "hooks.json").write_text(json.dumps(hooks))
        self.assertTrue(any("S4" in e for e in run_all(self.plugin)))

    def test_s5_review_agent_needs_grounding(self):
        (self.plugin / "agents" / "review-x.md").write_text(
            "---\nname: review-x\ndescription: d\n---\nNo grounding here.\n")
        self.assertTrue(any("S5" in e for e in run_all(self.plugin)))

    def test_s6_skill_missing_skill_md(self):
        (self.plugin / "skills" / "ghost").mkdir()
        self.assertTrue(any("S6" in e for e in run_all(self.plugin)))

    def test_s7_self_host_path_in_plugin_markdown(self):
        d = self.plugin / "skills" / "x"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            "---\nname: x\ndescription: d\n---\nRun python3 plugin/scripts/check.py\n")
        self.assertTrue(any("S7" in e for e in run_all(self.plugin)))

    def test_s4_missing_referenced_script(self):
        hooks = {"hooks": {"SessionStart": [{"hooks": [
            {"type": "command",
             "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/ghost.py\""}]}]}}
        (self.plugin / "hooks" / "hooks.json").write_text(json.dumps(hooks))
        errs = run_all(self.plugin)
        self.assertTrue(any("S4" in e and "ghost.py" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
