import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import docs_sync as ds

NOW = 1_700_000_000
GREEN = lambda root: True           # gate stub: synthetic repos aren't full harness repos
RED = lambda root: False


class _Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.dd = self.root / "docs" / "design-docs"
        self.dd.mkdir(parents=True)
        (self.root / "docs" / "journal").mkdir(parents=True)
        self.foo = self.dd / "foo.md"
        self.foo.write_text(
            "---\nstatus: draft\nlast_verified: 2026-01-01\nowner: harness\n---\n"
            "# Foo\n\nThe feeder_sessionstart hook compiles a pack.\n"
            "See feeder_sessionstart-notes for details.\n\n"
            "## Decision log\n\n- 2026-01-01: routed claim about caching — because.\n",
            encoding="utf-8")

    def _foo(self):
        return self.foo.read_text(encoding="utf-8")

    def _journal(self, body):
        (self.root / "docs" / "journal" / "2026-06.md").write_text(body, encoding="utf-8")

    def _apply(self, plan, run_check=GREEN, run_generator=None):
        gen = run_generator or (lambda root, target: False)
        return ds.apply_plan(self.root, plan, NOW, run_check=run_check, run_generator=gen)


# ---- mechanical kinds apply correctly --------------------------------------

class TestMechanical(_Case):
    def test_rename_is_verbatim_and_boundary_safe(self):
        # mechanical-3: swaps the token everywhere it stands alone, but must NOT
        # corrupt the larger identifier `feeder_sessionstart-notes`.
        plan = [{"target": "docs/design-docs/foo.md", "kind": "outdated",
                 "evidence": "scripts/x.py:1 renamed", "risk": "mechanical",
                 "change": {"op": "rename", "old": "feeder_sessionstart",
                            "new": "feeder_start"}}]
        res = self._apply(plan)
        self.assertEqual(len(res["applied"]), 1)
        foo = self._foo()
        self.assertIn("feeder_start hook compiles", foo)
        self.assertIn("feeder_sessionstart-notes", foo)     # adjacent token untouched
        self.assertNotIn("feeder_sessionstart hook", foo)

    def test_set_frontmatter_last_verified(self):
        plan = [{"target": "docs/design-docs/foo.md", "kind": "outdated",
                 "change": {"op": "set_frontmatter", "field": "last_verified",
                            "value": "2026-06-14"}, "risk": "mechanical"}]
        res = self._apply(plan)
        self.assertEqual(len(res["applied"]), 1)
        self.assertIn("last_verified: 2026-06-14", self._foo())
        self.assertNotIn("last_verified: 2026-01-01", self._foo())

    def test_set_frontmatter_status_in_allowlist(self):
        plan = [{"target": "docs/design-docs/foo.md",
                 "change": {"op": "set_frontmatter", "field": "status",
                            "value": "stable"}}]
        self.assertEqual(len(self._apply(plan)["applied"]), 1)
        self.assertIn("status: stable", self._foo())

    def test_regenerate_runs_generator(self):
        # mechanical-1: content comes from the injected generator, never the agent.
        out = self.root / "docs" / "generated" / "component-inventory.md"

        def fake_gen(root, target):
            self.assertEqual(target, "docs/generated/component-inventory.md")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("# regenerated\n", encoding="utf-8")
            return True
        plan = [{"target": "docs/generated/component-inventory.md",
                 "change": {"op": "regenerate"}, "kind": "outdated"}]
        res = self._apply(plan, run_generator=fake_gen)
        self.assertEqual(len(res["applied"]), 1)
        self.assertIn("regenerated", out.read_text(encoding="utf-8"))

    def test_retract_deletes_attributable_line(self):
        # mechanical-4: the journal proves the router authored this line into foo.md.
        self._journal('## run\n- [routed] decision "routed claim about caching" '
                      '-> docs/design-docs/foo.md\n')
        line = "- 2026-01-01: routed claim about caching — because."
        plan = [{"target": "docs/design-docs/foo.md", "kind": "retract",
                 "change": {"op": "retract", "line": line}}]
        res = self._apply(plan)
        self.assertEqual(len(res["applied"]), 1)
        self.assertNotIn("routed claim about caching", self._foo())


# ---- the re-validator forces everything else to the report -----------------

