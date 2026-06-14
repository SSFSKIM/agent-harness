import json
import os
import sys
import unittest
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import dream_router as dr
import memories_db as mdb

NOW = 1_700_000_000
DAY = 86400


class _Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "docs" / "design-docs").mkdir(parents=True)
        (self.root / "docs" / "exec-plans").mkdir(parents=True)
        (self.root / "docs" / "design-docs" / "foo.md").write_text(
            "---\nstatus: draft\n---\n# Foo\n\n## Decision log\n\n"
            "- 2026-01-01: existing — because.\n\n## Open decisions\n\n"
            "- existing question\n", encoding="utf-8")
        (self.root / "docs" / "exec-plans" / "tech-debt-tracker.md").write_text(
            "# Tech debt\n\n| desc | sev | date | source | status |\n"
            "|---|---|---|---|---|\n", encoding="utf-8")
        self.conn = mdb.connect(self.root)
        self.addCleanup(self.conn.close)

    def _tracker(self):
        return (self.root / "docs/exec-plans/tech-debt-tracker.md").read_text()

    def _foo(self):
        return (self.root / "docs/design-docs/foo.md").read_text()

    def _journal(self):
        p = dr.journal_path(self.root, NOW)
        return p.read_text() if p.exists() else ""

    def _rows(self, *tids):
        return [{"thread_id": t, "source_updated_at": NOW} for t in (tids or ("s",))]

    def _seed(self, tid="s1"):
        mdb.upsert_stage1_output(self.conn, tid, NOW - DAY, "raw memory text",
                                 "summary", "slug", NOW)


class TestParse(_Case):
    def test_extracts_from_fenced_or_prose(self):
        ops = dr.parse_routing_plan(
            'Here is the plan:\n{"operations":[{"kind":"journal","text":"hi"}]}\n')
        self.assertEqual(ops, [{"kind": "journal", "text": "hi"}])

    def test_keeps_all_dict_ops_drops_non_dicts(self):
        # unknown kinds are KEPT (journaled downstream, never silently dropped);
        # only non-dict entries are discarded.
        ops = dr.parse_routing_plan(json.dumps(
            {"operations": [{"kind": "bogus"}, {"kind": "journal", "text": "x"},
                            "notadict"]}))
        self.assertEqual([o["kind"] for o in ops], ["bogus", "journal"])

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            dr.parse_routing_plan("   ")

    def test_no_operations_list_raises(self):
        with self.assertRaises(ValueError):
            dr.parse_routing_plan('{"foo": 1}')


