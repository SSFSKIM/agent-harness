"""Tests for director.config — the `.harness.json` `director` block loader
(ExecPlan 2026-06-16-director-declarative-config, M1).

Drives the pure loader on a fixture root with an injected `environ`, so nothing
touches the real filesystem outside a tmpdir or the real os.environ."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from director import config


def _write(root: Path, doc: dict) -> None:
    (root / ".harness.json").write_text(json.dumps(doc), encoding="utf-8")


class LoadConfigTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    # -- fail-open: absence yields defaults ---------------------------------
    def test_absent_file_yields_defaults(self):
        cfg = config.load_director_config(root=self.root)
        self.assertEqual(cfg, config.defaults())
        self.assertIsNone(cfg.team)
        self.assertEqual(cfg.concurrency, 3)
        self.assertEqual(cfg.states["ready"], "Todo")
        self.assertEqual(cfg.posture.approval_policy, "on-request")

    def test_no_director_block_yields_defaults(self):
        # the real repo .harness.json shape: worker_policy present, no director key
        _write(self.root, {"worker_policy": {"worker_env": []}})
        self.assertEqual(config.load_director_config(root=self.root), config.defaults())

    # -- partial block merges over defaults ---------------------------------
    def test_partial_block_merges(self):
        _write(self.root, {"director": {"concurrency": 7}})
        cfg = config.load_director_config(root=self.root)
        self.assertEqual(cfg.concurrency, 7)
        self.assertEqual(cfg.max_turns, 8)          # untouched default
        self.assertEqual(cfg.states["done"], "Done")

    def test_states_partial_override(self):
        _write(self.root, {"director": {"states": {"ready": "Backlog", "failed": "Failed"}}})
        cfg = config.load_director_config(root=self.root)
        self.assertEqual(cfg.states["ready"], "Backlog")
        self.assertEqual(cfg.states["failed"], "Failed")
        self.assertEqual(cfg.states["started"], "In Progress")  # default kept
        self.assertIsNone(cfg.states["blocked"])

    def test_unknown_state_key_ignored(self):
        _write(self.root, {"director": {"states": {"bogus": "X"}}})
        cfg = config.load_director_config(root=self.root)
        self.assertNotIn("bogus", cfg.states)
        self.assertEqual(cfg.states["ready"], "Todo")

    def test_posture_and_merger_override(self):
        _write(self.root, {"director": {
            "worker": {"network": False, "approval_policy": "untrusted"},
            "merger": {"max_merges": 5}}})
        cfg = config.load_director_config(root=self.root)
        self.assertFalse(cfg.posture.network)
        self.assertEqual(cfg.posture.approval_policy, "untrusted")
        self.assertTrue(cfg.posture.auto_review)           # default kept
        self.assertEqual(cfg.merger.max_merges, 5)
        self.assertEqual(cfg.merger.poll_s, 1.0)           # default kept

    # -- fail-loud: present-but-malformed raises ----------------------------
    def test_director_not_object_raises(self):
        _write(self.root, {"director": "nope"})
        with self.assertRaises(ValueError):
            config.load_director_config(root=self.root)

    def test_bad_concurrency_raises(self):
        for bad in (0, -1, "3", 3.5, True):
            _write(self.root, {"director": {"concurrency": bad}})
            with self.assertRaises(ValueError, msg=f"concurrency={bad!r}"):
                config.load_director_config(root=self.root)

    def test_bad_posture_raises(self):
        _write(self.root, {"director": {"worker": {"approval_policy": "yolo"}}})
        with self.assertRaises(ValueError):
            config.load_director_config(root=self.root)
        _write(self.root, {"director": {"worker": {"sandbox": "anywhere"}}})
        with self.assertRaises(ValueError):
            config.load_director_config(root=self.root)
        _write(self.root, {"director": {"worker": {"network": "yes"}}})
        with self.assertRaises(ValueError):
            config.load_director_config(root=self.root)

    def test_bad_done_types_raises(self):
        for bad in ([], "completed", [1, 2]):
            _write(self.root, {"director": {"done_types": bad}})
            with self.assertRaises(ValueError, msg=f"done_types={bad!r}"):
                config.load_director_config(root=self.root)

    def test_bad_codex_command_raises(self):
        _write(self.root, {"director": {"codex_command": "  "}})
        with self.assertRaises(ValueError):
            config.load_director_config(root=self.root)

    def test_malformed_json_file_raises(self):
        (self.root / ".harness.json").write_text("{not valid", encoding="utf-8")
        with self.assertRaises(ValueError):
            config.load_director_config(root=self.root)

    # -- $VAR indirection ---------------------------------------------------
    def test_var_resolves_from_environ(self):
        _write(self.root, {"director": {"team": "$DIRECTOR_TEAM"}})
        cfg = config.load_director_config(root=self.root, environ={"DIRECTOR_TEAM": "T-99"})
        self.assertEqual(cfg.team, "T-99")

    def test_var_braces_form(self):
        _write(self.root, {"director": {"team": "${DIRECTOR_TEAM}"}})
        cfg = config.load_director_config(root=self.root, environ={"DIRECTOR_TEAM": "T-7"})
        self.assertEqual(cfg.team, "T-7")

    def test_var_unset_is_missing(self):
        _write(self.root, {"director": {"team": "$NOPE"}})
        cfg = config.load_director_config(root=self.root, environ={})
        self.assertIsNone(cfg.team)  # unset $VAR → None (missing)

    def test_var_unset_for_typed_field_raises(self):
        # an unset $VAR on a field that must be a non-empty string → None → fail-loud
        _write(self.root, {"director": {"codex_command": "$CODEX"}})
        with self.assertRaises(ValueError):
            config.load_director_config(root=self.root, environ={})

    def test_literal_not_resolved(self):
        _write(self.root, {"director": {"states": {"ready": "Todo"}}})
        cfg = config.load_director_config(root=self.root, environ={})
        self.assertEqual(cfg.states["ready"], "Todo")  # no `$` → passthrough

    # -- immutability + operator surface ------------------------------------
    def test_config_is_frozen(self):
        cfg = config.defaults()
        with self.assertRaises(Exception):
            cfg.posture.network = False  # frozen dataclass

    def test_main_prints_json(self):
        import contextlib
        import io
        _write(self.root, {"director": {"concurrency": 4}})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = config.main(["--root", str(self.root)])
        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["concurrency"], 4)
        self.assertIn("posture", out)
        self.assertEqual(out["posture"]["approval_policy"], "on-request")


if __name__ == "__main__":
    unittest.main()
