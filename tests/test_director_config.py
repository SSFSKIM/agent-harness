"""Tests for director.config — the `.harness.json` `director` block loader
(ExecPlan 2026-06-16-director-declarative-config, M1).

Drives the pure loader on a fixture root with an injected `environ`, so nothing
touches the real filesystem outside a tmpdir or the real os.environ."""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from director import config


def _write(root: Path, doc: dict) -> None:
    (root / ".harness.json").write_text(json.dumps(doc), encoding="utf-8")


@contextlib.contextmanager
def _chdir(path):
    prev = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


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

    # -- worker capability knobs (tools / install_skills) -------------------
    def test_worker_tools_default_off(self):
        # global default leaves the offline behavior unchanged (no tool, no skills)
        d = config.defaults()
        self.assertEqual(d.worker_tools, "none")
        self.assertFalse(d.worker_install_skills)

    def test_worker_tools_opt_in(self):
        _write(self.root, {"director": {"worker": {"tools": "linear",
                                                   "install_skills": True}}})
        cfg = config.load_director_config(root=self.root)
        self.assertEqual(cfg.worker_tools, "linear")
        self.assertTrue(cfg.worker_install_skills)
        self.assertEqual(cfg.posture.approval_policy, "on-request")  # posture untouched

    def test_bad_worker_tools_raises(self):
        _write(self.root, {"director": {"worker": {"tools": "github"}}})
        with self.assertRaises(ValueError):
            config.load_director_config(root=self.root)

    def test_bad_install_skills_raises(self):
        _write(self.root, {"director": {"worker": {"install_skills": "yes"}}})
        with self.assertRaises(ValueError):
            config.load_director_config(root=self.root)

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

    # -- workspace lifecycle hooks (R4) -------------------------------------
    def test_workspace_hooks_absent_yields_none(self):
        cfg = config.load_director_config(root=self.root)
        self.assertEqual(cfg.workspace.hooks,
                         {"after_create": None, "before_run": None,
                          "after_run": None, "before_remove": None})
        self.assertEqual(cfg.workspace.hook_timeout_s, 60.0)

    def test_workspace_hooks_partial_override(self):
        # whole-string $VAR is substituted at the config layer; an EMBEDDED $VAR (e.g.
        # `git clone $REPO .`) is left for `sh -lc` to expand at runtime from the env.
        _write(self.root, {"director": {"workspace": {
            "hooks": {"after_create": "$CLONE_CMD", "before_run": "git clone $REPO ."},
            "hook_timeout_s": 120}}})
        cfg = config.load_director_config(root=self.root,
                                          environ={"CLONE_CMD": "git clone https://x/y.git ."})
        self.assertEqual(cfg.workspace.hooks["after_create"], "git clone https://x/y.git .")
        self.assertEqual(cfg.workspace.hooks["before_run"], "git clone $REPO .")  # shell-time
        self.assertIsNone(cfg.workspace.hooks["after_run"])  # unset stays None
        self.assertEqual(cfg.workspace.hook_timeout_s, 120.0)

    def test_workspace_unknown_hook_key_raises(self):
        # a typo'd hook name must fail loud (a silently-never-run clone is a bad failure)
        _write(self.root, {"director": {"workspace": {"hooks": {"befor_run": "x"}}}})
        with self.assertRaises(ValueError):
            config.load_director_config(root=self.root)

    def test_workspace_bad_hook_type_raises(self):
        _write(self.root, {"director": {"workspace": {"hooks": {"after_create": 7}}}})
        with self.assertRaises(ValueError):
            config.load_director_config(root=self.root)

    def test_workspace_bad_timeout_raises(self):
        for bad in (0, -1, "60", True):
            _write(self.root, {"director": {"workspace": {"hook_timeout_s": bad}}})
            with self.assertRaises(ValueError, msg=f"timeout={bad!r}"):
                config.load_director_config(root=self.root)

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