class TestApply(_Case):
    def test_tracker_row_appended_with_provenance(self):
        ops = [{"kind": "tracker_row", "desc": "scope check holds whole repo in memory",
                "severity": "Minor", "source": "s1"}]
        summ = dr.apply_plan(self.root, ops, self._rows("s1"), NOW)
        self.assertEqual(summ["applied"]["tracker_row"], 1)
        self.assertIn("scope check holds whole repo in memory", self._tracker())
        self.assertIn("| Minor |", self._tracker())
        self.assertIn("[routed] debt", self._journal())

    def test_design_decision_inserted_in_decision_log(self):
        ops = [{"kind": "design_decision", "target": "docs/design-docs/foo.md",
                "decision": "use --no-renames", "why": "forgetting must stay a Delete",
                "source": "s"}]
        dr.apply_plan(self.root, ops, self._rows(), NOW)
        foo = self._foo()
        self.assertIn("use --no-renames — forgetting must stay a Delete", foo)
        self.assertLess(foo.index("use --no-renames"), foo.index("## Open decisions"))

    def test_open_question_inserted(self):
        ops = [{"kind": "design_openq", "target": "docs/design-docs/foo.md",
                "question": "should the ledger rotate weekly?", "source": "s"}]
        dr.apply_plan(self.root, ops, self._rows(), NOW)
        self.assertIn("should the ledger rotate weekly?", self._foo())

    def test_bad_design_target_demoted_to_journal(self):
        ops = [{"kind": "design_decision", "target": "docs/../etc/passwd",
                "decision": "x", "why": "y", "source": "s"}]
        summ = dr.apply_plan(self.root, ops, self._rows(), NOW)
        self.assertEqual(summ["applied"]["rejected"], 1)
        self.assertEqual(summ["applied"]["design_decision"], 0)
        self.assertIn("[held] design_decision (bad target", self._journal())

    def test_target_outside_designdocs_rejected(self):
        ops = [{"kind": "design_decision",
                "target": "docs/exec-plans/tech-debt-tracker.md",
                "decision": "x", "why": "y", "source": "s"}]
        summ = dr.apply_plan(self.root, ops, self._rows(), NOW)
        self.assertEqual(summ["applied"]["rejected"], 1)

    def test_journal_is_the_default_home(self):
        ops = [{"kind": "journal", "text": "spent 3h on git rename detection",
                "source": "s"}]
        dr.apply_plan(self.root, ops, self._rows(), NOW)
        self.assertIn("[held] spent 3h on git rename detection", self._journal())

    def test_dedupe_no_duplicate_row(self):
        ops = [{"kind": "tracker_row", "desc": "same debt item",
                "severity": "Minor", "source": "s"}]
        dr.apply_plan(self.root, ops, self._rows(), NOW)
        dr.apply_plan(self.root, ops, self._rows(), NOW)
        self.assertEqual(self._tracker().count("same debt item"), 1)

    def test_pipe_escaped_keeps_table_shape(self):
        ops = [{"kind": "tracker_row", "desc": "a | b | c", "severity": "Minor",
                "source": "s"}]
        dr.apply_plan(self.root, ops, self._rows(), NOW)
        row = [l for l in self._tracker().splitlines() if "a / b / c" in l][0]
        self.assertEqual(row.count("|"), 6)            # 5 columns

    def test_unknown_kind_is_journaled_not_dropped(self):
        ops = dr.parse_routing_plan(json.dumps({"operations": [
            {"kind": "design_decison", "decision": "typod kind", "source": "s"}]}))
        self.assertEqual(len(ops), 1)                  # kept, not filtered out
        summ = dr.apply_plan(self.root, ops, self._rows(), NOW)
        self.assertIn("typod kind", self._journal())   # journaled as held
        self.assertEqual(summ["applied"]["journal"], 1)

    def test_symlinked_tracker_is_not_written_through(self):
        with tempfile.TemporaryDirectory() as out:
            decoy = Path(out) / "evil-tracker.md"
            decoy.write_text("# outside\n", encoding="utf-8")
            tracker = self.root / "docs/exec-plans/tech-debt-tracker.md"
            tracker.unlink()
            os.symlink(decoy, tracker)                 # allowlist file → outside
            ops = [{"kind": "tracker_row", "desc": "pwn", "severity": "Minor",
                    "source": "s"}]
            summ = dr.apply_plan(self.root, ops, self._rows(), NOW)
            self.assertEqual(summ["applied"]["tracker_row"], 0)   # refused
            self.assertNotIn("pwn", decoy.read_text(encoding="utf-8"))

    def test_journal_strips_redundant_tag(self):
        ops = [{"kind": "journal", "text": "[held] already tagged note", "source": "s"}]
        dr.apply_plan(self.root, ops, self._rows(), NOW)
        j = self._journal()
        self.assertIn("[held] already tagged note", j)
        self.assertNotIn("[held] [held]", j)

    def test_secret_redacted_before_write(self):
        ops = [{"kind": "journal",
                "text": "token sk-ant-abcdefghijklmnopqrstuvwxyz0123", "source": "s"}]
        dr.apply_plan(self.root, ops, self._rows(), NOW)
        self.assertNotIn("sk-ant-abcdefghijklmnopqrstuvwxyz0123", self._journal())
        self.assertIn("[REDACTED_SECRET]", self._journal())


class TestConsolidate(_Case):
    def test_routes_and_marks_selected(self):
        self._seed("s1")
        plan = json.dumps({"operations": [
            {"kind": "tracker_row", "desc": "a real debt", "severity": "Minor",
             "source": "s1"}]})
        res = dr.consolidate(self.conn, self.root, NOW,
                             spawn=lambda prompt, model, cwd: plan)
        self.assertEqual(res["status"], "routed")
        self.assertIn("s1", res["selected"])
        self.assertIn("a real debt", self._tracker())
        row = self.conn.execute(
            "SELECT selected_for_phase2 FROM stage1_outputs WHERE thread_id='s1'"
        ).fetchone()
        self.assertEqual(row["selected_for_phase2"], 1)

    def test_empty_when_no_rows(self):
        res = dr.consolidate(self.conn, self.root, NOW, spawn=lambda *a, **k: "{}")
        self.assertEqual(res["status"], "empty")

    def test_skipped_when_lock_held(self):
        mdb.claim_phase2(self.conn, "other", 1800, NOW)
        self._seed()
        res = dr.consolidate(self.conn, self.root, NOW, spawn=lambda *a, **k: "{}")
        self.assertEqual(res["status"], "skipped")

    def test_failed_on_spawn_error_writes_nothing(self):
        self._seed()

        def boom(*a, **k):
            raise RuntimeError("model down")
        res = dr.consolidate(self.conn, self.root, NOW, spawn=boom)
        self.assertEqual(res["status"], "failed")
        self.assertEqual(self._journal(), "")


if __name__ == "__main__":
    unittest.main()
