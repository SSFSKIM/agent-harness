import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import scaffold

PLUGIN = Path(__file__).resolve().parent.parent / "plugin"


class TestScaffold(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.logs = []
        scaffold.scaffold(self.root, PLUGIN, self.logs.append)

    def tearDown(self):
        self._tmp.cleanup()

    def test_tree_created(self):
        for rel in ("AGENTS.md", "CLAUDE.md", "ARCHITECTURE.md",
                    "docs/memory/MEMORY.md",
                    "docs/memory/progress/current.md",
                    "docs/memory/openq/index.md",
                    "docs/design-docs/agent-harness.md",
                    "docs/exec-plans/tech-debt-tracker.md",
                    "docs/generated/component-inventory.md",
                    "docs/PLANS.md", "docs/DESIGN.md", "docs/QUALITY_SCORE.md",
                    "docs/PRODUCT_SENSE.md", "docs/product-specs/index.md",
                    "docs/references/index.md"):
            self.assertTrue((self.root / rel).exists(), rel)

    def test_no_unrendered_tokens(self):
        for p in self.root.rglob("*.md"):
            self.assertNotIn("{{", p.read_text(encoding="utf-8"), p.name)

    def test_idempotent_never_overwrites(self):
        agents = self.root / "AGENTS.md"
        agents.write_text("# custom map\n", encoding="utf-8")
        logs = []
        scaffold.scaffold(self.root, PLUGIN, logs.append)
        self.assertEqual(agents.read_text(encoding="utf-8"), "# custom map\n")
        self.assertTrue(any(l.startswith("SKIP") and "AGENTS.md" in l for l in logs))

    def test_every_component_mentioned(self):
        page = (self.root / "docs/design-docs/agent-harness.md").read_text(encoding="utf-8")
        names = [d.parent.name for d in (PLUGIN / "skills").glob("*/SKILL.md")]
        names += [a.stem for a in (PLUGIN / "agents").glob("*.md")]
        self.assertTrue(names)
        for name in names:
            self.assertIn(name, page)

    def test_gitignore_appended_once(self):
        gi = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".claude/harness/", gi)
        scaffold.scaffold(self.root, PLUGIN, lambda _: None)
        gi2 = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(gi2.count(".claude/harness/"), 1)

    def test_git_hook_installed_and_idempotent(self):
        (self.root / ".git" / "hooks").mkdir(parents=True)
        scaffold.scaffold(self.root, PLUGIN, lambda _: None)
        hook = self.root / ".git" / "hooks" / "pre-commit"
        self.assertTrue(hook.exists())
        self.assertTrue(hook.stat().st_mode & 0o111)
        self.assertIn("check.py", hook.read_text(encoding="utf-8"))
        logs = []
        scaffold.scaffold(self.root, PLUGIN, logs.append)
        self.assertTrue(any("SKIP" in l and "pre-commit" in l for l in logs))

    def test_foreign_pre_commit_never_overwritten(self):
        hooks = self.root / ".git" / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "pre-commit").write_text("#!/bin/sh\necho custom\n")
        scaffold.scaffold(self.root, PLUGIN, lambda _: None)
        self.assertEqual((hooks / "pre-commit").read_text(),
                         "#!/bin/sh\necho custom\n")

    def test_fresh_host_is_lint_green(self):
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(self.root)
        for script, args in (("lint_docs.py", []), ("lint_structure.py", []),
                             ("gen_inventory.py", ["--check"])):
            r = subprocess.run(
                [sys.executable, str(PLUGIN / "scripts" / script), *args],
                cwd=self.root, env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{script}: {r.stdout}{r.stderr}")


if __name__ == "__main__":
    unittest.main()
