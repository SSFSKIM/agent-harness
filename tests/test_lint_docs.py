import sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import lint_docs
from fixtures import fm, make_repo, make_plugin


def run_all(root, plugin=None):
    host = lint_docs.hl.exempt_roots(root)  # mirror main()'s host-aware path
    errors = []
    lint_docs.check_entrypoints(root, errors)
    lint_docs.check_frontmatter(root, errors, host)
    lint_docs.check_links(root, errors, host)
    lint_docs.check_naming(root, errors, host)
    lint_docs.check_sizes(root, errors, host)
    lint_docs.check_indexes(root, errors)
    if plugin is not None:
        lint_docs.check_coverage(root, errors, plugin)
    return errors


class TestLintDocs(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_valid_repo_is_green(self):
        self.assertEqual(run_all(self.root), [])

    def test_d1_agents_md_over_limit(self):
        (self.root / "AGENTS.md").write_text("x\n" * 121)
        errs = run_all(self.root)
        self.assertTrue(any("D1" in e and "FIX:" in e for e in errs))

    def test_d3_missing_frontmatter(self):
        (self.root / "docs" / "design-docs" / "core-beliefs.md").write_text("# no fm\n")
        errs = run_all(self.root)
        self.assertTrue(any("D3" in e for e in errs))

    def test_d4_stale_fails_but_archived_exempt(self):
        p = self.root / "docs" / "design-docs" / "core-beliefs.md"
        p.write_text(fm(last_verified="2020-01-01") + "# old\n")
        self.assertTrue(any("D4" in e for e in run_all(self.root)))
        p.write_text(fm(status="archived", last_verified="2020-01-01") + "# old\n")
        self.assertFalse(any("D4" in e for e in run_all(self.root)))

    def test_d10_machine_docs_missing(self):
        errs = []
        lint_docs.check_machine_refs(self.root, errs)
        self.assertTrue(any("D10" in e and "docs/PLANS.md" in e for e in errs))

    def test_d5_broken_link(self):
        (self.root / "AGENTS.md").write_text("[gone](docs/nope.md)\n")
        self.assertTrue(any("D5" in e for e in run_all(self.root)))

    def test_d6_bad_filename(self):
        bad = self.root / "docs" / "design-docs" / "Bad_Name.md"
        bad.write_text(fm() + "# x\n")
        idx = self.root / "docs" / "design-docs" / "index.md"
        idx.write_text(fm() + "# Index\n- core-beliefs.md\n- Bad_Name.md\n")
        self.assertTrue(any("D6" in e for e in run_all(self.root)))

    def test_d7_memory_bootloader_size(self):
        mem = self.root / "docs" / "memory"
        mem.mkdir(parents=True)
        (mem / "MEMORY.md").write_text("x\n" * 61)
        self.assertTrue(any("D7" in e and "MEMORY.md" in e for e in run_all(self.root)))

    def test_d8_unregistered_page(self):
        extra = self.root / "docs" / "design-docs" / "loose-page.md"
        extra.write_text(fm() + "# loose\n")
        self.assertTrue(any("D8" in e for e in run_all(self.root)))

    def test_d5_exempt_dirs_not_link_checked(self):
        sp = self.root / "docs" / "superpowers" / "plans"
        sp.mkdir(parents=True)
        (sp / "plan.md").write_text("[fake example](docs/nope.md)\n")
        self.assertFalse(any("D5" in e for e in run_all(self.root)))

    def test_d8_empty_category_needs_no_index(self):
        (self.root / "docs" / "product-specs").mkdir()
        self.assertFalse(any("D8" in e for e in run_all(self.root)))

    def test_d9_undocumented_component(self):
        plugin = make_plugin(self.root)
        sk = plugin / "skills" / "mystery"
        sk.mkdir()
        (sk / "SKILL.md").write_text("---\nname: mystery\ndescription: d\n---\n")
        self.assertTrue(any("D9" in e and "mystery" in e for e in run_all(self.root, plugin)))

    def test_d5_anchored_broken_link_fails(self):
        (self.root / "AGENTS.md").write_text("[gone](docs/nope.md#section)\n")
        self.assertTrue(any("D5" in e for e in run_all(self.root)))

    def test_d5_anchored_valid_link_passes(self):
        (self.root / "AGENTS.md").write_text(
            "[ok](docs/design-docs/core-beliefs.md#golden-rules)\n")
        self.assertFalse(any("D5" in e for e in run_all(self.root)))

    def _legacy(self, *lines):
        (self.root / "docs" / ".harnessignore").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")

    def test_harnessignore_exempts_legacy_subtree(self):
        biz = self.root / "docs" / "business"
        biz.mkdir()
        (biz / "VC_Report (시장).md").write_text("# no fm, bad name\n" + "x\n" * 500)
        self.assertTrue(run_all(self.root))  # fails D3/D6/D7 before declaring
        self._legacy("business/")
        errs = run_all(self.root)
        self.assertFalse(any(r in e for e in errs for r in ("D3", "D6", "D7")), errs)

    def test_harnessignore_exempts_single_file(self):
        (self.root / "docs" / "README.md").write_text("# legacy root doc, no fm\n")
        self._legacy("README.md")
        self.assertFalse(any("D3" in e for e in run_all(self.root)))

    def test_harnessignore_does_not_exempt_unlisted_doc(self):
        d = self.root / "docs" / "notes"
        d.mkdir()
        (d / "loose.md").write_text("# no frontmatter\n")
        self._legacy("business/")  # declares a DIFFERENT root
        self.assertTrue(any("D3" in e for e in run_all(self.root)))

    def test_harnessignore_cannot_exempt_managed_tree(self):
        # a host listing the memory tree must not un-govern it (security)
        bad = self.root / "docs" / "memory" / "knowledge"
        bad.mkdir(parents=True)
        (bad / "loose.md").write_text("# no frontmatter\n")
        self._legacy("memory/")
        self.assertTrue(any("D3" in e for e in run_all(self.root)))

    def test_harnessignore_slashless_entry_is_segment_matched(self):
        # `business` (no slash) exempts the business/ tree but NOT a sibling
        # `business-plan.md` — segment boundary, not bare substring (arch P1).
        biz = self.root / "docs" / "business"
        biz.mkdir()
        (biz / "in-tree.md").write_text("# no fm\n")
        (self.root / "docs" / "business-plan.md").write_text("# no fm sibling\n")
        self._legacy("business")  # deliberately omit the trailing slash
        errs = run_all(self.root)
        self.assertFalse(any("business/in-tree.md" in e for e in errs), errs)
        self.assertTrue(any("business-plan.md" in e and "D3" in e for e in errs), errs)

    def test_harnessignore_partial_prefix_cannot_bypass_managed_guard(self):
        # `mem` must not reach `memory/…` (security P1 — the poisoning vector).
        bad = self.root / "docs" / "memory" / "knowledge"
        bad.mkdir(parents=True)
        (bad / "poison.md").write_text("# no frontmatter\n")
        self._legacy("mem")
        self.assertTrue(any("D3" in e for e in run_all(self.root)))

    def test_harnessignore_cannot_exempt_top_level_machine_doc(self):
        # SECURITY.md / DESIGN.md etc. (persona grounding docs) are non-exemptable.
        (self.root / "docs" / "SECURITY.md").write_text("# no frontmatter\n")
        self._legacy("SECURITY.md")
        self.assertTrue(any("D3" in e and "SECURITY.md" in e
                            for e in run_all(self.root)))

    def test_harnessignore_drop_guard_normalizes_dotslash(self):
        # `./memory` must be dropped by the guard itself (both layers agree),
        # not merely rendered inert by _exempt.
        self._legacy("./memory", "memory//knowledge", "business/")
        self.assertEqual(lint_docs.hl.exempt_roots(self.root), ("business",))

    def test_d1_threshold_overridable_per_repo(self):
        # our 120-line default is a default, not a mandate: a host whose map
        # legitimately runs long raises the cap via .harness.json size_limits.
        (self.root / "AGENTS.md").write_text("x\n" * 200)
        errs = []
        lint_docs.check_entrypoints(self.root, errs)
        self.assertTrue(any("D1" in e for e in errs))            # default 120 → fail
        errs = []
        lint_docs.check_entrypoints(self.root, errs, {"AGENTS.md": 300})
        self.assertFalse(any("D1" in e for e in errs))           # override 300 → pass

    def test_d7_default_size_overridable_per_repo(self):
        big = self.root / "docs" / "design-docs" / "big.md"
        big.write_text(fm() + "x\n" * 500)
        errs = []
        lint_docs.check_sizes(self.root, errs)
        self.assertTrue(any("D7" in e for e in errs))            # default 400 → fail
        errs = []
        lint_docs.check_sizes(self.root, errs, (), None, 600)
        self.assertFalse(any("D7" in e for e in errs))           # default_limit 600 → pass

    def test_d4_stale_window_overridable_per_repo(self):
        import datetime
        d45 = (datetime.date.today() - datetime.timedelta(days=45)).isoformat()
        p = self.root / "docs" / "design-docs" / "core-beliefs.md"
        p.write_text(fm(last_verified=d45) + "# x\n")
        errs = []
        lint_docs.check_frontmatter(self.root, errs)
        self.assertTrue(any("D4" in e for e in errs))            # 30-day default → stale
        errs = []
        lint_docs.check_frontmatter(self.root, errs, (), 60)
        self.assertFalse(any("D4" in e for e in errs))           # 60-day window → fresh

    def test_int_or_rejects_bool_and_nonint(self):
        # a malformed override (JSON `true`, a string) falls back to the default,
        # never crashing or silently coercing — parse-don't-validate at the seam.
        self.assertEqual(lint_docs._int_or(True, 30), 30)
        self.assertEqual(lint_docs._int_or("60", 30), 30)
        self.assertEqual(lint_docs._int_or(60, 30), 60)

    def test_size_override_cannot_loosen_managed_doc(self):
        # security T9: a host override may TIGHTEN a managed doc but never loosen
        # it — SECURITY.md stays capped at the harness default despite a huge
        # default_size_limit, while a non-managed doc IS loosened by the same.
        (self.root / "docs" / "SECURITY.md").write_text(fm() + "x\n" * 500)
        (self.root / "docs" / "notes.md").write_text(fm() + "x\n" * 500)
        errs = []
        lint_docs.check_sizes(self.root, errs, (), None, 9999)
        self.assertTrue(any("D7" in e and "SECURITY.md" in e for e in errs), errs)
        self.assertFalse(any("D7" in e and "notes.md" in e for e in errs), errs)

    def test_stale_override_cannot_loosen_managed_doc(self):
        import datetime
        d45 = (datetime.date.today() - datetime.timedelta(days=45)).isoformat()
        (self.root / "docs" / "SECURITY.md").write_text(fm(last_verified=d45) + "# x\n")
        errs = []
        lint_docs.check_frontmatter(self.root, errs, (), 9999)  # try to loosen
        self.assertTrue(any("D4" in e and "SECURITY.md" in e for e in errs), errs)

    def test_d9_superpowers_mention_does_not_count(self):
        plugin = make_plugin(self.root)
        sk = plugin / "skills" / "mystery"
        sk.mkdir()
        (sk / "SKILL.md").write_text("---\nname: mystery\ndescription: d\n---\n")
        sp = self.root / "docs" / "superpowers" / "plans"
        sp.mkdir(parents=True)
        (sp / "plan.md").write_text("mentions mystery here\n")
        self.assertTrue(any("D9" in e for e in run_all(self.root, plugin)))


if __name__ == "__main__":
    unittest.main()
