import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugin-workspace"
EXPECTED_SKILLS = ("commit", "debug", "land", "linear", "pull", "push")


def _frontmatter_value_present(text, key):
    """True if a `---`-delimited frontmatter block defines `key` with a non-empty
    value — inline (`key: v`) OR a YAML block scalar (`key:` then indented lines).
    Tolerant of the multi-line form the vendored Symphony skills use, which a
    naive `key: value` parser would miss."""
    if not text.startswith("---"):
        return False
    parts = text.split("---", 2)
    if len(parts) < 3:
        return False
    block = parts[1].splitlines()
    for i, line in enumerate(block):
        m = re.match(rf"^{re.escape(key)}:(.*)$", line)
        if not m:
            continue
        if m.group(1).strip():
            return True  # inline value
        # block scalar: the next indented, non-blank line carries the value
        for nxt in block[i + 1:]:
            if not nxt.strip():
                continue
            return bool(re.match(r"^\s+\S", nxt))
        return False
    return False


class WorkspacePluginTest(unittest.TestCase):
    """The vendored worker-skill bundle ships as the standalone, Apache-2.0
    `agent-harness-workspace` plugin. The core gate lints (lint_structure /
    gen_inventory) stay single-plugin by design (they govern the MIT machine
    `plugin/`), so this test is the structural governance for the vendored bundle:
    a valid manifest, every skill present with SKILL.md frontmatter, and the
    Apache-2.0 LICENSE + attribution NOTICE the public MIT repo requires."""

    def test_plugin_manifest_valid(self):
        data = json.loads((PLUGIN / ".claude-plugin" / "plugin.json")
                          .read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "agent-harness-workspace")
        self.assertTrue(data.get("version"), "plugin.json needs a version")
        self.assertTrue(data.get("description"), "plugin.json needs a description")

    def test_exactly_the_expected_skills_present(self):
        dirs = sorted(p.name for p in (PLUGIN / "skills").iterdir() if p.is_dir())
        self.assertEqual(dirs, sorted(EXPECTED_SKILLS))

    def test_every_skill_has_name_and_description_frontmatter(self):
        for name in EXPECTED_SKILLS:
            skill = PLUGIN / "skills" / name / "SKILL.md"
            self.assertTrue(skill.is_file(), f"{name}: missing SKILL.md")
            text = skill.read_text(encoding="utf-8")
            self.assertTrue(_frontmatter_value_present(text, "name"),
                            f"{name}: SKILL.md needs a non-empty `name`")
            self.assertTrue(_frontmatter_value_present(text, "description"),
                            f"{name}: SKILL.md needs a non-empty `description`")

    def test_license_and_notice_present(self):
        self.assertTrue((PLUGIN / "LICENSE").is_file(), "Apache-2.0 LICENSE required")
        notice = PLUGIN / "NOTICE"
        self.assertTrue(notice.is_file(), "attribution NOTICE required")
        self.assertIn("openai/symphony", notice.read_text(encoding="utf-8"),
                      "NOTICE must attribute the openai/symphony upstream")

    def test_registered_in_marketplace(self):
        market = json.loads((REPO / ".claude-plugin" / "marketplace.json")
                            .read_text(encoding="utf-8"))
        entry = next((p for p in market["plugins"]
                      if p["name"] == "agent-harness-workspace"), None)
        self.assertIsNotNone(entry, "agent-harness-workspace not in marketplace.json")
        self.assertEqual(entry["source"], "./plugin-workspace")


if __name__ == "__main__":
    unittest.main()
