import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.queue as dq  # noqa: E402
import director.director_min as dmin  # noqa: E402
import director.run as run  # noqa: E402
from director.worker.app_server import ReadTimeout, extract_usage  # noqa: E402

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

    def test_main_accepts_worker_codex(self):
        # --worker codex is wired and resolves the default runtime; --mock still runs.
        rc = run.main(["--ticket", str(self._ticket_path()), "--mock",
                       "--mock-scenario", "report", "--queue-dir", str(self.qbase),
                       "--worker", "codex"])
        self.assertEqual(rc, 0)

    def test_main_unknown_worker_runtime_fails_loud(self):
        # a typo'd --worker must fail loud BEFORE dispatch, not silently run the default.
        with self.assertRaises(ValueError):
            run.main(["--ticket", str(self._ticket_path()), "--mock",
                      "--mock-scenario", "report", "--queue-dir", str(self.qbase),
                      "--worker", "nope"])

    def test_load_ticket_requires_id_and_prompt(self):
        bad = self.tmp / "bad.json"
        bad.write_text(json.dumps({"id": "X"}))  # no prompt
        with self.assertRaises(ValueError):
            run.load_ticket(bad)

    def test_install_worker_methodology(self):
        ws = self.tmp / "wsskills"
        run.install_worker_methodology(ws)
        # SKILLS land where each runtime's loader scans: Claude=.claude/skills, Codex=.agents/
        # skills (the real Codex CLI never reads .codex/skills).
        for sdir in (".claude/skills", ".agents/skills"):
            # workspace plugin (agent-harness-workspace): git/PR/Linear skills.
            self.assertTrue((ws / sdir / "linear" / "SKILL.md").exists())
            self.assertTrue((ws / sdir / "commit" / "SKILL.md").exists())
            self.assertTrue((ws / sdir / "push" / "SKILL.md").exists())
            # methodology plugin (agent-harness): the skills a worker INVOKES, alongside
            # the workspace skills in the same skills/ dir (disjoint name-sets).
            self.assertTrue((ws / sdir / "execplan" / "SKILL.md").exists())
            self.assertTrue((ws / sdir / "product-design" / "SKILL.md").exists())
            # Slice 4 R4.3: the standalone `qa` skill was retired (redundant with the
            # execplan completion gate); it must no longer be installed into a worker.
            self.assertFalse((ws / sdir / "qa").exists())
        self.assertFalse((ws / ".codex" / "skills").exists())  # inert path dropped (M1)
        # AGENTS — the review/gardener personas a worker DISPATCHES at its completion gate
        # (a runtime registers agents only from its own agents/ dir, never a repo path), each
        # in its native format: Claude reads .claude/agents/*.md, Codex reads .codex/agents/*.toml.
        # Claude keeps the hyphenated .md name; the Codex .toml uses the sanitized
        # (underscore) name — Codex's spawn tool rejects hyphens (F1, codex-cli 0.142).
        for md_name in ("review-spec-compliance", "review-arch", "doc-gardener"):
            self.assertTrue((ws / ".claude" / "agents" / f"{md_name}.md").exists())
            codex_name = run._codex_agent_name(md_name)
            self.assertTrue((ws / ".codex" / "agents" / f"{codex_name}.toml").exists())
        # The Codex side is TOML, not the inert .md (which Codex never loads).
        self.assertFalse((ws / ".codex" / "agents" / "review_arch.md").exists())
        run.install_worker_methodology(ws)  # idempotent re-run

    def test_codex_agent_toml_translation_round_trips(self):
        # M2: each .md persona is translated to a Codex custom-agent .toml that an independent
        # TOML parser accepts, with the three required keys + a tools-derived sandbox_mode and
        # the body preserved verbatim as developer_instructions.
        import tomllib
        ws = self.tmp / "wstoml"
        run.install_worker_methodology(ws)
        # The codex file + its `name` field both use the SANITIZED name (hyphens → underscores)
        # — Codex's spawn tool rejects a hyphenated agent_name (live, codex-cli 0.142).
        data = tomllib.loads(
            (ws / ".codex" / "agents" / "review_security.toml").read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "review_security")
        self.assertTrue(data["description"])
        self.assertEqual(data["sandbox_mode"], "read-only")  # Read/Grep/Glob/Bash → read-only
        self.assertIn("security", data["developer_instructions"].lower())
        src = (Path(run.__file__).resolve().parent.parent / "plugin" / "agents"
               / "review-security.md").read_text(encoding="utf-8")
        _, body = run._parse_agent_frontmatter(src)
        self.assertEqual(data["developer_instructions"].rstrip("\n"), body.rstrip("\n"))
        # doc-gardener carries Edit/Write → workspace-write (file: doc_gardener.toml).
        gardener = tomllib.loads(
            (ws / ".codex" / "agents" / "doc_gardener.toml").read_text(encoding="utf-8"))
        self.assertEqual(gardener["sandbox_mode"], "workspace-write")
        self.assertEqual(gardener["name"], "doc_gardener")

    def test_codex_agent_names_are_spawnable_charset(self):
        # F1 regression guard: EVERY translated persona name must match Codex's spawn-tool
        # charset `^[a-z0-9_]+$` (hyphens are rejected at spawn) AND equal _codex_agent_name of
        # the source. Without this the codex worker's completion-gate personas are unspawnable.
        import tomllib
        ws = self.tmp / "wscharset"
        run.install_worker_methodology(ws)
        src_dir = Path(run.__file__).resolve().parent.parent / "plugin" / "agents"
        names = [p.stem for p in src_dir.glob("*.md")]
        self.assertTrue(names)
        for md_name in names:
            codex_name = run._codex_agent_name(md_name)
            self.assertRegex(codex_name, r"^[a-z0-9_]+$")
            data = tomllib.loads(
                (ws / ".codex" / "agents" / f"{codex_name}.toml").read_text(encoding="utf-8"))
            self.assertEqual(data["name"], codex_name)
        # the mapping is exactly hyphen→underscore for our personas
        self.assertEqual(run._codex_agent_name("review-spec-compliance"), "review_spec_compliance")

    def test_with_codex_trust_appends_for_bash_runtime(self):
        # M3: the bash-wrapped real runtime gets -c projects."<ws>".trust_level="trusted" so
        # Codex loads the vendored project .codex/ layer; prior -c overrides are preserved.
        import shlex
        ws = self.tmp / "wstrust"
        cmd = ["bash", "-c", "codex app-server -c approvals_reviewer=auto_review"]
        out = run._with_codex_trust(cmd, ws)
        self.assertEqual(out[:2], ["bash", "-c"])
        # realpath (not abspath): the key must match the canonical path Codex resolves the
        # project root to, or trust silently fails on a symlinked workspace-root component.
        real_ws = os.path.realpath(str(ws))
        self.assertIn("-c approvals_reviewer=auto_review", out[2])  # preserved
        # bash re-tokenizes the appended fragment to the EXACT TOML kv (quotes pass literally
        # to codex's -c parser — the quoting that the live probe confirmed codex accepts).
        self.assertEqual(shlex.split(out[2])[-1],
                         f'projects."{real_ws}".trust_level="trusted"')

    def test_with_codex_trust_leaves_mock_unchanged(self):
        # The mock command is not `bash -c …`, so trust must not corrupt it.
        cmd = [sys.executable, MOCK, "plain"]
        self.assertEqual(run._with_codex_trust(cmd, self.tmp / "x"), cmd)

    def test_translate_agent_guards_fail_loud(self):
        # The parse/translate guards must fail LOUD on a malformed first-party persona
        # (fail before any worker spawn — never emit silently-broken TOML).
        with self.assertRaises(RuntimeError):
            run._parse_agent_frontmatter("no opening fence\n")
        with self.assertRaises(RuntimeError):
            run._parse_agent_frontmatter("---\nname: x\n(never closed)\n")
        noname = self.tmp / "noname.md"
        noname.write_text("---\ndescription: d\n---\nbody\n", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            run._translate_agent_md_to_toml(noname)
        triple = self.tmp / "triple.md"
        triple.write_text("---\nname: n\ndescription: d\n---\nhas ''' inside\n", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            run._translate_agent_md_to_toml(triple)

    def test_translate_agent_body_ending_in_apostrophe_is_parseable(self):
        # closing-fence robustness: a body ending in apostrophes with no trailing newline
        # must still emit TOML an independent parser accepts.
        import tomllib
        p = self.tmp / "apos.md"
        p.write_text("---\nname: n\ndescription: d\ntools: Read\n---\nends in two''",
                     encoding="utf-8")
        data = tomllib.loads(run._translate_agent_md_to_toml(p))
        self.assertEqual(data["developer_instructions"].rstrip("\n"), "ends in two''")

    def test_install_recovers_from_planted_file_at_dest_dir(self):
        # reliability: a prior workspace-write worker plants a regular FILE where a dest dir
        # must go; the idempotent re-run clears it rather than crashing on mkdir.
        ws = self.tmp / "wsplanted"
        (ws / ".codex").mkdir(parents=True)
        (ws / ".codex" / "agents").write_text("planted\n", encoding="utf-8")
        run.install_worker_methodology(ws)  # must not raise
        self.assertTrue((ws / ".codex" / "agents").is_dir())
        self.assertTrue((ws / ".codex" / "agents" / "review_arch.toml").exists())

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
        skills = ws / ".agents" / "skills"
        skills.mkdir(parents=True)
        outside = self.tmp / "outside_dir"
        outside.mkdir()
        (skills / "linear").symlink_to(outside, target_is_directory=True)
        run.install_worker_methodology(ws)
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
            run.install_worker_methodology(ws)

    def test_install_methodology_excludes_injected_from_worker_git(self):
        # PR hygiene: a worker that runs `git add -A` must not stage the Director-injected
        # methodology. install writes the skill roots to the clone's .git/info/exclude
        # (uncommitted, touches no tracked file). The bare-dir test above already proves
        # install still succeeds when there's no git dir.
        ws = self.tmp / "wsgit"
        (ws / ".git" / "info").mkdir(parents=True)
        run.install_worker_methodology(ws)
        lines = (ws / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()
        # Every injected dir is excluded — both skill dests AND both agent dests.
        for pat in ("/.claude/skills/", "/.agents/skills/",
                    "/.claude/agents/", "/.codex/agents/"):
            self.assertIn(pat, lines)
        run.install_worker_methodology(ws)  # idempotent: no duplicate patterns
        lines2 = (ws / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines2.count("/.claude/skills/"), 1)
        self.assertEqual(lines2.count("/.claude/agents/"), 1)

    def test_install_refuses_symlinked_git_exclude(self):
        # Hardening (codex review): the PR-hygiene exclude write must not follow a symlink
        # any more than the skill/agent copy does — a prior sandboxed worker that symlinks
        # `.git/info/exclude` outside the workspace must not redirect the Director's write.
        ws = self.tmp / "wsgitsym"
        (ws / ".git" / "info").mkdir(parents=True)
        outside = self.tmp / "outside_exclude"
        outside.write_text("SENTINEL\n", encoding="utf-8")
        (ws / ".git" / "info" / "exclude").symlink_to(outside)
        with self.assertRaises(RuntimeError):
            run.install_worker_methodology(ws)
        # the outside file was NOT written through (still the sentinel)
        self.assertEqual(outside.read_text(encoding="utf-8"), "SENTINEL\n")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires os.mkfifo (POSIX)")
    def test_install_replaces_special_node_target(self):
        # Hardening (codex review): a pre-existing special node (fifo/socket/device) at a
        # vendored target — neither file nor dir — must be removed before copy, or the
        # idempotent re-run breaks. A prior sandboxed worker could plant one.
        ws = self.tmp / "wsfifo"
        skills = ws / ".agents" / "skills"
        skills.mkdir(parents=True)
        os.mkfifo(skills / "linear")
        run.install_worker_methodology(ws)  # must not raise
        self.assertFalse((skills / "linear").is_fifo())
        self.assertTrue((skills / "linear" / "SKILL.md").exists())

    def test_install_refuses_colliding_vendored_sources(self):
        # Hardening (codex review): the two skill sources copy into the SAME dest dir, so
        # their entry names must be disjoint (they do today) — a future collision must fail
        # loud, not silently clobber. Drive it with two temp sources that share a name.
        srcA = self.tmp / "srcA"
        srcB = self.tmp / "srcB"
        (srcA / "dup").mkdir(parents=True)
        (srcB / "dup").mkdir(parents=True)
        with mock.patch.object(run, "_SKILL_SOURCES", (srcA, srcB)):
            with self.assertRaises(RuntimeError):
                run.install_worker_methodology(self.tmp / "wscollide")


class _ReadTimeoutClient:
    """A fake AppServerClient whose turn raises ReadTimeout — the worker went silent past
    the read budget (cold start / long command / deep reasoning). Context-manager + the
    handshake methods drive() calls; run_turn raises (use-all shakedown F3)."""
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def initialize(self): pass
    def thread_start(self, **kw): return "thread_1"
    def run_turn(self, *a, **kw): raise ReadTimeout("no app-server output within read timeout")


class _RateLimitedClient:
    """A fake client whose turn completes but carries an EXHAUSTED rate-limit payload
    (no credits) and an empty final_message — the real rate-limited symptom (F7)."""
    def __init__(self, rl): self._rl = rl
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def initialize(self): pass
    def thread_start(self, **kw): return "thread_1"
    def run_turn(self, *a, **kw):
        return {"status": "completed", "turn_id": "t1", "final_message": None,
                "usage": None, "rate_limits": self._rl}


class RateLimitParkTest(unittest.TestCase):
    def test_drive_parks_on_exhausted_credits(self):
        # F7: has_credits=False → park (escalate) instead of looping on empty turns.
        rl = {"limit_id": "premium", "credits": {"has_credits": False}}
        with mock.patch("director.run._prepare", return_value=_RateLimitedClient(rl)):
            disp = run.drive({"id": "RL-1", "prompt": "p"}, command=["x"],
                             workspace_root=Path("/tmp/unused-rl"), max_turns=5)
        self.assertEqual(disp["kind"], "escalate")
        self.assertIn("rate-limited", disp["reason"])

    def test_drive_parks_on_spent_primary_window(self):
        # camelCase usedPercent>=100 is also exhaustion.
        rl = {"primary": {"usedPercent": 100}}
        with mock.patch("director.run._prepare", return_value=_RateLimitedClient(rl)):
            disp = run.drive({"id": "RL-2", "prompt": "p"}, command=["x"],
                             workspace_root=Path("/tmp/unused-rl"), max_turns=5)
        self.assertEqual(disp["kind"], "escalate")

    def test_rate_limited_total_over_odd_shapes(self):
        # Total (R12): missing/odd payloads never falsely park.
        for rl in (None, {}, {"credits": None}, {"credits": {"has_credits": True}},
                   {"primary": {"usedPercent": 40}}, {"primary": "nope"}, "junk"):
            self.assertFalse(run._rate_limited(rl), rl)


class ReadTimeoutDispositionTest(unittest.TestCase):
    def test_drive_returns_failed_on_read_timeout(self):
        # F3: a ReadTimeout mid-turn must surface as a RECOVERABLE `failed` disposition
        # (so the orchestrator retries it like any failed turn), NOT an uncaught crash.
        # Pre-fix, drive() let ReadTimeout propagate and the whole ticket died with a
        # traceback — the real bug the canary shakedown hit on the first live worker.
        # _prepare is mocked, so workspace_root is never used (no fs touch).
        with mock.patch("director.run._prepare", return_value=_ReadTimeoutClient()):
            disp = run.drive({"id": "RT-1", "prompt": "p"}, command=["x"],
                             workspace_root=Path("/tmp/unused-rt"))
        self.assertEqual(disp["kind"], "failed")
        self.assertEqual(disp["status"], "read_timeout")
        self.assertIn("telemetry", disp)  # carries run facts like every other disposition


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
