import json, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import lint_docs
from fixtures import fm, make_repo, make_plugin, TODAY


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

    def test_d8_unregistered_page(self):
        extra = self.root / "docs" / "design-docs" / "loose-page.md"
        extra.write_text(fm() + "# loose\n")
        self.assertTrue(any("D8" in e for e in run_all(self.root)))

    def test_d5_exempt_dirs_not_link_checked(self):
        sp = self.root / "docs" / "superpowers" / "plans"
        sp.mkdir(parents=True)
        (sp / "plan.md").write_text("[fake example](docs/nope.md)\n")
        self.assertFalse(any("D5" in e for e in run_all(self.root)))

    def test_d5_broken_link_into_harnessignored_tree_is_external(self):
        # F8: a link whose TARGET is under a .harnessignore'd tree is EXTERNAL, not broken,
        # even when the target is absent (e.g. the vendored, .gitignored symphony-original
        # oracle missing from a fresh clone). The gate must pass on any clone/ported host.
        (self.root / "docs" / ".harnessignore").write_text("vendor/\n", encoding="utf-8")
        (self.root / "AGENTS.md").write_text("see the [oracle](docs/vendor/SPEC.md)\n")
        self.assertFalse(any("D5" in e for e in run_all(self.root)),
                         "link into a .harnessignore'd absent tree must not be a broken link")

    def test_d5_broken_link_into_unmanaged_path_still_fails(self):
        # Control: a broken link into a NON-exempt path still fails D5 (the guard is narrow).
        (self.root / "AGENTS.md").write_text("see [gone](docs/not-exempt/SPEC.md)\n")
        self.assertTrue(any("D5" in e for e in run_all(self.root)))

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

    def test_d13_unfilled_marker_warns_never_fails(self):
        p = self.root / "docs" / "design-docs" / "core-beliefs.md"
        p.write_text(fm() + "# Beliefs\n<!-- FILL: real content here -->\n")
        # D13 is non-blocking: it must NEVER appear in the FAIL/error path.
        self.assertFalse(any("D13" in e for e in run_all(self.root)), "D13 must not be a FAIL")
        warnings = []
        lint_docs.check_fill_markers(self.root, warnings)
        self.assertTrue(any("D13" in w and "core-beliefs.md" in w for w in warnings), warnings)

    def test_d13_prose_mention_of_marker_does_not_warn(self):
        # A doc that DOCUMENTS the marker must stay quiet, both forms: `<!-- FILL -->`
        # (no colon, as completed plans write it) AND the backtick-wrapped full form
        # `<!-- FILL: -->` (as KNOWLEDGE_FORMAT/the tracker write it — this exact case
        # false-fired a naive colon match). A real marker is a RAW HTML comment, never
        # backtick-wrapped; the negative lookbehind is the discriminator.
        p = self.root / "docs" / "design-docs" / "core-beliefs.md"
        p.write_text(fm() + "# Beliefs\nThe seed leaves a `<!-- FILL -->` placeholder,\n"
                     "documented as `<!-- FILL: instruction -->` in the format spec.\n")
        warnings = []
        lint_docs.check_fill_markers(self.root, warnings)
        self.assertEqual(warnings, [], warnings)

    def test_d13_scans_root_agents_and_architecture(self):
        (self.root / "AGENTS.md").write_text("# map\n<!-- FILL: what this repo is -->\n")
        (self.root / "ARCHITECTURE.md").write_text("# arch\n<!-- FILL: the codemap -->\n")
        warnings = []
        lint_docs.check_fill_markers(self.root, warnings)
        self.assertTrue(any("AGENTS.md" in w for w in warnings), warnings)
        self.assertTrue(any("ARCHITECTURE.md" in w for w in warnings), warnings)

    def test_d13_clean_repo_has_no_warnings(self):
        warnings = []
        lint_docs.check_fill_markers(self.root, warnings)
        self.assertEqual(warnings, [], warnings)

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
        d = self.root / "docs" / "adr"
        d.mkdir(parents=True)
        (d / "loose.md").write_text("# no frontmatter\n")
        self._legacy("business/")  # declares a DIFFERENT root
        self.assertTrue(any("D3" in e for e in run_all(self.root)))

    def test_harnessignore_cannot_exempt_managed_tree(self):
        # a host listing a managed tree (adr) must not un-govern it (security)
        bad = self.root / "docs" / "adr"
        bad.mkdir(parents=True)
        (bad / "loose.md").write_text("# no frontmatter\n")
        self._legacy("adr/")
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
        # `ad` must not reach `adr/…` (security P1 — the poisoning vector).
        bad = self.root / "docs" / "adr"
        bad.mkdir(parents=True)
        (bad / "poison.md").write_text("# no frontmatter\n")
        self._legacy("ad")
        self.assertTrue(any("D3" in e for e in run_all(self.root)))

    def test_harnessignore_cannot_exempt_top_level_machine_doc(self):
        # SECURITY.md / DESIGN.md etc. (persona grounding docs) are non-exemptable.
        (self.root / "docs" / "SECURITY.md").write_text("# no frontmatter\n")
        self._legacy("SECURITY.md")
        self.assertTrue(any("D3" in e and "SECURITY.md" in e
                            for e in run_all(self.root)))

    def test_harnessignore_drop_guard_normalizes_dotslash(self):
        # `./adr` must be dropped by the guard itself (both layers agree),
        # not merely rendered inert by _exempt.
        self._legacy("./adr", "adr//sub", "business/")
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


