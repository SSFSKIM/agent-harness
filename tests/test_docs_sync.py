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

    def _apply(self, plan, run_check=GREEN, run_generator=None, changed_symbols=None):
        gen = run_generator or (lambda root, target: False)
        return ds.apply_plan(self.root, plan, NOW, run_check=run_check,
                             run_generator=gen, changed_symbols=changed_symbols)

    def _hash(self, line):
        return ds.hl.line_provenance_hash(line)


# ---- mechanical kinds apply correctly --------------------------------------

class TestMechanical(_Case):
    def test_rename_is_verbatim_and_boundary_safe(self):
        # mechanical-3: swaps the token everywhere it stands alone, but must NOT
        # corrupt the larger identifier `feeder_sessionstart-notes`.
        plan = [{"target": "docs/design-docs/foo.md", "kind": "outdated",
                 "evidence": "scripts/x.py:1 renamed", "risk": "mechanical",
                 "change": {"op": "rename", "old": "feeder_sessionstart",
                            "new": "feeder_start"}}]
        res = self._apply(plan, changed_symbols={"feeder_sessionstart"})
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
        # mechanical-4: the journal's @<hash> proves the router authored THIS exact
        # line into foo.md, so deleting it reverses a router append.
        line = "- 2026-01-01: routed claim about caching — because."
        self._journal('## run\n- [routed] decision "routed claim about caching" '
                      '-> docs/design-docs/foo.md @' + self._hash(line) + '\n')
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
        # risk claims mechanical and `old` IS a changed symbol, but it is not in the
        # doc → still report (the verbatim-presence check is the last gate).
        before = self._foo()
        plan = [{"target": "docs/design-docs/foo.md", "risk": "mechanical",
                 "change": {"op": "rename", "old": "not_present_symbol",
                            "new": "x"}}]
        res = self._apply(plan, changed_symbols={"not_present_symbol"})
        self.assertEqual(res["applied"], [])
        self.assertIn("not found verbatim", res["report"][0]["reason"])
        self.assertEqual(self._foo(), before)

    def test_rename_non_symbol_reports(self):
        plan = [{"target": "docs/design-docs/foo.md", "risk": "mechanical",
                 "change": {"op": "rename", "old": "the feeder", "new": "the pack"}}]
        res = self._apply(plan, changed_symbols={"the feeder"})
        self.assertEqual(res["applied"], [])
        self.assertIn("symbol-shaped", res["report"][0]["reason"])

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
        res = self._apply(plan, run_check=RED, changed_symbols={"feeder_sessionstart"})
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
        res = self._apply(plan, changed_symbols={"feeder_sessionstart"})
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


# ---- M3: the read-only audit agent + plan parsing --------------------------

import json as _json

STUB_TMPL = ("AUDIT SYSTEM", "SCOPE:\n{scope}\nEND")


class TestParseMaintenancePlan(unittest.TestCase):
    def test_extracts_plan_from_prose(self):
        plan = ds.parse_maintenance_plan(
            'Here is the plan:\n{"plan":[{"target":"docs/x.md","kind":"outdated"}]}\n')
        self.assertEqual(plan, [{"target": "docs/x.md", "kind": "outdated"}])

    def test_keeps_dicts_drops_non_dicts(self):
        plan = ds.parse_maintenance_plan(_json.dumps(
            {"plan": [{"kind": "outdated"}, "notadict", 5]}))
        self.assertEqual(plan, [{"kind": "outdated"}])

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            ds.parse_maintenance_plan("   ")

    def test_no_plan_list_raises(self):
        with self.assertRaises(ValueError):
            ds.parse_maintenance_plan('{"foo": 1}')


