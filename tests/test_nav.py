import datetime, subprocess, sys, tempfile, unittest
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
        paths = sorted(r["path"] for r in nav.stale(self.records, self.root))
        self.assertEqual(paths, ["docs/memory/knowledge/old.md"])


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


if __name__ == "__main__":
    unittest.main()
