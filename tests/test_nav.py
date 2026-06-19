import datetime, json, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import nav


def _page(p, fm_lines, body=""):
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = "\n".join(fm_lines)
    p.write_text(f"---\n{fm}\n---\n{body}", encoding="utf-8")


def _fixture(root):
    """A minimal corpus under docs/memory/ — a default managed root, so every
    page here is governed (catalog scope) even in relaxed host mode."""
    (root / "AGENTS.md").write_text("# map\nsee [adr](docs/memory/adr/a1.md)\n",
                                    encoding="utf-8")
    _page(root / "docs/memory/adr/a1.md",
          ["status: accepted", "last_verified: 2026-06-18", "owner: h",
           "type: adr", "tags: [alpha, beta]",
           "description: First decision."],
          body="links to [k](../knowledge/k1.md)\n")
    _page(root / "docs/memory/knowledge/k1.md",
          ["status: stable", "last_verified: 2026-06-18", "owner: h",
           "type: knowledge", "tags: [alpha]",
           "description: A how-to.", "resource: plugin/scripts/nav.py"])
    # body-less page: metadata must still surface (catalog reads frontmatter)
    _page(root / "docs/memory/knowledge/empty.md",
          ["status: stable", "last_verified: 2026-06-18", "owner: h",
           "type: knowledge", "tags: [gamma]", "description: No body here."])
    # malformed tags (scalar instead of list) must not crash --tag
    _page(root / "docs/memory/openq/q1.md",
          ["status: open", "last_verified: 2026-06-18", "owner: h",
           "type: openq", "tags: solo", "description: An open question."])