class TestAudit(_Case):
    def test_audit_renders_scope_and_returns_parsed_plan(self):
        captured = {}

        def stub(prompt, model, cwd, timeout):
            captured["prompt"] = prompt
            captured["cwd"] = cwd
            return '{"plan":[{"target":"docs/design-docs/foo.md","kind":"outdated",' \
                   '"evidence":"m.py:1","change":{"op":"rename","old":"feeder_sessionstart",' \
                   '"new":"feeder_start"},"risk":"mechanical"}]}'
        scope = {"changed_symbols": [{"symbol": "feeder_sessionstart", "file": "m.py"}]}
        plan = ds.audit(scope, self.root, spawn=stub, templates=STUB_TMPL)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["change"]["op"], "rename")
        self.assertIn("feeder_sessionstart", captured["prompt"])   # scope embedded as DATA
        self.assertEqual(captured["cwd"], self.root)

    def test_audit_to_apply_seam_mechanical_fix(self):
        # the M3 -> M1 seam: a live-shaped plan flows into the deterministic applicator.
        def stub(prompt, model, cwd, timeout):
            return '{"plan":[{"target":"docs/design-docs/foo.md","kind":"outdated",' \
                   '"evidence":"m.py:1","change":{"op":"rename","old":"feeder_sessionstart",' \
                   '"new":"feeder_start"},"risk":"mechanical"}]}'
        plan = ds.audit({"changed_symbols": []}, self.root, spawn=stub, templates=STUB_TMPL)
        res = ds.apply_plan(self.root, plan, NOW, run_check=GREEN,
                            changed_symbols={"feeder_sessionstart"})
        self.assertEqual(len(res["applied"]), 1)
        self.assertIn("feeder_start hook compiles", self._foo())


# ---- M4: the completion-gate orchestration ---------------------------------

class TestRun(_Case):
    def _spawn(self, plan_json):
        return lambda prompt, model, cwd, timeout: plan_json

    def test_run_scope_to_apply(self):
        plan = '{"plan":[{"target":"docs/design-docs/foo.md","kind":"outdated",' \
               '"change":{"op":"rename","old":"feeder_sessionstart","new":"feeder_start"},' \
               '"risk":"mechanical"}]}'
        # audit() reads real templates from the plugin dir; spawn is stubbed.
        res = ds.run(self.root, scope={"changed_symbols": [{"symbol": "feeder_sessionstart"}]},
                     spawn=self._spawn(plan), now=NOW, run_check=GREEN)
        self.assertEqual(len(res["applied"]), 1)
        self.assertEqual(len(res["plan"]), 1)
        self.assertIn("feeder_start hook compiles", self._foo())

    def test_run_empty_scope_is_noop_and_never_spawns(self):
        def boom(*a, **k):
            raise AssertionError("audit agent must not run on an empty scope")
        res = ds.run(self.root, scope={"changed_files": [], "changed_symbols": [],
                                       "removed": []}, spawn=boom, now=NOW, run_check=GREEN)
        self.assertEqual(res, {"applied": [], "report": [], "rolled_back": False, "plan": []})

    def test_run_surfaces_semantic_without_blocking(self):
        plan = '{"plan":[{"target":"docs/design-docs/foo.md","kind":"structural",' \
               '"change":{"op":"rewrite","text":"reorganize"},"risk":"semantic"}]}'
        res = ds.run(self.root, scope={"removed": [{"symbol": "x"}]},
                     spawn=self._spawn(plan), now=NOW, run_check=GREEN)
        self.assertEqual(res["applied"], [])
        self.assertEqual(len(res["report"]), 1)        # surfaced, not applied, not blocked


# ---- M5 (v1.1): provenance-driven forgetting -------------------------------

class TestForgetting(_Case):
    def _journal_block(self, thread, snippet, target, line=None):
        prov = f'- [routed] decision "{snippet}" -> {target}'
        if line is not None:                       # record the exact-line hash
            prov += " @" + ds.hl.line_provenance_hash(line)
        (self.root / "docs" / "journal" / "2026-06.md").write_text(
            f"## 2026-06-14T00:00Z — dream run (sessions: {thread[:8]})\n"
            + prov + "\n", encoding="utf-8")

    def test_provenance_scope_names_dropped_targets(self):
        self._journal_block("threadAAA000", "routed claim about caching",
                            "docs/design-docs/foo.md")
        scope = ds.build_provenance_scope(self.root, ["threadAAA000", "other"])
        self.assertEqual(len(scope["forgetting_targets"]), 1)
        t = scope["forgetting_targets"][0]
        self.assertEqual(t["target"], "docs/design-docs/foo.md")
        self.assertIn("caching", t["routed_snippet"])

    def test_provenance_scope_ignores_non_dropped_threads(self):
        self._journal_block("keepKEEP000", "x", "docs/design-docs/foo.md")
        scope = ds.build_provenance_scope(self.root, ["dropDROP000"])
        self.assertEqual(scope["forgetting_targets"], [])

    def test_forgetting_pass_retracts_attributable_line(self):
        # the journal attributes foo.md's line to a now-dropped thread -> the agent
        # proposes a retract -> M1 DELETEs it (attributable via the same provenance).
        line = "- 2026-01-01: routed claim about caching — because."
        self._journal_block("dropDROP000", "routed claim about caching",
                            "docs/design-docs/foo.md", line=line)
        plan = _json.dumps({"plan": [{"target": "docs/design-docs/foo.md",
            "kind": "retract", "change": {"op": "retract", "line": line},
            "risk": "mechanical"}]})
        res = ds.forgetting_pass(self.root, ["dropDROP000"],
                                 spawn=lambda p, m, cwd, timeout: plan,
                                 now=NOW, run_check=GREEN)
        self.assertEqual(len(res["applied"]), 1)
        self.assertEqual(res["forgetting_targets"], 1)
        self.assertNotIn("routed claim about caching", self._foo())

    def test_forgetting_pass_noop_without_provenance(self):
        def boom(*a, **k):
            raise AssertionError("must not spawn the agent when nothing was routed")
        res = ds.forgetting_pass(self.root, ["nobodyNO000"], spawn=boom, now=NOW,
                                 run_check=GREEN)
        self.assertEqual(res["forgetting_targets"], 0)
        self.assertEqual(res["applied"], [])


