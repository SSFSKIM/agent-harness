import sys, tempfile, unittest
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


if __name__ == "__main__":
    unittest.main()