class TestReportNotEdit(_Case):
    def test_free_prose_change_reports_not_edits(self):
        before = self._foo()
        plan = [{"target": "docs/design-docs/foo.md", "risk": "semantic",
                 "change": {"op": "rewrite", "text": "a whole new paragraph"}}]
        res = self._apply(plan)
        self.assertEqual(res["applied"], [])
        self.assertEqual(len(res["report"]), 1)
        self.assertEqual(self._foo(), before)               # untouched

    def test_semantic_mislabeled_mechanical_is_downgraded(self):
        # risk claims mechanical, but the rename's `old` is not in the doc → report.
        before = self._foo()
        plan = [{"target": "docs/design-docs/foo.md", "risk": "mechanical",
                 "change": {"op": "rename", "old": "not_present_symbol",
                            "new": "x"}}]
        res = self._apply(plan)
        self.assertEqual(res["applied"], [])
        self.assertIn("not found verbatim", res["report"][0]["reason"])
        self.assertEqual(self._foo(), before)

    def test_rename_non_symbol_reports(self):
        plan = [{"target": "docs/design-docs/foo.md", "risk": "mechanical",
                 "change": {"op": "rename", "old": "the feeder", "new": "the pack"}}]
        res = self._apply(plan)
        self.assertEqual(res["applied"], [])
        self.assertIn("not plain symbols", res["report"][0]["reason"])

    def test_frontmatter_field_out_of_allowlist_reports(self):
        before = self._foo()
        plan = [{"target": "docs/design-docs/foo.md",
                 "change": {"op": "set_frontmatter", "field": "owner",
                            "value": "attacker"}}]
        res = self._apply(plan)
        self.assertEqual(res["applied"], [])
        self.assertEqual(self._foo(), before)

    def test_retract_without_provenance_reports(self):
        # no journal [routed] line → the line is presumed human prose → report.
        line = "- 2026-01-01: routed claim about caching — because."
        plan = [{"target": "docs/design-docs/foo.md",
                 "change": {"op": "retract", "line": line}}]
        res = self._apply(plan)
        self.assertEqual(res["applied"], [])
        self.assertIn("provenance", res["report"][0]["reason"])
        self.assertIn("routed claim about caching", self._foo())   # kept

    def test_retract_line_not_present_reports(self):
        self._journal('- [routed] decision "ghost" -> docs/design-docs/foo.md\n')
        plan = [{"target": "docs/design-docs/foo.md",
                 "change": {"op": "retract", "line": "- a line that is not there"}}]
        res = self._apply(plan)
        self.assertEqual(res["applied"], [])
        self.assertIn("not found verbatim", res["report"][0]["reason"])


# ---- guards: symlink containment + gate rollback ---------------------------

class TestGuards(_Case):
    def test_symlinked_target_refused(self):
        with tempfile.TemporaryDirectory() as out:
            decoy = Path(out) / "evil.md"
            decoy.write_text("---\nlast_verified: 2026-01-01\n---\n# outside\n",
                             encoding="utf-8")
            self.foo.unlink()
            os.symlink(decoy, self.foo)                  # allowlist file → outside repo
            plan = [{"target": "docs/design-docs/foo.md",
                     "change": {"op": "set_frontmatter", "field": "last_verified",
                                "value": "2026-06-14"}}]
            res = self._apply(plan)
            self.assertEqual(res["applied"], [])
            self.assertIn("out-of-allowlist", res["report"][0]["reason"])
            self.assertIn("2026-01-01", decoy.read_text(encoding="utf-8"))   # untouched

    def test_out_of_docs_target_reported(self):
        (self.root / "secrets.md").write_text("# nope\n", encoding="utf-8")
        plan = [{"target": "../secrets.md",
                 "change": {"op": "rename", "old": "nope", "new": "pwned"}}]
        res = self._apply(plan)
        self.assertEqual(res["applied"], [])

    def test_red_gate_rolls_whole_batch_back(self):
        before = self._foo()
        plan = [{"target": "docs/design-docs/foo.md",
                 "change": {"op": "rename", "old": "feeder_sessionstart",
                            "new": "feeder_start"}}]
        res = self._apply(plan, run_check=RED)
        self.assertTrue(res["rolled_back"])
        self.assertEqual(res["applied"], [])
        self.assertEqual(self._foo(), before)            # reverted to pre-edit bytes


# ---- a mixed plan: mechanical applied, semantic surfaced -------------------