class TestLintNavKeys(unittest.TestCase):
    """KF v2.0 governance flip — D11 (required nav keys) + D12 (validate-if-present)."""
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def _dd(self, name, extra=""):
        """Write a valid-v2.0 design-doc page (+ extra frontmatter lines)."""
        p = self.root / "docs" / "design-docs" / name
        p.write_text(f"---\nstatus: draft\nlast_verified: {TODAY}\nowner: h\n"
                     f"type: design-doc\ndescription: d\n{extra}---\n# x\n")
        return p

    def test_d11_requires_type_and_description(self):
        # the fixture page is valid v2.0 -> no D11
        self.assertFalse(any("D11" in e for e in run_all(self.root)))
        p = self.root / "docs" / "design-docs" / "core-beliefs.md"
        p.write_text(fm(type="") + "# x\n")  # empty type
        self.assertTrue(any("D11" in e and "`type`" in e for e in run_all(self.root)))
        p.write_text(fm(description="") + "# x\n")  # empty description
        self.assertTrue(any("D11" in e and "`description`" in e for e in run_all(self.root)))

    def test_d11_index_spines_are_exempt(self):
        # an index.md with no type/description must NOT trip D11 (it is a listing)
        (self.root / "docs" / "design-docs" / "index.md").write_text(
            f"---\nstatus: draft\nlast_verified: {TODAY}\nowner: h\n---\n# I\n- core-beliefs.md\n")
        self.assertFalse(any("D11" in e for e in run_all(self.root)))

    def test_d11_phase_required_on_product_spec_not_exec_plan(self):
        ps = self.root / "docs" / "product-specs"; ps.mkdir()
        (ps / "index.md").write_text(fm() + "# I\n- s.md\n")
        spec = ps / "s.md"
        spec.write_text(fm(type="product-spec") + "# s\n")  # product-spec, no phase
        self.assertTrue(any("D11" in e and "phase" in e and "s.md" in e
                            for e in run_all(self.root)))
        spec.write_text(fm(type="product-spec", phase="x/01-y") + "# s\n")  # phased
        self.assertFalse(any("D11" in e and "s.md" in e for e in run_all(self.root)))
        ep = self.root / "docs" / "exec-plans" / "active"; ep.mkdir(parents=True)
        (ep / "p.md").write_text(fm(type="exec-plan") + "# p\n")  # plan, no phase = OK
        self.assertFalse(any("D11" in e and "p.md" in e for e in run_all(self.root)))

    def test_d12_resource_must_exist_if_repo_path(self):
        self._dd("r.md", extra="resource: nope/missing.py\n")
        self.assertTrue(any("D12" in e and "resource" in e for e in run_all(self.root)))
        self._dd("r.md", extra="resource: docs/design-docs/core-beliefs.md\n")  # exists
        self.assertFalse(any("D12" in e and "resource" in e for e in run_all(self.root)))
        self._dd("r.md", extra="resource: https://example.com/x\n")  # URL exempt
        self.assertFalse(any("D12" in e and "resource" in e for e in run_all(self.root)))

    def test_d12_supersedes_must_resolve(self):
        self._dd("a.md", extra="supersedes: gone.md\n")
        self.assertTrue(any("D12" in e and "supersedes" in e for e in run_all(self.root)))
        self._dd("a.md", extra="supersedes: core-beliefs.md\n")  # sibling exists
        self.assertFalse(any("D12" in e and "supersedes" in e for e in run_all(self.root)))

    def test_d12_phase_must_be_well_formed(self):
        self._dd("ph.md", extra="phase: //bad\n")
        self.assertTrue(any("D12" in e and "phase" in e for e in run_all(self.root)))
        self._dd("ph.md", extra="phase: alpha/01-good\n")
        self.assertFalse(any("D12" in e and "phase" in e for e in run_all(self.root)))
        self._dd("ph.md", extra="phase: alpha\n")  # bare initiative ok
        self.assertFalse(any("D12" in e and "phase" in e for e in run_all(self.root)))


if __name__ == "__main__":
    unittest.main()