# ---- M6 review hardening: adversarial attempts on the safety crux -----------

class TestAdversarial(_Case):
    def _journal(self, body):
        (self.root / "docs" / "journal" / "2026-06.md").write_text(body, encoding="utf-8")

    def test_retract_human_tail_line_not_attributable(self):
        # P1-B: a human appends a caveat to a routed line. The journal recorded the
        # ORIGINAL line's @<hash>, so the edited (tailed) line hashes differently →
        # attribution fails → the delete is reported, the human caveat is kept.
        original = "- 2026-01-01: keep SQLite for the audit log — durability"
        tailed = original + "; BUT we may revisit this, see incident #88"
        self.foo.write_text("---\nstatus: draft\n---\n# Foo\n\n## Decision log\n\n"
                            + tailed + "\n", encoding="utf-8")
        self._journal('## r — dream run (sessions: s1aaaaaa)\n'
                      '- [routed] decision "keep SQLite for the audit log" '
                      '-> docs/design-docs/foo.md @' + self._hash(original) + '\n')
        res = self._apply([{"target": "docs/design-docs/foo.md", "kind": "retract",
                            "change": {"op": "retract", "line": tailed}}])
        self.assertEqual(res["applied"], [])
        self.assertIn("incident #88", self.foo.read_text())          # human caveat kept

    def test_retract_exact_hash_attributable_line_applies(self):
        # the legitimate case: the journal's @<hash> is of THIS exact line → reversible.
        line = "- 2026-01-01: routed claim about caching — because."
        self._journal('## r — dream run (sessions: s1aaaaaa)\n'
                      '- [routed] decision "routed claim about caching" '
                      '-> docs/design-docs/foo.md @' + self._hash(line) + '\n')
        res = self._apply([{"target": "docs/design-docs/foo.md", "kind": "retract",
                            "change": {"op": "retract", "line": line}}])
        self.assertEqual(len(res["applied"]), 1)

    def test_retract_no_hash_provenance_reports(self):
        # an old-format or dedupe [routed] line (no @<hash>) can't attribute a delete.
        line = "- 2026-01-01: routed claim about caching — because."
        self._journal('## r — dream run (sessions: s1aaaaaa)\n'
                      '- [routed] decision "routed claim about caching" '
                      '-> docs/design-docs/foo.md\n')
        res = self._apply([{"target": "docs/design-docs/foo.md", "kind": "retract",
                            "change": {"op": "retract", "line": line}}])
        self.assertEqual(res["applied"], [])
        self.assertIn("provenance", res["report"][0]["reason"])
        self.assertIn("routed claim about caching", self._foo())     # kept

    def test_rename_prose_with_structure_not_in_scope_rejected(self):
        # P1-A: "self-contained" is symbol-SHAPED (a hyphen) but is NOT a changed code
        # symbol — grounding in the change scope rejects it, so prose is never swept.
        self.foo.write_text("---\nstatus: draft\n---\n# Foo\n\n"
                            "The store is self-contained, fully self-contained.\n",
                            encoding="utf-8")
        before = self._foo()
        res = self._apply([{"target": "docs/design-docs/foo.md", "risk": "mechanical",
                            "change": {"op": "rename", "old": "self-contained",
                                       "new": "BROKEN"}}],
                          changed_symbols={"some_other_symbol"})
        self.assertEqual(res["applied"], [])
        self.assertIn("grounded in the change scope", res["report"][0]["reason"])
        self.assertEqual(self._foo(), before)                        # prose untouched

    def test_rename_capitalized_word_not_in_scope_rejected(self):
        # P1-A: a sentence-initial word ("The") is not a changed symbol → report.
        before = self._foo()
        res = self._apply([{"target": "docs/design-docs/foo.md", "risk": "mechanical",
                            "change": {"op": "rename", "old": "The", "new": "X"}}],
                          changed_symbols={"feeder_sessionstart"})
        self.assertEqual(res["applied"], [])
        self.assertEqual(self._foo(), before)

    def test_rename_grounded_symbol_applies(self):
        # the legitimate case: `old` IS a symbol that changed in the diff.
        res = self._apply([{"target": "docs/design-docs/foo.md", "risk": "mechanical",
                            "change": {"op": "rename", "old": "feeder_sessionstart",
                                       "new": "feeder_start"}}],
                          changed_symbols={"feeder_sessionstart"})
        self.assertEqual(len(res["applied"]), 1)
        self.assertIn("feeder_start hook compiles", self._foo())

    def test_regenerate_symlinked_target_refused(self):
        with tempfile.TemporaryDirectory() as out:
            decoy = Path(out) / "evil.md"
            decoy.write_text("# outside\n", encoding="utf-8")
            gen = self.root / "docs" / "generated"
            gen.mkdir(parents=True, exist_ok=True)
            os.symlink(decoy, gen / "component-inventory.md")
            res = ds.apply_plan(
                self.root, [{"target": "docs/generated/component-inventory.md",
                             "change": {"op": "regenerate"}}],
                NOW, run_check=GREEN, run_generator=lambda r, t: True)
            self.assertEqual(res["applied"], [])
            self.assertIn("symlink guard", res["report"][0]["reason"])
            self.assertEqual(decoy.read_text(), "# outside\n")       # not regenerated


