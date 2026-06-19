import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.queue as dq  # noqa: E402
import director.director_min as dmin  # noqa: E402
import director.run as run  # noqa: E402
from director.worker.app_server import extract_usage  # noqa: E402

MOCK = str(Path(run.__file__).resolve().parent / "worker" / "_mock_app_server.py")


class RunEndToEndTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.qbase = self.tmp / "q"

    def _ticket_path(self, prompt="do a risky thing"):
        path = self.tmp / "stub.json"
        path.write_text(json.dumps({
            "id": "STUB-1", "prompt": prompt, "workspace": str(self.tmp / "ws")}))
        return path

    def test_end_to_end_stub_with_director_responder(self):
        ticket = run.load_ticket(self._ticket_path())
        stop = threading.Event()
        responder = threading.Thread(
            target=dmin.auto_respond, kwargs={"base": self.qbase, "stop": stop})
        responder.start()
        try:
            result = run.run_ticket(
                ticket, command=[sys.executable, MOCK, "approval"],
                queue_base=self.qbase, workspace_root=self.tmp / "wsroot")
        finally:
            stop.set()
            responder.join(timeout=5)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["turn_id"], "turn_mock_1")
        # the Director actually answered the worker's request
        ans = dq.read_answer("STUB-1|turn_mock_1|item_1", base=self.qbase)
        self.assertIsNotNone(ans)
        self.assertEqual(ans["decision"], "accept")

    def test_main_report_ticket_returns_zero(self):
        # run.main now drives multi-turn; the `report` worker signals report_outcome(done)
        # so the autonomous decider returns a terminal disposition → rc 0.
        rc = run.main(["--ticket", str(self._ticket_path()), "--mock",
                       "--mock-scenario", "report", "--queue-dir", str(self.qbase)])
        self.assertEqual(rc, 0)

    def test_load_ticket_requires_id_and_prompt(self):
        bad = self.tmp / "bad.json"
        bad.write_text(json.dumps({"id": "X"}))  # no prompt
        with self.assertRaises(ValueError):
            run.load_ticket(bad)

    def test_install_workspace_skills(self):
        ws = self.tmp / "wsskills"
        run.install_workspace_skills(ws)
        self.assertTrue((ws / ".codex" / "skills" / "linear" / "SKILL.md").exists())
        self.assertTrue((ws / ".codex" / "skills" / "commit" / "SKILL.md").exists())
        self.assertTrue((ws / ".codex" / "skills" / "qa" / "SKILL.md").exists())  # M1
        run.install_workspace_skills(ws)  # idempotent re-run

    def test_run_ticket_threads_tools_and_executor(self):
        seen = []

        def texec(name, args):
            seen.append(name)
            return {"success": True, "output": "ok"}

        ticket = run.load_ticket(self._ticket_path())
        res = run.run_ticket(ticket, command=[sys.executable, MOCK, "tool"],
                             queue_base=self.qbase, workspace_root=self.tmp / "wsr2",
                             tools=[{"name": "linear_graphql", "description": "d",
                                     "inputSchema": {"type": "object"}}],
                             tool_executor=texec)
        self.assertEqual(res["status"], "completed")
        self.assertEqual(seen, ["linear_graphql"])

    def test_run_ticket_threads_on_event_to_client(self):
        # Layer-2 M2: an on_event passed to run_ticket reaches the AppServerClient and
        # fires per notification — at least one carries usage extract_usage recognizes.
        # Proves the run.py→_prepare→AppServerClient on_event plumbing (the seam the
        # orchestrator binds its per-ticket usage marshal to).
        events = []
        ticket = run.load_ticket(self._ticket_path())
        res = run.run_ticket(ticket, command=[sys.executable, MOCK, "usage"],
                             queue_base=self.qbase, workspace_root=self.tmp / "wsr_ev",
                             on_event=lambda ev: events.append(ev))
        self.assertEqual(res["status"], "completed")
        self.assertTrue(events, "on_event should fire for the turn-stream notifications")
        self.assertTrue(
            any(extract_usage(e.get("method"), e.get("params", {})) is not None for e in events),
            "at least one streamed event should carry recognizable usage")

    def test_drive_threads_on_event_to_client(self):
        # Layer-2 M2 — the PRODUCTION path. The orchestrator dispatches via drive() (not
        # run_ticket), so live accrual binds on_event onto DRIVE's client. This guards
        # run.py's drive→_prepare on_event wiring: dropping it would break live accrual
        # yet leave the run_ticket test above green (review-code-quality P1).
        events = []
        ticket = run.load_ticket(self._ticket_path())
        disp = run.drive(ticket, command=[sys.executable, MOCK, "usage"],
                         queue_base=self.qbase, workspace_root=self.tmp / "wsr_drv",
                         on_event=lambda ev: events.append(ev))
        self.assertEqual(disp["kind"], "terminal")
        self.assertTrue(
            any(extract_usage(e.get("method"), e.get("params", {})) is not None for e in events),
            "drive must thread on_event to the client — the orchestrator's live-accrual seam")

    def test_install_skills_does_not_follow_symlink_target(self):
        # P1: a pre-existing symlinked skill target must not be written through.
        ws = self.tmp / "wssym"
        skills = ws / ".codex" / "skills"
        skills.mkdir(parents=True)
        outside = self.tmp / "outside_dir"
        outside.mkdir()
        (skills / "linear").symlink_to(outside, target_is_directory=True)
        run.install_workspace_skills(ws)
        self.assertFalse((skills / "linear").is_symlink())  # replaced by a real dir
        self.assertTrue((skills / "linear" / "SKILL.md").exists())
        self.assertEqual(list(outside.iterdir()), [])  # nothing leaked outside

    def test_install_skills_refuses_symlinked_parent(self):
        ws = self.tmp / "wssym2"
        ws.mkdir()
        outside = self.tmp / "outside2"
        outside.mkdir()
        (ws / ".codex").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(RuntimeError):
            run.install_workspace_skills(ws)


class WorkspaceSafetyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_workspace_key_sanitizes_unsafe_chars(self):
        # slash + space → _; alnum/./-/_ preserved (Symphony §9.5 invariant 3)
        self.assertEqual(run.workspace_key("feat/ABC XY"), "feat_ABC_XY")
        self.assertEqual(run.workspace_key("LIN-22"), "LIN-22")
        self.assertEqual(run.workspace_key("a.b_c-1"), "a.b_c-1")
        # '.' is in the allowed set, so '..' SURVIVES sanitization (containment, not the
        # sanitizer, blocks the escape — see the derived-'..' test below)
        self.assertEqual(run.workspace_key(".."), "..")

    def test_workspace_path_is_root_plus_sanitized_key(self):
        p = run.workspace_path("a/b", self.tmp)
        self.assertEqual(p, self.tmp / "a_b")

    def test_derived_workspace_contained_under_root(self):
        ws, created = run._workspace_for({"id": "ABC-1"}, self.tmp)
        self.assertEqual(ws, self.tmp / "ABC-1")
        self.assertTrue(ws.is_dir())
        self.assertTrue(created)  # brand-new dir → created_now True (drives after_create)

    def test_derived_path_escaping_root_raises(self):
        # a derived id that resolves outside the root (e.g. '..') is rejected before mkdir
        with self.assertRaises(RuntimeError):
            run._workspace_for({"id": ".."}, self.tmp / "root")

    def test_derived_id_resolving_to_root_itself_raises(self):
        # a degenerate id ('.' / '') resolves to the ROOT itself — strict containment
        # rejects it so cleanup can never rmtree the whole root (security/spec P1)
        for degenerate in (".", ""):
            with self.assertRaises(RuntimeError):
                run._workspace_for({"id": degenerate}, self.tmp / "root")

    def test_is_contained_is_strict_descendant(self):
        root = self.tmp / "root"
        self.assertFalse(run.is_contained(root, root))             # root itself: NOT contained
        self.assertFalse(run.is_contained(root / "..", root))      # parent: NOT contained
        self.assertTrue(run.is_contained(root / "abc", root))      # a child: contained
        self.assertTrue(run.is_contained(root / "a" / "b", root))  # a descendant: contained

    def test_explicit_workspace_override_is_exempt_from_containment(self):
        # the trusted single-ticket-CLI/test affordance may target an arbitrary path
        outside = self.tmp / "outside"
        ws, _ = run._workspace_for({"id": "X", "workspace": str(outside)}, self.tmp / "root")
        self.assertEqual(ws, outside)
        self.assertTrue(ws.is_dir())

    def test_dispatch_and_merge_enqueue_agree_on_path(self):
        # _maybe_enqueue_merge derives the same path as _workspace_for (one helper, R2c)
        import director.orchestrator as orch
        root = self.tmp / "wsroot"
        derived, _ = run._workspace_for({"id": "feat/Z 1"}, root)
        errs = []
        orch._maybe_enqueue_merge("feat/Z 1", {"id": "feat/Z 1"},
                                  {"status": "done", "pr_url": "http://pr"},
                                  self.tmp / "q", root, errs)
        # the helper-derived path equals what dispatch created
        self.assertEqual(run.workspace_path("feat/Z 1", root), derived)