class TestNavCatalog(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _fixture(self.root)
        self.records = nav.build_index(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _paths(self, rows):
        return sorted(r["path"] for r in rows)

    def test_build_index_reads_frontmatter_columns(self):
        rec = next(r for r in self.records if r["path"] == "docs/memory/adr/a1.md")
        self.assertEqual(rec["type"], "adr")
        self.assertEqual(rec["tags"], ["alpha", "beta"])
        self.assertEqual(rec["status"], "accepted")
        self.assertEqual(rec["description"], "First decision.")
        self.assertTrue(rec["catalog"])

    def test_catalog_filters_by_type(self):
        rows = nav.catalog(self.records, kind="knowledge")
        self.assertEqual(self._paths(rows),
                         ["docs/memory/knowledge/empty.md",
                          "docs/memory/knowledge/k1.md"])

    def test_catalog_filters_by_tag_AND_type(self):
        rows = nav.catalog(self.records, kind="knowledge", tag="alpha")
        self.assertEqual(self._paths(rows), ["docs/memory/knowledge/k1.md"])

    def test_catalog_filters_by_status(self):
        rows = nav.catalog(self.records, status="open")
        self.assertEqual(self._paths(rows), ["docs/memory/openq/q1.md"])

    def test_bodyless_page_still_catalogued(self):
        # the whole point: metadata comes from frontmatter, not the body
        rec = next(r for r in self.records
                   if r["path"] == "docs/memory/knowledge/empty.md")
        self.assertEqual(rec["description"], "No body here.")
        self.assertIn(rec, nav.catalog(self.records, kind="knowledge"))

    def test_malformed_scalar_tags_coerced_not_crash(self):
        rec = next(r for r in self.records if r["path"] == "docs/memory/openq/q1.md")
        self.assertEqual(rec["tags"], ["solo"])  # scalar -> single-item list
        # and it is filterable without raising
        self.assertEqual(self._paths(nav.catalog(self.records, tag="solo")),
                         ["docs/memory/openq/q1.md"])

    def test_catalog_excludes_spine_maps(self):
        # AGENTS.md is indexed (link source) but never a catalog row
        self.assertNotIn("AGENTS.md", self._paths(nav.catalog(self.records)))
        self.assertIn("AGENTS.md", [r["path"] for r in self.records])

    def test_links_resolved_repo_relative(self):
        rec = next(r for r in self.records if r["path"] == "docs/memory/adr/a1.md")
        self.assertEqual(rec["links"], ["docs/memory/knowledge/k1.md"])

    def test_links_and_backlinks(self):
        self.assertEqual(nav.links(self.records, "docs/memory/adr/a1.md", self.root),
                         ["docs/memory/knowledge/k1.md"])
        # AGENTS.md links to a1 (a1 has an inbound edge from the map)
        self.assertEqual(nav.backlinks(self.records, "docs/memory/adr/a1.md", self.root),
                         ["AGENTS.md"])
        # k1 is linked only by a1
        self.assertEqual(nav.backlinks(self.records, "docs/memory/knowledge/k1.md",
                                       self.root), ["docs/memory/adr/a1.md"])

    def test_orphans_are_catalog_pages_with_no_inbound(self):
        # a1 (linked by AGENTS) and k1 (linked by a1) are reachable; empty + q1
        # have no inbound markdown link. Spines/maps are never orphans.
        self.assertEqual(nav.orphans(self.records),
                         ["docs/memory/knowledge/empty.md", "docs/memory/openq/q1.md"])


class TestNavStale(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _page(self.root / "docs/memory/knowledge/fresh.md",
              ["status: stable", f"last_verified: {datetime.date.today().isoformat()}",
               "owner: h", "type: knowledge", "description: Fresh."])
        _page(self.root / "docs/memory/knowledge/old.md",
              ["status: stable", "last_verified: 2000-01-01", "owner: h",
               "type: knowledge", "description: Old and active."])
        _page(self.root / "docs/memory/archive/done.md",
              ["status: archived", "last_verified: 2000-01-01", "owner: h",
               "type: session-digest", "description: Old but archived."])
        self.records = nav.build_index(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_stale_lists_only_old_active_pages(self):
        # old+active is stale; fresh is within window; archived is exempt
        paths = sorted(r["path"] for r in nav.stale(self.records, 30))
        self.assertEqual(paths, ["docs/memory/knowledge/old.md"])


class TestNavLinkEscape(unittest.TestCase):
    def test_out_of_root_link_skipped_not_crash(self):
        # a link target that EXISTS but resolves outside the repo root must be
        # skipped, never crash build_index (review: nav.py _resolve_links).
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "outside.md").write_text("# out\n", encoding="utf-8")
            root = tmp / "repo"
            _page(root / "docs/memory/knowledge/p.md",
                  ["status: stable", "last_verified: 2026-06-18", "owner: h",
                   "type: knowledge", "description: links outside root."],
                  body="see [o](../../../../outside.md)\n")
            records = nav.build_index(root)  # must not raise
            rec = next(r for r in records if r["path"].endswith("p.md"))
            self.assertEqual(rec["links"], [])  # escaping edge dropped


class TestNavDrift(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for args in (["init", "-q"], ["config", "user.email", "t@t"],
                     ["config", "user.name", "t"]):
            subprocess.run(["git", "-C", str(self.root), *args], check=True,
                           capture_output=True, text=True)
        res = self.root / "plugin" / "scripts" / "x.py"
        res.parent.mkdir(parents=True)
        res.write_text("# code\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True,
                       capture_output=True, text=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-q", "-m", "x"],
                       check=True, capture_output=True, text=True)  # commit date = today
        _page(self.root / "docs/memory/knowledge/drifted.md",
              ["status: stable", "last_verified: 2000-01-01", "owner: h",
               "type: knowledge", "resource: plugin/scripts/x.py", "description: d"])
        _page(self.root / "docs/memory/knowledge/current.md",
              ["status: stable", f"last_verified: {datetime.date.today().isoformat()}",
               "owner: h", "type: knowledge", "resource: plugin/scripts/x.py",
               "description: c"])
        _page(self.root / "docs/memory/knowledge/missing.md",
              ["status: stable", "last_verified: 2000-01-01", "owner: h",
               "type: knowledge", "resource: plugin/scripts/gone.py", "description: m"])
        self.records = nav.build_index(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_drift_states(self):
        states = {r["path"]: r["state"] for r in nav.drift(self.records, self.root)}
        self.assertEqual(states["docs/memory/knowledge/drifted.md"], "drifted")
        self.assertEqual(states["docs/memory/knowledge/current.md"], "current")
        self.assertEqual(states["docs/memory/knowledge/missing.md"], "unknown")


def _typed_fixture(root):
    """A corpus exercising each inferred edge type across multiple directories."""
    _page(root / "docs/exec-plans/active/p1.md",
          ["status: active", "last_verified: 2026-06-19", "owner: h",
           "type: exec-plan", "description: a plan."],
          body="implements [s1](../../product-specs/s1.md) on "
               "[d1](../../design-docs/d1.md)\n")
    _page(root / "docs/product-specs/s1.md",
          ["status: active", "last_verified: 2026-06-19", "owner: h",
           "type: product-spec", "description: spec one."],
          body="refines [s2](s2.md); governed by [plans](../PLANS.md)\n")
    _page(root / "docs/product-specs/s2.md",
          ["status: stable", "last_verified: 2026-06-19", "owner: h",
           "type: product-spec", "description: spec two."],
          body="references [k1](../memory/knowledge/k1.md)\n")
    _page(root / "docs/design-docs/d1.md",
          ["status: stable", "last_verified: 2026-06-19", "owner: h",
           "type: design-doc", "description: a design doc."])
    _page(root / "docs/memory/adr/a1.md",
          ["status: accepted", "last_verified: 2026-06-19", "owner: h",
           "type: adr", "description: new decision."],
          body="supersedes [a0](a0.md)\n")
    _page(root / "docs/memory/adr/a0.md",
          ["status: archived", "last_verified: 2026-06-19", "owner: h",
           "type: adr", "description: old decision."])
    _page(root / "docs/memory/knowledge/k1.md",
          ["status: stable", "last_verified: 2026-06-19", "owner: h",
           "type: knowledge", "description: a how-to."],
          body="grounded in [d1](../../design-docs/d1.md)\n")
    _page(root / "docs/PLANS.md",
          ["status: stable", "last_verified: 2026-06-19", "owner: h",
           "type: methodology", "description: the method."])
    # no `type` key -> degrades gracefully to untyped 'links'
    _page(root / "docs/memory/knowledge/notype.md",
          ["status: stable", "last_verified: 2026-06-19", "owner: h",
           "description: no type key."],
          body="see [s1](../../product-specs/s1.md)\n")


class TestNavRelations(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _typed_fixture(self.root)
        self.records = nav.build_index(self.root)
        self.rel = {(e["src"], e["dst"]): e["rel"]
                    for e in nav.relations(self.records)}

    def tearDown(self):
        self._tmp.cleanup()

    def _r(self, src, dst):
        return self.rel[(f"docs/{src}", f"docs/{dst}")]

    def test_inferred_edge_types(self):
        self.assertEqual(self._r("exec-plans/active/p1.md",
                                 "product-specs/s1.md"), "implements")
        self.assertEqual(self._r("exec-plans/active/p1.md",
                                 "design-docs/d1.md"), "grounded-in")
        self.assertEqual(self._r("product-specs/s1.md",
                                 "product-specs/s2.md"), "refines")
        self.assertEqual(self._r("product-specs/s1.md", "PLANS.md"), "governed-by")
        self.assertEqual(self._r("memory/adr/a1.md",
                                 "memory/adr/a0.md"), "supersedes")
        self.assertEqual(self._r("memory/knowledge/k1.md",
                                 "design-docs/d1.md"), "grounded-in")
        self.assertEqual(self._r("product-specs/s2.md",
                                 "memory/knowledge/k1.md"), "references")

    def test_inverse_covers_every_inferable_relation(self):
        # guard: INVERSE must stay in lockstep with what _infer_rel can emit, so
        # `tree --reverse` never silently falls back to a forward label
        inferable = set(nav.EDGE_RULES.values()) | {
            "supersedes", "governed-by", "references", "links"}
        self.assertTrue(inferable <= set(nav.INVERSE),
                        f"missing inverse for {inferable - set(nav.INVERSE)}")

    def test_missing_type_degrades_to_links(self):
        # source has no `type` and no dst-kind rule fires -> untyped
        self.assertEqual(self._r("memory/knowledge/notype.md",
                                 "product-specs/s1.md"), "links")

    def test_orphans_type_filter(self):
        allo = nav.orphans(self.records)
        self.assertIn("docs/exec-plans/active/p1.md", allo)  # nothing links to it
        self.assertIn("docs/memory/adr/a1.md", allo)
        self.assertEqual(nav.orphans(self.records, kind="adr"),
                         ["docs/memory/adr/a1.md"])
        self.assertEqual(nav.orphans(self.records, kind="exec-plan"),
                         ["docs/exec-plans/active/p1.md"])
        # the knowledge tier is fully connected (k1 has an inbound link)
        self.assertEqual(nav.orphans(self.records, kind="knowledge"), [])

    def test_basis_is_auditable(self):
        basis = {(e["src"], e["dst"]): e["basis"]
                 for e in nav.relations(self.records)}
        self.assertEqual(basis[("docs/exec-plans/active/p1.md",
                                "docs/product-specs/s1.md")],
                         "exec-plan->product-spec")


class TestNavTree(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _typed_fixture(self.root)
        self.records = nav.build_index(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _flatten(self, node, acc=None):
        acc = [] if acc is None else acc
        acc.append(node)
        for c in node["children"]:
            self._flatten(c, acc)
        return acc

    def test_forward_tree_is_directory_independent(self):
        # one derived tree groups pages from >=3 different directories — the proof
        t = nav.tree(self.records, "docs/exec-plans/active/p1.md")
        nodes = self._flatten(t)
        paths = [n["path"] for n in nodes]
        self.assertIn("docs/product-specs/s1.md", paths)
        self.assertIn("docs/design-docs/d1.md", paths)
        dirs = {p.rsplit("/", 1)[0] for p in paths}
        self.assertGreaterEqual(len(dirs), 3)
        s1 = next(n for n in nodes if n["path"] == "docs/product-specs/s1.md")
        self.assertEqual(s1["rel"], "implements")  # typed, not bare 'links'

    def test_reverse_tree_shows_dependents(self):
        t = nav.tree(self.records, "docs/product-specs/s1.md", reverse=True)
        kids = {c["path"]: c["rel"] for c in t["children"]}
        self.assertEqual(kids.get("docs/exec-plans/active/p1.md"), "implemented-by")

    def test_rel_filter_restricts_edges(self):
        t = nav.tree(self.records, "docs/exec-plans/active/p1.md",
                     rels={"implements"})
        kids = [c["path"] for c in t["children"]]
        self.assertIn("docs/product-specs/s1.md", kids)
        self.assertNotIn("docs/design-docs/d1.md", kids)  # grounded-in excluded

    def test_render_is_indented_ascii(self):
        lines = nav._tree_lines(nav.tree(self.records,
                                         "docs/exec-plans/active/p1.md"))
        self.assertTrue(lines[0].startswith("exec-plan: p1"))
        self.assertTrue(any("─" in line for line in lines[1:]))

    def test_default_excludes_untyped_links(self):
        # notype.md -> s1 is an untyped 'links' edge; default tree drops it,
        # --all (include_untyped) keeps it (the only edge, so children prove it)
        t = nav.tree(self.records, "docs/memory/knowledge/notype.md")
        self.assertEqual(t["children"], [])
        t_all = nav.tree(self.records, "docs/memory/knowledge/notype.md",
                         include_untyped=True)
        kids = {c["path"]: c["rel"] for c in t_all["children"]}
        self.assertEqual(kids.get("docs/product-specs/s1.md"), "links")


class TestNavTreeCycle(unittest.TestCase):
    def test_cycle_does_not_loop(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _page(root / "docs/product-specs/s1.md",
                  ["status: active", "last_verified: 2026-06-19", "owner: h",
                   "type: product-spec", "description: one."], body="[s2](s2.md)\n")
            _page(root / "docs/product-specs/s2.md",
                  ["status: active", "last_verified: 2026-06-19", "owner: h",
                   "type: product-spec", "description: two."], body="[s1](s1.md)\n")
            records = nav.build_index(root)
            t = nav.tree(records, "docs/product-specs/s1.md")  # must terminate
            s2 = t["children"][0]
            self.assertEqual(s2["path"], "docs/product-specs/s2.md")
            back = s2["children"][0]  # s2 -> s1 again
            self.assertEqual(back["path"], "docs/product-specs/s1.md")
            self.assertTrue(back["seen"])      # marked seen
            self.assertEqual(back["children"], [])  # and not re-expanded


class TestNavTreeDedup(unittest.TestCase):
    def test_duplicate_links_collapse_in_tree_not_relations(self):
        # asymmetric dedup: relations() is faithful 1:1 to the link list, but the
        # tree/adjacency view collapses repeated (src,dst) to one child.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _page(root / "docs/exec-plans/active/p.md",
                  ["status: active", "last_verified: 2026-06-19", "owner: h",
                   "type: exec-plan", "description: links target twice."],
                  body="[s](../../product-specs/s.md) and again "
                       "[s](../../product-specs/s.md)\n")
            _page(root / "docs/product-specs/s.md",
                  ["status: stable", "last_verified: 2026-06-19", "owner: h",
                   "type: product-spec", "description: target."])
            records = nav.build_index(root)
            edges = [e for e in nav.relations(records)
                     if e["dst"] == "docs/product-specs/s.md"]
            self.assertEqual(len(edges), 2)  # relations: faithful to the links
            t = nav.tree(records, "docs/exec-plans/active/p.md")
            kids = [c["path"] for c in t["children"]]
            self.assertEqual(kids.count("docs/product-specs/s.md"), 1)  # tree: once


def _roadmap_fixture(root):
    """Two phased initiatives + an unphased page + a pivot + a non-row type."""
    # alpha/01: spec + a plan that implements it (no own phase -> inherits)
    _page(root / "docs/product-specs/sa1.md",
          ["status: active", "last_verified: 2026-06-19", "owner: h",
           "type: product-spec", "phase: alpha/01-foo", "description: alpha one."])
    _page(root / "docs/exec-plans/active/pa1.md",
          ["status: completed", "last_verified: 2026-06-19", "owner: h",
           "type: exec-plan", "description: builds sa1."],
          body="implements [sa1](../../product-specs/sa1.md)\n")
    # alpha/02: an ARCHIVED spec superseded by its replacement, same phase. The
    # replacement links it twice — pivots must dedupe.
    _page(root / "docs/product-specs/sa2.md",
          ["status: archived", "last_verified: 2026-06-19", "owner: h",
           "type: product-spec", "phase: alpha/02-bar", "description: retired."])
    _page(root / "docs/product-specs/sa3.md",
          ["status: active", "last_verified: 2026-06-19", "owner: h",
           "type: product-spec", "phase: alpha/02-bar", "description: replaces two."],
          body="supersedes [sa2](sa2.md) — see also [sa2](sa2.md)\n")
    # a design-doc carrying a phase: must NOT become a roadmap row (work tier only)
    _page(root / "docs/design-docs/dd1.md",
          ["status: stable", "last_verified: 2026-06-19", "owner: h",
           "type: design-doc", "phase: alpha/01-foo", "description: not a row."])
    # beta: a bare-initiative umbrella (no NN)
    _page(root / "docs/product-specs/sb1.md",
          ["status: stable", "last_verified: 2026-06-19", "owner: h",
           "type: product-spec", "phase: beta", "description: beta umbrella."])
    # unphased: no phase, no implements edge
    _page(root / "docs/product-specs/su1.md",
          ["status: active", "last_verified: 2026-06-19", "owner: h",
           "type: product-spec", "description: unphased."])


class TestNavRoadmap(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _roadmap_fixture(self.root)
        self.records = nav.build_index(self.root)
        self.rm = nav.roadmap(self.records)

    def tearDown(self):
        self._tmp.cleanup()

    def _init(self, name):
        return next(b for b in self.rm["initiatives"] if b["initiative"] == name)

    def test_groups_by_initiative_sorted(self):
        self.assertEqual([b["initiative"] for b in self.rm["initiatives"]],
                         ["alpha", "beta"])

    def test_phases_ordered_by_NN(self):
        self.assertEqual([p["phase"] for p in self._init("alpha")["phases"]],
                         ["01-foo", "02-bar"])

    def test_bare_initiative_is_umbrella(self):
        self.assertEqual([p["phase"] for p in self._init("beta")["phases"]], [""])

    def test_status_is_projected(self):
        foo = self._init("alpha")["phases"][0]
        st = {i["path"].rsplit("/", 1)[-1]: i["status"] for i in foo["items"]}
        self.assertEqual(st["sa1.md"], "active")
        self.assertEqual(st["pa1.md"], "completed")

    def test_plan_inherits_phase_from_implemented_spec(self):
        foo = self._init("alpha")["phases"][0]
        paths = [i["path"] for i in foo["items"]]
        self.assertIn("docs/exec-plans/active/pa1.md", paths)  # inherited alpha/01
        self.assertEqual(foo["items"][0]["path"],  # spec sorts before its plan
                         "docs/product-specs/sa1.md")

    def test_unphased_bucket(self):
        self.assertEqual([i["path"] for i in self.rm["unphased"]],
                         ["docs/product-specs/su1.md"])

    def test_pivot_annotation_inline_and_deduped(self):
        # a supersession (newer page -> archived predecessor of its kind) shows
        # inline; a structural `refines` does NOT; duplicate links collapse to one
        bar = self._init("alpha")["phases"][1]
        sa2 = next(i for i in bar["items"] if i["path"].endswith("sa2.md"))
        self.assertEqual(sa2["pivots"],
                         [("superseded-by", "docs/product-specs/sa3.md")])

    def test_only_work_tier_pages_are_rows(self):
        # dd1 (design-doc) carries phase alpha/01-foo but must not appear as a row
        rows = [i["path"] for b in self.rm["initiatives"]
                for p in b["phases"] for i in p["items"]]
        rows += [i["path"] for i in self.rm["unphased"]]
        self.assertNotIn("docs/design-docs/dd1.md", rows)
        self.assertTrue(all(p.startswith(("docs/product-specs/",
                                          "docs/exec-plans/")) for p in rows))

    def test_render_and_empty_corpus(self):
        # both render modes do not raise; the JSON path is serializable and the
        # parsed JSON preserves the structure (tuples become arrays); an empty
        # corpus is a no-crash empty map
        nav._emit_roadmap(self.rm, as_json=False)
        nav._emit_roadmap(self.rm, as_json=True)
        parsed = json.loads(json.dumps(self.rm))  # serializable, no raise
        self.assertEqual(parsed["initiatives"][0]["initiative"], "alpha")
        self.assertEqual(nav.roadmap([]), {"initiatives": [], "unphased": []})


if __name__ == "__main__":
    unittest.main()