# ---- M6 review hardening: input robustness (the gate must degrade, not crash) ---

class TestRobustness(_Case):
    def test_non_dict_plan_items_reported_not_crash(self):
        # a malformed plan with bare-value items must not raise — each is reported.
        res = self._apply(["notadict", None, 5,
                           {"target": "docs/design-docs/foo.md",
                            "change": {"op": "set_frontmatter", "field": "status",
                                       "value": "stable"}}])
        self.assertEqual(len(res["applied"]), 1)             # the one real item applied
        self.assertEqual(len(res["report"]), 3)              # the 3 non-objects reported
        self.assertTrue(all("not an object" in r["reason"] for r in res["report"]))

    def test_parse_plan_robust_to_preamble_trailing_and_siblings(self):
        # a preamble object, the real plan, then trailing brace-bearing prose.
        out = ('{"note":"scanning"}\n'
               '{"plan":[{"target":"docs/x.md","kind":"outdated"}]}\nDone. {trailing}')
        self.assertEqual(ds.parse_maintenance_plan(out),
                         [{"target": "docs/x.md", "kind": "outdated"}])

    def test_run_degrades_on_unparseable_audit(self):
        # the audit agent returns prose with no plan object → run() reports, never raises.
        res = ds.run(self.root, scope={"changed_symbols": [{"symbol": "x"}]},
                     spawn=lambda p, m, cwd, timeout: "Found nothing useful. {oops}",
                     now=NOW, run_check=GREEN)
        self.assertEqual(res["applied"], [])
        self.assertEqual(res["plan"], [])
        self.assertIn("unparseable", res["report"][0]["reason"])

    def test_regenerate_writes_then_fails_restores_tree(self):
        # a generator that writes its target then returns failure must NOT leave the
        # tree dirty — the pre-edit snapshot is restored.
        out = self.root / "docs" / "generated" / "component-inventory.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("# original inventory\n", encoding="utf-8")

        def bad_gen(root, target):
            out.write_text("# GARBAGE half-written\n", encoding="utf-8")
            return False                                     # wrote, then failed
        res = self._apply([{"target": "docs/generated/component-inventory.md",
                            "change": {"op": "regenerate"}}], run_generator=bad_gen)
        self.assertEqual(res["applied"], [])
        self.assertFalse(res["rolled_back"])
        self.assertEqual(out.read_text(), "# original inventory\n")   # restored

    def test_run_check_timeout_counts_as_red(self):
        import subprocess as _sp
        real = _sp.run

        def fake_run(*a, **k):
            raise _sp.TimeoutExpired(cmd="check.py", timeout=1)
        _sp.run = fake_run
        try:
            self.assertFalse(ds.run_check(self.root))        # timeout → RED, no raise
        finally:
            _sp.run = real


if __name__ == "__main__":
    unittest.main()