class WorkspaceHookTest(unittest.TestCase):
    """R4 workspace lifecycle hooks: run_hook + the create/run/after_run wiring."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = self.tmp / "ws"
        self.ws.mkdir()

    # -- run_hook unit behavior --
    def test_falsy_script_is_noop(self):
        run.run_hook("x", None, cwd=self.ws, timeout_s=5, fatal=True)  # must not raise
        run.run_hook("x", "", cwd=self.ws, timeout_s=5, fatal=True)

    def test_runs_in_workspace_cwd(self):
        run.run_hook("x", "touch marker", cwd=self.ws, timeout_s=5, fatal=True)
        self.assertTrue((self.ws / "marker").exists())

    def test_nonzero_exit_fatal_raises_nonfatal_swallows(self):
        with self.assertRaises(RuntimeError):
            run.run_hook("x", "exit 3", cwd=self.ws, timeout_s=5, fatal=True)
        run.run_hook("x", "exit 3", cwd=self.ws, timeout_s=5, fatal=False)  # swallowed

    def test_timeout_fatal_raises_nonfatal_swallows(self):
        with self.assertRaises(RuntimeError):
            run.run_hook("x", "sleep 5", cwd=self.ws, timeout_s=0.3, fatal=True)
        run.run_hook("x", "sleep 5", cwd=self.ws, timeout_s=0.3, fatal=False)  # swallowed

    def test_launch_failure_is_total(self):
        # a vanished cwd (concurrent-session delete) → OSError on launch: a non-fatal hook
        # MUST swallow it (R8 — never crash the reap loop / daemon), a fatal hook raises.
        missing = self.tmp / "vanished"  # does not exist
        run.run_hook("before_remove", "echo hi", cwd=missing, timeout_s=5, fatal=False)
        with self.assertRaises(RuntimeError):
            run.run_hook("after_create", "echo hi", cwd=missing, timeout_s=5, fatal=True)

    # -- _prepare lifecycle (create / run), no real worker --
    def _prepare(self, ticket, hooks):
        return run._prepare(ticket, command=["true"], queue_base=self.tmp / "q",
                            workspace_root=self.tmp / "root", timeout_s=5, read_timeout_s=5,
                            tool_executor=None, install_skills=False, worker_env={},
                            hooks=hooks, hook_timeout_s=5)

    def test_after_create_fatal_on_new_workspace(self):
        with self.assertRaises(RuntimeError):
            self._prepare({"id": "NEW-1"}, {"after_create": "exit 1"})

    def test_after_create_skipped_on_reuse(self):
        (self.tmp / "root" / "REUSE-1").mkdir(parents=True)  # pre-exists → created_now False
        # a failing after_create must NOT fire on reuse → _prepare succeeds (builds client)
        self._prepare({"id": "REUSE-1"}, {"after_create": "exit 1"})

    def test_after_create_populates_then_before_run(self):
        self._prepare({"id": "POP-1"}, {"after_create": "touch populated"})
        self.assertTrue((self.tmp / "root" / "POP-1" / "populated").exists())

    def test_before_run_fatal_every_prepare(self):
        with self.assertRaises(RuntimeError):
            self._prepare({"id": "BR-1"}, {"before_run": "exit 1"})

    # -- after_run fires through the real drive path (mock worker) --
    def test_after_run_fires_via_run_ticket(self):
        root = self.tmp / "root2"
        run.run_ticket({"id": "AR-1", "prompt": "do it"},
                       command=[sys.executable, MOCK, "plain"], queue_base=self.tmp / "q2",
                       workspace_root=root,
                       hooks={"after_create": "touch ac", "after_run": "touch ar"},
                       hook_timeout_s=5)
        self.assertTrue((root / "AR-1" / "ac").exists())   # after_create populated
        self.assertTrue((root / "AR-1" / "ar").exists())   # after_run fired post-attempt


if __name__ == "__main__":
    unittest.main()
