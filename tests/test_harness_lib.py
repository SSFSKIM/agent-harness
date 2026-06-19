import os, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import harness_lib as hl


class TestHarnessLib(unittest.TestCase):
    def test_frontmatter_parses_flat_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.md"
            p.write_text("---\nstatus: draft\nlast_verified: 2026-06-12\nowner: a\n---\n# hi\n")
            fm = hl.read_frontmatter(p)
            self.assertEqual(fm["status"], "draft")
            self.assertEqual(fm["owner"], "a")

    def test_frontmatter_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.md"
            p.write_text("# no frontmatter\n")
            self.assertIsNone(hl.read_frontmatter(p))

    def test_frontmatter_unterminated_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.md"
            p.write_text("---\nstatus: draft\n# body without closing fence\n")
            self.assertIsNone(hl.read_frontmatter(p))

    def _fm(self, body):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.md"
            p.write_text(body, encoding="utf-8")
            return hl.read_frontmatter(p)

    def test_frontmatter_tags_flow_list(self):
        # canonical authored form: YAML flow inline -> Python list
        fm = self._fm("---\ntype: knowledge\ntags: [alpha, beta, gamma]\n---\n#h\n")
        self.assertEqual(fm["tags"], ["alpha", "beta", "gamma"])
        self.assertEqual(fm["type"], "knowledge")  # scalar alongside the list

    def test_frontmatter_tags_flow_empty_and_quoted(self):
        self.assertEqual(self._fm("---\ntags: []\n---\n")["tags"], [])
        fm = self._fm("---\ntags: ['a b', \"c\", d]\n---\n")
        self.assertEqual(fm["tags"], ["a b", "c", "d"])  # quotes/space stripped

    def test_frontmatter_tags_block_list(self):
        # OKF block form tolerated on read — both non-indented and indented
        flat = self._fm("---\ntags:\n- x\n- y\n---\n")
        self.assertEqual(flat["tags"], ["x", "y"])
        indented = self._fm("---\ntags:\n  - x\n  - y\n---\n")
        self.assertEqual(indented["tags"], ["x", "y"])

    def test_frontmatter_scalar_unchanged_regression(self):
        # the byte-for-byte backward-compat guarantee: scalars are still strings
        fm = self._fm("---\nstatus: stable\nlast_verified: 2026-06-18\nowner: a\n---\n")
        self.assertEqual(fm["status"], "stable")
        self.assertIsInstance(fm["owner"], str)

    def test_frontmatter_colon_in_value_preserved(self):
        # partition on first colon only — a colon inside a description survives
        fm = self._fm("---\ndescription: Triage: do the thing\n---\n")
        self.assertEqual(fm["description"], "Triage: do the thing")

    def test_frontmatter_empty_value_stays_scalar(self):
        # an empty-value key with no following `- ` items must NOT become a list
        fm = self._fm("---\nowner:\nstatus: stable\n---\n")
        self.assertEqual(fm["owner"], "")
        self.assertEqual(fm["status"], "stable")

    def test_frontmatter_mixed_scalar_flow_block(self):
        fm = self._fm(
            "---\ntype: adr\ntitle: T\ntags: [one, two]\nrefs:\n- a\n- b\n---\n")
        self.assertEqual(fm["type"], "adr")
        self.assertEqual(fm["title"], "T")
        self.assertEqual(fm["tags"], ["one", "two"])
        self.assertEqual(fm["refs"], ["a", "b"])

    def test_links_in_extracts_md_targets(self):
        # the one link definition shared by lint D5 and nav: .md targets only,
        # fragment stripped, http(s) targets still returned (callers skip them)
        text = ("see [a](foo.md) and [b](../bar/baz.md#frag) and "
                "[ext](https://x.md) and [c](dir/q.md)")
        self.assertEqual(hl.links_in(text),
                         ["foo.md", "../bar/baz.md", "https://x.md", "dir/q.md"])
        # non-.md links and plain text are not edges
        self.assertEqual(hl.links_in("[no](x.txt) text [y](z.png)"), [])

    def test_is_stale_true_for_old_active_page(self):
        self.assertTrue(hl.is_stale("2000-01-01", 30, "stable"))

    def test_is_stale_false_within_window(self):
        self.assertFalse(hl.is_stale(hl.today().isoformat(), 30, "active"))

    def test_is_stale_false_for_archived_or_completed_even_if_old(self):
        self.assertFalse(hl.is_stale("2000-01-01", 30, "archived"))
        self.assertFalse(hl.is_stale("2000-01-01", 30, "completed"))

    def test_is_stale_raises_on_bad_or_list_date(self):
        # the contract that lets lint emit a D4 "bad last_verified" FAIL and nav
        # skip the page rather than crash — parse happens before the status check
        with self.assertRaises(ValueError):
            hl.is_stale("not-a-date", 30, "stable")
        with self.assertRaises(TypeError):
            hl.is_stale(["2026-06-18"], 30, "stable")

    def test_is_headless_reads_env(self):
        import os
        os.environ.pop(hl.HEADLESS_ENV, None)
        self.assertFalse(hl.is_headless())
        os.environ[hl.HEADLESS_ENV] = "1"
        try:
            self.assertTrue(hl.is_headless())
        finally:
            del os.environ[hl.HEADLESS_ENV]

    def test_state_dir_creates_under_root(self):
        with tempfile.TemporaryDirectory() as d:
            sd = hl.state_dir(Path(d))
            self.assertTrue(sd.is_dir())
            self.assertEqual(sd, Path(d) / ".claude" / "harness")

    def test_gate_config_absent_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(hl.gate_config(Path(d)), {})

    def test_gate_config_parses_valid_object(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".harness.json").write_text(
                '{"lint_cmd": "make lint", "stale_days": 60}', encoding="utf-8")
            cfg = hl.gate_config(Path(d))
            self.assertEqual(cfg["lint_cmd"], "make lint")
            self.assertEqual(cfg["stale_days"], 60)

    def test_gate_config_malformed_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".harness.json").write_text("not json{{{", encoding="utf-8")
            self.assertEqual(hl.gate_config(Path(d)), {})

    def test_gate_config_non_object_returns_empty(self):
        # a top-level array/scalar is not a config object — fail open to {}
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".harness.json").write_text("[1, 2, 3]", encoding="utf-8")
            self.assertEqual(hl.gate_config(Path(d)), {})

    def test_gate_config_non_utf8_returns_empty(self):
        # a non-UTF8 byte must fail open, not be silently repaired into config
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".harness.json").write_bytes(b'{"lint_cmd": "echo \xff"}')
            self.assertEqual(hl.gate_config(Path(d)), {})

    def test_gate_command_absent_is_none(self):
        os.environ.pop("HARNESS_LINT_CMD", None)
        self.assertIsNone(hl.gate_command({}, "lint_cmd", "HARNESS_LINT_CMD"))

    def test_gate_command_splits_argv(self):
        os.environ.pop("HARNESS_LINT_CMD", None)
        self.assertEqual(
            hl.gate_command({"lint_cmd": "python3 .claude/lints/check.py"},
                            "lint_cmd", "HARNESS_LINT_CMD"),
            ["python3", ".claude/lints/check.py"])

    def test_gate_command_env_wins_over_config(self):
        os.environ["HARNESS_LINT_CMD"] = "env-cmd --flag"
        try:
            self.assertEqual(
                hl.gate_command({"lint_cmd": "cfg"}, "lint_cmd", "HARNESS_LINT_CMD"),
                ["env-cmd", "--flag"])
        finally:
            del os.environ["HARNESS_LINT_CMD"]

    def test_gate_command_non_string_and_blank_are_none(self):
        os.environ.pop("HARNESS_LINT_CMD", None)
        self.assertIsNone(hl.gate_command({"lint_cmd": 5}, "lint_cmd", "HARNESS_LINT_CMD"))
        self.assertIsNone(hl.gate_command({"lint_cmd": True}, "lint_cmd", "HARNESS_LINT_CMD"))
        self.assertIsNone(hl.gate_command({"lint_cmd": "  "}, "lint_cmd", "HARNESS_LINT_CMD"))

    def test_gate_command_unparseable_raises(self):
        # present but broken (unbalanced quote) must be LOUD, not a silent skip
        os.environ.pop("HARNESS_LINT_CMD", None)
        with self.assertRaises(ValueError):
            hl.gate_command({"lint_cmd": "foo '"}, "lint_cmd", "HARNESS_LINT_CMD")


if __name__ == "__main__":
    unittest.main()