class TestMixedPlan(_Case):
    def test_one_applied_one_reported(self):
        plan = [
            {"target": "docs/design-docs/foo.md",
             "change": {"op": "rename", "old": "feeder_sessionstart",
                        "new": "feeder_start"}},
            {"target": "docs/design-docs/foo.md", "risk": "semantic",
             "change": {"op": "rewrite", "text": "free prose"}},
        ]
        res = self._apply(plan)
        self.assertEqual(len(res["applied"]), 1)
        self.assertEqual(len(res["report"]), 1)
        self.assertIn("feeder_start", self._foo())


# ---- M2: change-driven scope builder ---------------------------------------

class TestParseDiffSurface(unittest.TestCase):
    """Pure parser, no git — exact surface extraction with file:line evidence."""
    def test_added_removed_and_files(self):
        diff = (
            "diff --git a/m.py b/m.py\n"
            "--- a/m.py\n+++ b/m.py\n"
            "@@ -4,1 +4,2 @@\n"
            "-def old_fn(x):\n"
            "+def new_fn(x):\n"
            "+MAX_RETRIES = 3\n"
            "diff --git a/cli.py b/cli.py\n"
            "--- a/cli.py\n+++ b/cli.py\n"
            "@@ -10,0 +11,1 @@\n"
            '+    ap.add_argument("--verbose")\n')
        scope = ds.parse_diff_surface(diff)
        syms = {(s["symbol"], s["kind"], s["file"], s["line"]) for s in scope["changed_symbols"]}
        self.assertIn(("new_fn", "function", "m.py", 4), syms)
        self.assertIn(("MAX_RETRIES", "constant", "m.py", 5), syms)
        self.assertIn(("verbose", "flag", "cli.py", 11), syms)
        removed = {(s["symbol"], s["file"]) for s in scope["removed"]}
        self.assertIn(("old_fn", "m.py"), removed)
        self.assertEqual({f["path"] for f in scope["changed_files"]}, {"m.py", "cli.py"})

    def test_modified_symbol_is_not_removed(self):
        # def foo present on both sides → a change, never a removal.
        diff = ("diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n"
                "@@ -1,1 +1,1 @@\n-def foo(a):\n+def foo(a, b):\n")
        scope = ds.parse_diff_surface(diff)
        self.assertEqual(scope["removed"], [])
        self.assertEqual(scope["changed_symbols"][0]["symbol"], "foo")

    def test_deleted_and_added_file_status(self):
        diff = ("diff --git a/gone.py b/gone.py\ndeleted file mode 100644\n"
                "--- a/gone.py\n+++ /dev/null\n@@ -1,1 +0,0 @@\n-def doomed():\n"
                "diff --git a/new.py b/new.py\nnew file mode 100644\n"
                "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1,1 @@\n+def fresh():\n")
        scope = ds.parse_diff_surface(diff)
        status = {f["path"]: f["status"] for f in scope["changed_files"]}
        self.assertEqual(status, {"gone.py": "deleted", "new.py": "added"})
        self.assertIn("doomed", {s["symbol"] for s in scope["removed"]})
        self.assertIn("fresh", {s["symbol"] for s in scope["changed_symbols"]})


class TestBuildChangeScope(unittest.TestCase):
    """End-to-end against a real temp git repo (per the ExecPlan)."""
    def _git(self, *args):
        import subprocess
        subprocess.run(["git", "-C", str(self.root), *args], check=True,
                       capture_output=True, text=True,
                       env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self._git("init", "-q")
        (self.root / "m.py").write_text("def old_fn(x):\n    return x\n", encoding="utf-8")
        self._git("add", "-A"); self._git("commit", "-q", "-m", "base")
        self.base = __import__("subprocess").run(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"],
            capture_output=True, text=True).stdout.strip()

    def test_known_diff_exact_surface(self):
        (self.root / "m.py").write_text("def new_fn(x):\n    return x\n", encoding="utf-8")
        self._git("add", "-A"); self._git("commit", "-q", "-m", "rename")
        scope = ds.build_change_scope(self.root, base=self.base)
        self.assertIn("new_fn", {s["symbol"] for s in scope["changed_symbols"]})
        self.assertIn("old_fn", {s["symbol"] for s in scope["removed"]})
        self.assertEqual(scope["changed_files"], [{"path": "m.py", "status": "modified"}])

    def test_no_op_diff_empty_scope(self):
        scope = ds.build_change_scope(self.root, base=self.base)   # base == HEAD
        self.assertEqual(scope, {"changed_files": [], "changed_symbols": [], "removed": []})


if __name__ == "__main__":
    unittest.main()
