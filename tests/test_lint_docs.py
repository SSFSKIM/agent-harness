import json, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import lint_docs
from fixtures import fm, make_repo, make_plugin


def run_all(root, plugin=None):
    host = lint_docs.hl.exempt_roots(root)  # mirror main()'s host-aware path
    cfg = lint_docs.hl.gate_config(root)
    stale_days = lint_docs._int_or(cfg.get("stale_days"), lint_docs.STALE_DAYS)
    errors = []
    lint_docs.check_entrypoints(root, errors)
    lint_docs.check_frontmatter(root, errors, host, stale_days, cfg)
    lint_docs.check_links(root, errors, host, cfg)
    lint_docs.check_naming(root, errors, host, cfg)
    lint_docs.check_indexes(root, errors, cfg)
    if plugin is not None:
        lint_docs.check_coverage(root, errors, plugin, cfg)
    return errors


def write_cfg(root, **cfg):
    (root / ".harness.json").write_text(json.dumps(cfg), encoding="utf-8")


class TestLintDocs(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_valid_repo_is_green(self):
        self.assertEqual(run_all(self.root), [])

    def test_d1_agents_md_over_limit(self):
        (self.root / "AGENTS.md").write_text("x\n" * 1000)
        errs = run_all(self.root)
        self.assertFalse(any("D1" in e for e in errs), errs)

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

    def test_d4_list_valued_last_verified_fails_gracefully(self):
        # a required key authored as a YAML list — the list-aware parser returns a
        # list, and D4 must degrade to a clean FAIL, never crash the gate (TypeError).
        p = self.root / "docs" / "design-docs" / "core-beliefs.md"
        p.write_text("---\nstatus: stable\nlast_verified: [2026-06-18]\nowner: a\n---\n# x\n")
        errs = run_all(self.root)  # must not raise
        self.assertTrue(any("D4" in e and "bad last_verified" in e for e in errs), errs)

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

    def test_memory_bootloader_has_no_line_cap(self):
        mem = self.root / "docs" / "memory"
        mem.mkdir(parents=True)
        (mem / "MEMORY.md").write_text("x\n" * 1000)
        errs = run_all(self.root)
        self.assertFalse(any("D7" in e and "MEMORY.md" in e for e in errs), errs)

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

    def test_product_specs_governed_by_default_on_ported_hosts(self):
        prod = self.root / "docs" / "product-specs"
        prod.mkdir()
        (prod / "Feature Brief.md").write_text("# product intent without convention\n")
        errs = run_all(self.root)
        self.assertTrue(any("product-specs" in e and "D3" in e for e in errs), errs)
        self.assertTrue(any("product-specs" in e and "D6" in e for e in errs), errs)

    def test_product_specs_needs_index_when_pages_exist(self):
        prod = self.root / "docs" / "product-specs"
        prod.mkdir()
        (prod / "feature-brief.md").write_text(fm() + "# product intent\n")
        errs = run_all(self.root)
        self.assertTrue(any("product-specs" in e and "D8" in e for e in errs), errs)

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
        write_cfg(self.root, doc_governance="strict")
        biz = self.root / "docs" / "business"
        biz.mkdir()
        (biz / "VC_Report (시장).md").write_text("# no fm, bad name\n" + "x\n" * 500)
        self.assertTrue(run_all(self.root))  # fails D3/D6 before declaring
        self._legacy("business/")
        errs = run_all(self.root)
        self.assertFalse(any(r in e for e in errs for r in ("D3", "D6", "D7")), errs)

    def test_harnessignore_exempts_single_file(self):
        write_cfg(self.root, doc_governance="strict")
        (self.root / "docs" / "README.md").write_text("# legacy root doc, no fm\n")
        self._legacy("README.md")
        self.assertFalse(any("D3" in e for e in run_all(self.root)))

    def test_harnessignore_does_not_exempt_unlisted_managed_doc(self):
        d = self.root / "docs" / "memory" / "knowledge"
        d.mkdir(parents=True)
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

    def test_harnessignore_cannot_exempt_product_specs(self):
        prod = self.root / "docs" / "product-specs"
        prod.mkdir()
        (prod / "loose.md").write_text("# no frontmatter\n")
        self._legacy("product-specs/")
        self.assertTrue(any("product-specs" in e and "D3" in e
                            for e in run_all(self.root)))

    def test_harnessignore_slashless_entry_is_segment_matched(self):
        write_cfg(self.root, doc_governance="strict")
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

    def test_project_specific_docs_are_flexible_by_default_on_ported_hosts(self):
        biz = self.root / "docs" / "business"
        biz.mkdir()
        (biz / "VC_Report (시장).md").write_text(
            "# project-owned doc, no harness frontmatter\n" + "x\n" * 500)
        errs = run_all(self.root)
        self.assertFalse(any("business" in e and r in e
                             for e in errs for r in ("D3", "D6", "D7")), errs)

    def test_host_can_opt_project_specific_root_into_governance(self):
        write_cfg(self.root, managed_doc_roots=["business/"])
        biz = self.root / "docs" / "business"
        biz.mkdir()
        (biz / "VC_Report (시장).md").write_text("# no fm, bad name\n")
        errs = run_all(self.root)
        self.assertTrue(any("business" in e and "D3" in e for e in errs), errs)
        self.assertTrue(any("business" in e and "D6" in e for e in errs), errs)

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

    def test_agents_md_line_count_is_not_governed_by_config(self):
        (self.root / "AGENTS.md").write_text("x\n" * 200)
        write_cfg(self.root, size_limits={"AGENTS.md": 1})
        errs = run_all(self.root)
        self.assertFalse(any("D1" in e for e in errs), errs)

    def test_governed_docs_have_no_default_line_cap(self):
        big = self.root / "docs" / "design-docs" / "big.md"
        big.write_text(fm() + "x\n" * 1000)
        write_cfg(self.root, default_size_limit=1)
        errs = run_all(self.root)
        self.assertFalse(any("D7" in e for e in errs), errs)

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

    def test_managed_docs_have_no_line_cap(self):
        (self.root / "docs" / "SECURITY.md").write_text(fm() + "x\n" * 500)
        (self.root / "docs" / "notes.md").write_text(fm() + "x\n" * 500)
        write_cfg(self.root, default_size_limit=1, size_limits={"SECURITY.md": 1})
        errs = run_all(self.root)
        self.assertFalse(any("D7" in e for e in errs), errs)

    def test_stale_override_cannot_loosen_managed_doc(self):
        import datetime
        d45 = (datetime.date.today() - datetime.timedelta(days=45)).isoformat()
        (self.root / "docs" / "SECURITY.md").write_text(fm(last_verified=d45) + "# x\n")
        errs = []
        lint_docs.check_frontmatter(self.root, errs, (), 9999)  # try to loosen
        self.assertTrue(any("D4" in e and "SECURITY.md" in e for e in errs), errs)

    def test_memory_bootloader_config_size_limit_is_ignored(self):
        mem = self.root / "docs" / "memory"
        mem.mkdir(parents=True)
        (mem / "MEMORY.md").write_text("x\n" * 200)
        write_cfg(self.root, size_limits={"MEMORY.md": 1})
        errs = run_all(self.root)
        self.assertFalse(any("D7" in e for e in errs), errs)

    def test_d9_superpowers_mention_does_not_count(self):
        plugin = make_plugin(self.root)
        sk = plugin / "skills" / "mystery"
        sk.mkdir()
        (sk / "SKILL.md").write_text("---\nname: mystery\ndescription: d\n---\n")
        sp = self.root / "docs" / "superpowers" / "plans"
        sp.mkdir(parents=True)
        (sp / "plan.md").write_text("mentions mystery here\n")
        self.assertTrue(any("D9" in e for e in run_all(self.root, plugin)))

    def test_d9_skips_external_plugin_on_ported_host_by_default(self):
        with tempfile.TemporaryDirectory() as d:
            plugin = make_plugin(Path(d))
            sk = plugin / "skills" / "mystery"
            sk.mkdir()
            (sk / "SKILL.md").write_text("---\nname: mystery\ndescription: d\n---\n")
            self.assertFalse(any("D9" in e for e in run_all(self.root, plugin)))

    def test_d9_can_be_strict_on_ported_host_when_opted_in(self):
        write_cfg(self.root, component_coverage="strict")
        with tempfile.TemporaryDirectory() as d:
            plugin = make_plugin(Path(d))
            sk = plugin / "skills" / "mystery"
            sk.mkdir()
            (sk / "SKILL.md").write_text("---\nname: mystery\ndescription: d\n---\n")
            self.assertTrue(any("D9" in e for e in run_all(self.root, plugin)))


if __name__ == "__main__":
    unittest.main()
