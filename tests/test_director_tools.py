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
        # allowlisted mutation so it reaches the (mocked) server, which returns errors
        ex = _executor({"errors": [{"message": "bad mutation"}]})
        r = ex("linear_graphql", {"query": "mutation { issueCreate(input:{title:\"t\"}) { id } }"})
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


class GuardrailWiringTest(unittest.TestCase):
    """The authority guardrail is wired into the executor (spec R3/R7/D-28)."""

    def _counting_executor(self, calls, *, guard=True, allow_mutations=None):
        def post(url, data, headers):
            calls.append(1)
            return {"data": {"ok": True}}
        return tools.make_linear_tool_executor(
            api_key="k", http_post=post, guard=guard, allow_mutations=allow_mutations)

    def test_destructive_mutation_refused_without_post(self):
        calls = []
        ex = self._counting_executor(calls)
        r = ex("linear_graphql", {"query": 'mutation { issueDelete(id: "x") { success } }'})
        self.assertFalse(r["success"])
        self.assertIn("issueDelete", r["output"])
        self.assertIn("guardrail", r["output"])
        self.assertEqual(calls, [])  # never reached the network

    def test_allowed_mutation_reaches_post(self):
        calls = []
        ex = self._counting_executor(calls)
        r = ex("linear_graphql", {"query": "mutation { issueCreate(input:{title:\"t\"}) { id } }"})
        self.assertTrue(r["success"])
        self.assertEqual(calls, [1])

    def test_read_reaches_post(self):
        calls = []
        ex = self._counting_executor(calls)
        ex("linear_graphql", {"query": "query { issues { nodes { id } } }"})
        self.assertEqual(calls, [1])

    def test_default_guard_is_on(self):
        # no explicit guard= : run.py / orchestrator.py call the factory exactly like
        # this (make_linear_tool_executor()), so the default must refuse a delete.
        calls = []
        ex = tools.make_linear_tool_executor(
            api_key="k", http_post=lambda u, d, h: calls.append(1) or {"data": {}})
        r = ex("linear_graphql", {"query": "mutation { issueDelete(id: 1) { success } }"})
        self.assertFalse(r["success"])
        self.assertEqual(calls, [])

    def test_guard_false_opts_out(self):
        calls = []
        ex = self._counting_executor(calls, guard=False)
        r = ex("linear_graphql", {"query": "mutation { issueDelete(id: 1) { success } }"})
        self.assertTrue(r["success"])
        self.assertEqual(calls, [1])

    def test_custom_allowlist_tightens(self):
        calls = []
        ex = self._counting_executor(calls, allow_mutations=frozenset({"commentCreate"}))
        r = ex("linear_graphql", {"query": "mutation { issueUpdate(id: 1) { id } }"})
        self.assertFalse(r["success"])
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