class WiringTest(unittest.TestCase):
    """orchestrator.resolve_settings precedence (CLI > config > default) and the
    fail-loud-before-dispatch guarantee at orchestrator.main (M2)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _args(self, **over):
        base = dict(team=None, ready_state=None, started_state=None, done_state=None,
                    failed_state=None, blocked_state=None, done_types=None,
                    concurrency=None, max_turns=None, max_passes=None, max_dispatched=None,
                    read_timeout=None, turn_review_timeout=None, reconcile_interval=None,
                    poll_interval=None, backoff_base=None, backoff_cap=None, codex=None,
                    workspace_root=None, queue_dir=None, status_dir=None)
        base.update(over)
        return argparse.Namespace(**base)

    def test_defaults_when_no_cli_no_config(self):
        from director import orchestrator
        s = orchestrator.resolve_settings(self._args(), config.defaults())
        self.assertEqual(s["concurrency"], 3)
        self.assertEqual(s["states"]["ready"], "Todo")
        self.assertEqual(s["done_types"], ("completed",))
        self.assertIsNone(s["team"])

    def test_config_fills_when_no_cli(self):
        from director import orchestrator
        cfg = config._build({"concurrency": 9, "team": "T-cfg",
                             "states": {"ready": "Backlog"}})
        s = orchestrator.resolve_settings(self._args(), cfg)
        self.assertEqual(s["concurrency"], 9)
        self.assertEqual(s["team"], "T-cfg")
        self.assertEqual(s["states"]["ready"], "Backlog")
        self.assertEqual(s["states"]["started"], "In Progress")  # default kept

    def test_cli_overrides_config(self):
        from director import orchestrator
        cfg = config._build({"concurrency": 9, "team": "T-cfg"})
        s = orchestrator.resolve_settings(
            self._args(concurrency=2, team="T-cli", done_types="completed,canceled"), cfg)
        self.assertEqual(s["concurrency"], 2)          # CLI wins
        self.assertEqual(s["team"], "T-cli")
        self.assertEqual(s["done_types"], ("completed", "canceled"))

    def test_worker_tools_resolve(self):
        from director import orchestrator
        cfg = config._build({"worker": {"tools": "linear", "install_skills": True}})
        s = orchestrator.resolve_settings(self._args(), cfg)            # config fills
        self.assertEqual((s["tools"], s["install_skills"]), ("linear", True))
        s2 = orchestrator.resolve_settings(                            # CLI overrides
            self._args(tools="linear", install_skills=True), config._build({}))
        self.assertEqual((s2["tools"], s2["install_skills"]), ("linear", True))

    def test_mock_run_ignores_linear_tool_config(self):
        # the offline --mock niche never wires the linear tool / skills, even when the
        # host config defaults them on (it has no live executor / real worker).
        from director import orchestrator
        _write(self.root, {"director": {"worker": {"tools": "linear",
                                                   "install_skills": True}}})
        board = orchestrator.MockBoard.demo()
        with _chdir(self.root), mock.patch(
                "director.orchestrator.run_until_drained",
                return_value={"summaries": [], "passes": 1,
                              "stopped_reason": "drained", "stuck": []}) as drained:
            orchestrator.main(["--team", "T", "--mock", "--mock-scenario", "report"],
                              board=board)
        kw = drained.call_args.kwargs
        self.assertIsNone(kw["tools"])
        self.assertFalse(kw["install_skills"])

    def test_real_run_honors_linear_tool_config(self):
        # a real (non-mock) run picks up the host's linear tool + skill default with no flag
        from director import orchestrator
        _write(self.root, {"director": {"team": "T", "worker": {
            "tools": "linear", "install_skills": True}}})
        board = orchestrator.MockBoard.demo()
        with _chdir(self.root), mock.patch(
                "director.orchestrator.run_until_drained",
                return_value={"summaries": [], "passes": 1,
                              "stopped_reason": "drained", "stuck": []}) as drained:
            orchestrator.main([], board=board)  # team + tooling from config, no flags
        kw = drained.call_args.kwargs
        self.assertIsNotNone(kw["tools"])
        self.assertTrue(kw["install_skills"])

    def test_reconcile_interval_resolves(self):
        from director import orchestrator
        cfg = config._build({"reconcile_interval_s": 3.0})
        self.assertEqual(orchestrator.resolve_settings(self._args(), cfg)["reconcile_interval_s"], 3.0)
        s = orchestrator.resolve_settings(self._args(reconcile_interval=0.5), cfg)
        self.assertEqual(s["reconcile_interval_s"], 0.5)  # CLI overrides config

    def test_poll_interval_resolves(self):
        from director import orchestrator
        cfg = config._build({"poll_interval_s": 4.0})
        self.assertEqual(orchestrator.resolve_settings(self._args(), cfg)["poll_interval_s"], 4.0)
        s = orchestrator.resolve_settings(self._args(poll_interval=0.25), cfg)
        self.assertEqual(s["poll_interval_s"], 0.25)  # CLI overrides config

    def test_poll_interval_default_and_validation(self):
        self.assertEqual(config.defaults().poll_interval_s, 10.0)
        _write(self.root, {"director": {"poll_interval_s": 0}})  # not positive
        with self.assertRaises(ValueError):
            config.load_director_config(root=self.root)

    def test_backoff_knobs_resolve(self):
        from director import orchestrator
        cfg = config._build({"backoff_base_s": 5.0, "backoff_cap_s": 120.0})
        s = orchestrator.resolve_settings(self._args(), cfg)
        self.assertEqual((s["backoff_base_s"], s["backoff_cap_s"]), (5.0, 120.0))
        s = orchestrator.resolve_settings(self._args(backoff_base=0.5, backoff_cap=9.0), cfg)
        self.assertEqual((s["backoff_base_s"], s["backoff_cap_s"]), (0.5, 9.0))  # CLI wins

    def test_backoff_defaults_and_validation(self):
        d = config.defaults()
        self.assertEqual((d.backoff_base_s, d.backoff_cap_s), (10.0, 300.0))
        for bad in ({"backoff_base_s": 0}, {"backoff_cap_s": -1}):
            _write(self.root, {"director": bad})
            with self.assertRaises(ValueError):
                config.load_director_config(root=self.root)

    def test_malformed_config_fails_before_dispatch(self):
        from director import orchestrator
        _write(self.root, {"director": {"concurrency": 0}})  # malformed (not positive)
        spy = orchestrator.MockBoard.demo()
        with _chdir(self.root), self.assertRaises(ValueError):
            orchestrator.main(["--team", "T", "--mock"], board=spy)
        self.assertEqual(spy.transitions, {})  # raised before any claim/dispatch

    def test_missing_team_fails_before_dispatch(self):
        from director import orchestrator
        _write(self.root, {"director": {"concurrency": 2}})  # valid, but no team
        spy = orchestrator.MockBoard.demo()
        with _chdir(self.root), self.assertRaises(SystemExit):
            orchestrator.main(["--mock"], board=spy)  # no --team, no director.team
        self.assertEqual(spy.transitions, {})


if __name__ == "__main__":
    unittest.main()
