import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.board.linear as linear  # noqa: E402
import director.run as run  # noqa: E402

_ISSUE = {"id": "uuid-1", "identifier": "ABC-123", "title": "Add a health check",
          "description": "Return 200 OK at /health.", "state": {"name": "Todo"}}


def _fake_post(captured):
    def post(url, data, headers):
        captured["url"] = url
        captured["headers"] = headers
        captured["data"] = data
        return {"data": {"issue": _ISSUE}}
    return post


class LinearAdapterTest(unittest.TestCase):
    def test_read_issue_normalizes_and_builds_prompt(self):
        cap = {}
        ticket = linear.read_issue("ABC-123", api_key="lin_key",
                                   http_post=_fake_post(cap))
        self.assertEqual(ticket["id"], "uuid-1")
        self.assertEqual(ticket["identifier"], "ABC-123")
        self.assertEqual(ticket["state"], "Todo")
        self.assertIn("Add a health check", ticket["prompt"])
        self.assertIn("Return 200 OK", ticket["prompt"])
        # raw API key in Authorization header (no "Bearer"), JSON content type
        self.assertEqual(cap["headers"]["Authorization"], "lin_key")
        self.assertEqual(cap["headers"]["Content-Type"], "application/json")

    def test_read_issue_raises_on_graphql_errors(self):
        def post(url, data, headers):
            return {"errors": [{"message": "boom"}]}
        with self.assertRaises(RuntimeError):
            linear.read_issue("X", api_key="k", http_post=post)

    def test_read_issue_raises_when_missing(self):
        def post(url, data, headers):
            return {"data": {"issue": None}}
        with self.assertRaises(RuntimeError):
            linear.read_issue("nope", api_key="k", http_post=post)

    def test_load_api_key_from_env_file(self):
        d = Path(tempfile.mkdtemp())
        (d / ".env").write_text('FOO=1\nLINEAR_API_KEY="lin_abc"\n')
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(linear.load_api_key(d / ".env"), "lin_abc")

    def test_run_main_linear_path_builds_ticket(self):
        # --linear path: read_issue is mocked; the mock worker runs the turn.
        with mock.patch("director.board.linear.read_issue",
                        return_value={"identifier": "ABC-9", "prompt": "do it"}):
            with tempfile.TemporaryDirectory() as q:
                rc = run.main(["--linear", "ABC-9", "--mock",
                               "--mock-scenario", "plain", "--queue-dir", q])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
