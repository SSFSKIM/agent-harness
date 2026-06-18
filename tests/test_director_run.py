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
        ws = run._workspace_for({"id": "ABC-1"}, self.tmp)
        self.assertEqual(ws, self.tmp / "ABC-1")
        self.assertTrue(ws.is_dir())

    def test_derived_path_escaping_root_raises(self):
        # a derived id that resolves outside the root (e.g. '..') is rejected before mkdir
        with self.assertRaises(RuntimeError):
            run._workspace_for({"id": ".."}, self.tmp / "root")

    def test_explicit_workspace_override_is_exempt_from_containment(self):
        # the trusted single-ticket-CLI/test affordance may target an arbitrary path
        outside = self.tmp / "outside"
        ws = run._workspace_for({"id": "X", "workspace": str(outside)}, self.tmp / "root")
        self.assertEqual(ws, outside)
        self.assertTrue(ws.is_dir())

    def test_dispatch_and_merge_enqueue_agree_on_path(self):
        # _maybe_enqueue_merge derives the same path as _workspace_for (one helper, R2c)
        import director.orchestrator as orch
        root = self.tmp / "wsroot"
        derived = run._workspace_for({"id": "feat/Z 1"}, root)
        errs = []
        orch._maybe_enqueue_merge("feat/Z 1", {"id": "feat/Z 1"},
                                  {"status": "done", "pr_url": "http://pr"},
                                  self.tmp / "q", root, errs)
        # the helper-derived path equals what dispatch created
        self.assertEqual(run.workspace_path("feat/Z 1", root), derived)


if __name__ == "__main__":
    unittest.main()
