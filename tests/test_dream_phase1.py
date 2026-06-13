import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))
import dream_phase1 as p1
import memories_db as mdb

NOW = 1_000_000_000


def _transcript(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")


def _user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def _assistant(*blocks):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}


def _tool_result(text):
    return {"type": "user", "message": {"role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "x", "content": text}]}}


class TestRender(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.f = Path(self._tmp.name) / "t.jsonl"

    def tearDown(self):
        self._tmp.cleanup()

    def test_keeps_user_assistant_tools_drops_thinking_and_reminders(self):
        _transcript(self.f, [
            {"type": "queue-operation"},                         # ignored
            _user("real question <system-reminder>AGENTS noise</system-reminder> here"),
            _assistant({"type": "thinking", "thinking": "secret reasoning", "signature": "s"},
                       {"type": "text", "text": "my answer"},
                       {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}),
            _tool_result("file1\nfile2"),
        ])
        out = p1.render_rollout(self.f)
        self.assertIn("## User", out)
        self.assertIn("real question  here", out)               # reminder stripped
        self.assertNotIn("AGENTS noise", out)
        self.assertNotIn("secret reasoning", out)               # thinking dropped
        self.assertIn("## Assistant\nmy answer", out)
        self.assertIn("## Tool call: Bash", out)
        self.assertIn("## Tool result\nfile1", out)

    def test_empty_transcript_renders_empty(self):
        _transcript(self.f, [{"type": "queue-operation"}, {"type": "attachment"}])
        self.assertEqual(p1.render_rollout(self.f), "")

    def test_missing_file_renders_empty(self):
        self.assertEqual(p1.render_rollout(self.f / "nope.jsonl"), "")

    def test_tail_kept_when_over_cap(self):
        _transcript(self.f, [_user("OLDEST"), _user("x" * 5000), _user("NEWEST")])
        out = p1.render_rollout(self.f, max_chars=200)
        self.assertIn("older turns truncated", out)
        self.assertIn("NEWEST", out)                            # recency kept
        self.assertNotIn("OLDEST", out)


class TestRedact(unittest.TestCase):
    def test_redacts_common_secret_shapes(self):
        for raw in ["AKIAABCDEFGHIJKLMNOP",
                    "ghp_" + "a" * 36,
                    "sk-ant-" + "A1b2" * 8,
                    "token: supersecretvalue",
                    "password=hunter2hunter"]:
            self.assertIn("[REDACTED_SECRET]", p1.redact_secrets(raw), raw)

    def test_keeps_key_name_redacts_only_value(self):
        out = p1.redact_secrets("api_key: abcdef123456")
        self.assertTrue(out.startswith("api_key:"))
        self.assertIn("[REDACTED_SECRET]", out)
        self.assertNotIn("abcdef123456", out)

    def test_conservative_no_false_positive_on_prose(self):
        self.assertEqual(p1.redact_secrets("the token: 0 was fine"),
                         "the token: 0 was fine")               # value < 6 chars


class TestParse(unittest.TestCase):
    def test_parses_plain_and_fenced(self):
        obj = {"rollout_summary": "s", "rollout_slug": "sl", "raw_memory": "m"}
        self.assertEqual(p1.parse_strict_json(json.dumps(obj)), obj)
        fenced = "```json\n" + json.dumps(obj) + "\n```"
        self.assertEqual(p1.parse_strict_json(fenced), obj)
        prosed = "Here you go:\n" + json.dumps(obj) + "\nDone."
        self.assertEqual(p1.parse_strict_json(prosed), obj)

    def test_missing_key_and_empty_raise(self):
        with self.assertRaises(ValueError):
            p1.parse_strict_json('{"rollout_summary":"s","raw_memory":"m"}')  # no slug
        with self.assertRaises(ValueError):
            p1.parse_strict_json("   ")
        with self.assertRaises(ValueError):
            p1.parse_strict_json("no json here")

    def test_coerces_null_slug_to_empty(self):
        out = p1.parse_strict_json(
            '{"rollout_summary":"s","rollout_slug":null,"raw_memory":"m"}')
        self.assertEqual(out["rollout_slug"], "")


class TestNoopAndPrompt(unittest.TestCase):
    def test_is_noop(self):
        self.assertTrue(p1.is_noop("", ""))
        self.assertTrue(p1.is_noop("  ", "\n"))
        self.assertFalse(p1.is_noop("x", ""))
        self.assertFalse(p1.is_noop("", "summary"))

    def test_render_prompt_survives_braces_in_contents(self):
        sys_t, in_t = p1.load_templates()
        # digest with literal braces (code) must not break .format framing
        prompt = p1.render_prompt(sys_t, in_t, "/p", "/cwd", 'def f(): return {"a": 1}')
        self.assertIn('def f(): return {"a": 1}', prompt)
        self.assertIn("rollout_path: /p", prompt)


class TestOrchestration(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.conn = mdb.connect(self.root)
        self.f = self.root / "t.jsonl"
        _transcript(self.f, [_user("do the thing"), _assistant({"type": "text", "text": "done"})])
        self.templates = ("SYS", "{rollout_path}|{rollout_cwd}|{rollout_contents}")

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def _run(self, spawn):
        # claim first (the orchestrator's invariant: a jobs row exists before
        # extract_rollouts finishes it)
        src_ts = NOW - 86400
        tok = mdb.claim_stage1_job(self.conn, "tid1", "w", src_ts, 3600, NOW)
        claimed = [("tid1", self.f, src_ts, tok)]
        return p1.extract_rollouts(self.conn, self.root, claimed, "haiku", NOW,
                                   spawn=spawn, templates=self.templates)

    def test_high_signal_saves_row(self):
        def spawn(prompt, model):
            return json.dumps({"rollout_summary": "summ", "rollout_slug": "the-slug",
                               "raw_memory": "mem body"})
        res = self._run(spawn)
        self.assertEqual(res[0]["outcome"], "saved")
        row = self.conn.execute(
            "SELECT raw_memory, rollout_slug FROM stage1_outputs WHERE thread_id='tid1'"
        ).fetchone()
        self.assertEqual(row["raw_memory"], "mem body")
        self.assertEqual(row["rollout_slug"], "the-slug")

    def test_noop_saves_nothing(self):
        def spawn(prompt, model):
            return '{"rollout_summary":"","rollout_slug":"","raw_memory":""}'
        res = self._run(spawn)
        self.assertEqual(res[0]["outcome"], "no_output")
        self.assertIsNone(self.conn.execute(
            "SELECT 1 FROM stage1_outputs WHERE thread_id='tid1'").fetchone())
        # the job is marked done (success, no_output) — not a retryable failure
        job = self.conn.execute(
            "SELECT status FROM jobs WHERE kind=? AND job_key='tid1'",
            (mdb.STAGE1,)).fetchone()
        self.assertEqual(job["status"], "done")

    def test_bad_json_fails_and_backs_off(self):
        def spawn(prompt, model):
            return "I could not produce JSON, sorry."
        res = self._run(spawn)
        self.assertEqual(res[0]["outcome"], "failed")
        self.assertIsNone(self.conn.execute(
            "SELECT 1 FROM stage1_outputs WHERE thread_id='tid1'").fetchone())
        job = self.conn.execute(
            "SELECT status, retry_at FROM jobs WHERE kind=? AND job_key='tid1'",
            (mdb.STAGE1,)).fetchone()
        self.assertEqual(job["status"], "error")
        self.assertIsNotNone(job["retry_at"])                  # backoff scheduled

    def test_output_secrets_redacted_before_store(self):
        def spawn(prompt, model):
            return json.dumps({"rollout_summary": "saw ghp_" + "b" * 36,
                               "rollout_slug": "s", "raw_memory": "key sk-ant-" + "C3d4" * 8})
        self._run(spawn)
        row = self.conn.execute(
            "SELECT raw_memory, rollout_summary FROM stage1_outputs WHERE thread_id='tid1'"
        ).fetchone()
        self.assertIn("[REDACTED_SECRET]", row["raw_memory"])
        self.assertIn("[REDACTED_SECRET]", row["rollout_summary"])


if __name__ == "__main__":
    unittest.main()
