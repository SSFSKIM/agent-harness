import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.worker.tools as tools  # noqa: E402


def _executor(resp, key="lin_key", captured=None):
    def post(url, data, headers):
        if captured is not None:
            captured["url"] = url
            captured["data"] = data
            captured["headers"] = headers
        return resp
    return tools.make_linear_tool_executor(api_key=key, http_post=post)


class LinearToolTest(unittest.TestCase):
    def test_success_returns_data(self):
        cap = {}
        ex = _executor({"data": {"viewer": {"id": "u1"}}}, captured=cap)
        r = ex("linear_graphql", {"query": "query { viewer { id } }"})
        self.assertTrue(r["success"])
        self.assertIn("u1", r["output"])
        self.assertEqual(cap["headers"]["Authorization"], "lin_key")
        self.assertEqual(cap["headers"]["Content-Type"], "application/json")

    def test_graphql_errors_is_failure(self):
        ex = _executor({"errors": [{"message": "bad mutation"}]})
        r = ex("linear_graphql", {"query": "mutation { x }"})
        self.assertFalse(r["success"])
        self.assertIn("bad mutation", r["output"])

    def test_unsupported_tool(self):
        ex = _executor({})
        self.assertFalse(ex("other_tool", {})["success"])

    def test_missing_query(self):
        ex = _executor({"data": {}})
        self.assertFalse(ex("linear_graphql", {})["success"])

    def test_missing_key(self):
        with mock.patch("director.board.linear.load_api_key", return_value=None):
            ex = tools.make_linear_tool_executor(api_key=None, http_post=lambda u, d, h: {})
            self.assertFalse(ex("linear_graphql", {"query": "x"})["success"])

    def test_spec_shape(self):
        s = tools.linear_graphql_spec()
        self.assertEqual(s["name"], "linear_graphql")
        self.assertIn("query", s["inputSchema"]["required"])


if __name__ == "__main__":
    unittest.main()
