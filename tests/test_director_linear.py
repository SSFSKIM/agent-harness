import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.board.linear as linear  # noqa: E402
import director.run as run  # noqa: E402


def _capturing_post(captured, response):
    """A fake http_post that records the decoded GraphQL body and returns `response`."""
    def post(url, data, headers):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = json.loads(data.decode("utf-8"))
        return response
    return post

def _paged_post(pages, captured=None):
    """A fake http_post returning successive page responses (pagination tests): each
    call pops the next response in `pages`, recording every request body in
    `captured["bodies"]` when given."""
    seq = list(pages)
    n = {"i": 0}

    def post(url, data, headers):
        if captured is not None:
            captured.setdefault("bodies", []).append(json.loads(data.decode("utf-8")))
        resp = seq[n["i"]]
        n["i"] += 1
        return resp
    return post


def _page(nodes, *, has_next=False, cursor=None):
    """A one-page `issues` connection response with pageInfo."""
    return {"data": {"issues": {"nodes": nodes,
                                "pageInfo": {"hasNextPage": has_next, "endCursor": cursor}}}}


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
                               "--mock-scenario", "report", "--queue-dir", q])
        self.assertEqual(rc, 0)


class LinearWriteMethodsTest(unittest.TestCase):
    def test_workflow_states_maps_name_to_id_and_type(self):
        cap = {}
        resp = {"data": {"team": {"states": {"nodes": [
            {"id": "s1", "name": "Todo", "type": "unstarted"},
            {"id": "s2", "name": "Done", "type": "completed"}]}}}}
        states = linear.workflow_states("team-1", api_key="k",
                                        http_post=_capturing_post(cap, resp))
        self.assertEqual(states["Todo"], {"id": "s1", "type": "unstarted"})
        self.assertEqual(states["Done"]["id"], "s2")
        self.assertEqual(cap["body"]["variables"], {"id": "team-1"})
        self.assertIn("team(id:", cap["body"]["query"].replace(" ", ""))

    def test_list_ready_issues_normalizes_with_state_id(self):
        cap = {}
        resp = {"data": {"issues": {"nodes": [
            {"id": "u1", "identifier": "ABC-1", "title": "T1", "description": "d1",
             "state": {"id": "s1", "name": "Todo"}}]}}}
        out = linear.list_ready_issues("team-1", "s1", api_key="k",
                                       http_post=_capturing_post(cap, resp))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], "u1")
        self.assertEqual(out[0]["identifier"], "ABC-1")
        self.assertEqual(out[0]["state_id"], "s1")
        self.assertIn("T1", out[0]["prompt"])
        self.assertEqual(cap["body"]["variables"],
                         {"team": "team-1", "state": "s1", "after": None})

    def test_list_ready_issues_parses_labels(self):
        cap = {}
        resp = {"data": {"issues": {"nodes": [
            {"id": "u1", "identifier": "ABC-1", "title": "T", "description": "d",
             "state": {"id": "s1", "name": "Todo"},
             "labels": {"nodes": [{"name": "spec"}, {"name": "Feature"}]}}]}}}
        out = linear.list_ready_issues("team-1", "s1", api_key="k",
                                       http_post=_capturing_post(cap, resp))
        self.assertEqual(out[0]["labels"], ["spec", "Feature"])
        self.assertIn("labels", cap["body"]["query"])

    def test_list_ready_issues_parses_blockers(self):
        cap = {}
        resp = {"data": {"issues": {"nodes": [
            {"id": "u2", "identifier": "ABC-2", "title": "T2", "description": "d2",
             "state": {"id": "s1", "name": "Todo"},
             "inverseRelations": {"nodes": [
                 {"type": "blocks",
                  "issue": {"id": "u1", "state": {"id": "s0", "name": "Todo",
                                                  "type": "unstarted"}}},
                 {"type": "related",  # must be ignored — not a blocker
                  "issue": {"id": "u9", "state": {"type": "completed"}}}]}}]}}}
        out = linear.list_ready_issues("team-1", "s1", api_key="k",
                                       http_post=_capturing_post(cap, resp))
        self.assertEqual(out[0]["blockers"], [{"id": "u1", "state_type": "unstarted"}])
        self.assertIn("inverseRelations", cap["body"]["query"])

    def test_update_issue_state_returns_success(self):
        cap = {}
        resp = {"data": {"issueUpdate": {"success": True}}}
        ok = linear.update_issue_state("u1", "s2", api_key="k",
                                       http_post=_capturing_post(cap, resp))
        self.assertTrue(ok)
        self.assertEqual(cap["body"]["variables"], {"id": "u1", "state": "s2"})
        self.assertIn("issueUpdate", cap["body"]["query"])

    def test_comment_issue_returns_success_and_sends_body(self):
        cap = {}
        resp = {"data": {"commentCreate": {"success": True}}}
        ok = linear.comment_issue("u1", "✅ done", api_key="k",
                                  http_post=_capturing_post(cap, resp))
        self.assertTrue(ok)
        self.assertEqual(cap["body"]["variables"], {"id": "u1", "body": "✅ done"})

    def test_write_methods_raise_on_graphql_errors(self):
        def post(url, data, headers):
            return {"errors": [{"message": "nope"}]}
        with self.assertRaises(RuntimeError):
            linear.update_issue_state("u1", "s2", api_key="k", http_post=post)

    def test_fetch_issue_states_by_ids_normalizes(self):
        cap = {}
        resp = {"data": {"issues": {"nodes": [
            {"id": "u1", "state": {"id": "s2", "name": "Done", "type": "completed"}},
            {"id": "u2", "state": {"id": "s1", "name": "In Progress", "type": "started"}}]}}}
        out = linear.fetch_issue_states_by_ids(["u1", "u2"], api_key="k",
                                               http_post=_capturing_post(cap, resp))
        self.assertEqual(out["u1"], {"state_id": "s2", "state_name": "Done",
                                     "state_type": "completed"})
        self.assertEqual(out["u2"]["state_type"], "started")
        self.assertEqual(cap["body"]["variables"], {"ids": ["u1", "u2"]})
        self.assertIn("issues(filter:", cap["body"]["query"].replace(" ", ""))

    def test_fetch_issue_states_by_ids_empty_makes_no_call(self):
        def boom(url, data, headers):
            raise AssertionError("http_post must not be called for empty ids")
        self.assertEqual(linear.fetch_issue_states_by_ids([], api_key="k", http_post=boom), {})

    def test_fetch_issue_states_by_ids_omits_unknown(self):
        # an id absent from the response is simply not in the map (caller stays conservative)
        resp = {"data": {"issues": {"nodes": [
            {"id": "u1", "state": {"id": "s1", "name": "Todo", "type": "unstarted"}}]}}}
        out = linear.fetch_issue_states_by_ids(["u1", "ghost"], api_key="k",
                                               http_post=_capturing_post({}, resp))
        self.assertIn("u1", out)
        self.assertNotIn("ghost", out)

    def test_fetch_issue_labels_by_ids_normalizes(self):
        cap = {}
        resp = {"data": {"issues": {"nodes": [
            {"id": "u1", "labels": {"nodes": [{"name": "agent-ready"}, {"name": "Bug"}]}},
            {"id": "u2", "labels": {"nodes": []}}]}}}
        out = linear.fetch_issue_labels_by_ids(["u1", "u2"], api_key="k",
                                               http_post=_capturing_post(cap, resp))
        self.assertEqual(out["u1"], ["agent-ready", "Bug"])
        self.assertEqual(out["u2"], [])                       # exists, no labels
        self.assertEqual(cap["body"]["variables"], {"ids": ["u1", "u2"]})
        self.assertIn("issues(filter:", cap["body"]["query"].replace(" ", ""))

    def test_fetch_issue_labels_by_ids_empty_makes_no_call(self):
        def boom(url, data, headers):
            raise AssertionError("http_post must not be called for empty ids")
        self.assertEqual(linear.fetch_issue_labels_by_ids([], api_key="k", http_post=boom), {})

    def test_fetch_issue_labels_by_ids_omits_unknown(self):
        # a missing id is absent from the map → the caller reads that as "ticket does not exist"
        resp = {"data": {"issues": {"nodes": [
            {"id": "u1", "labels": {"nodes": [{"name": "agent-ready"}]}}]}}}
        out = linear.fetch_issue_labels_by_ids(["u1", "ghost"], api_key="k",
                                               http_post=_capturing_post({}, resp))
        self.assertEqual(out, {"u1": ["agent-ready"]})
        self.assertNotIn("ghost", out)

    def test_linear_board_binds_key_and_delegates(self):
        cap = {}
        resp = {"data": {"issues": {"nodes": []}}}
        board = linear.LinearBoard(api_key="bound", http_post=_capturing_post(cap, resp))
        out = board.list_ready_issues("team-1", "s1")
        self.assertEqual(out, [])
        self.assertEqual(cap["headers"]["Authorization"], "bound")


class PaginationTest(unittest.TestCase):
    def _node(self, uid, ident):
        return {"id": uid, "identifier": ident, "title": ident, "description": "d",
                "state": {"id": "s1", "name": "Todo"}}

    def test_list_ready_issues_paginates_in_order(self):
        cap = {}
        pages = [_page([self._node("u1", "A-1")], has_next=True, cursor="c1"),
                 _page([self._node("u2", "A-2")], has_next=False)]
        out = linear.list_ready_issues("team-1", "s1", api_key="k",
                                       http_post=_paged_post(pages, cap))
        # all nodes from both pages, in fetch order
        self.assertEqual([t["id"] for t in out], ["u1", "u2"])
        # the second request carried after=endCursor of the first page
        self.assertEqual(cap["bodies"][0]["variables"]["after"], None)
        self.assertEqual(cap["bodies"][1]["variables"]["after"], "c1")
        self.assertEqual(len(cap["bodies"]), 2)

    def test_list_ready_issues_raises_on_missing_end_cursor(self):
        # hasNextPage true but no endCursor → pagination-integrity error, never silent truncation
        pages = [_page([self._node("u1", "A-1")], has_next=True, cursor=None)]
        with self.assertRaises(RuntimeError):
            linear.list_ready_issues("team-1", "s1", api_key="k",
                                     http_post=_paged_post(pages))

    def test_list_ready_issues_single_page_without_pageinfo(self):
        # a response with no pageInfo degrades to one fetch (no infinite loop)
        resp = {"data": {"issues": {"nodes": [self._node("u1", "A-1")]}}}
        out = linear.list_ready_issues("team-1", "s1", api_key="k",
                                       http_post=_capturing_post({}, resp))
        self.assertEqual([t["id"] for t in out], ["u1"])

    def test_fetch_issues_by_states_empty_makes_no_call(self):
        def boom(url, data, headers):
            raise AssertionError("http_post must not be called for empty state_ids")
        self.assertEqual(
            linear.fetch_issues_by_states("team-1", [], api_key="k", http_post=boom), [])

    def test_fetch_issues_by_states_paginates_and_normalizes(self):
        cap = {}
        pages = [_page([self._node("u1", "A-1")], has_next=True, cursor="c1"),
                 _page([self._node("u2", "A-2")], has_next=False)]
        out = linear.fetch_issues_by_states("team-1", ["sDone", "sCancelled"],
                                            api_key="k", http_post=_paged_post(pages, cap))
        self.assertEqual([t["id"] for t in out], ["u1", "u2"])
        # re-dispatchable shape: prompt + state_id + labels + blockers present
        self.assertIn("A-1", out[0]["prompt"])
        self.assertEqual(out[0]["state_id"], "s1")
        self.assertEqual(out[0]["labels"], [])
        self.assertEqual(out[0]["blockers"], [])
        self.assertEqual(cap["bodies"][0]["variables"]["states"], ["sDone", "sCancelled"])
        self.assertIn("in:", cap["bodies"][0]["query"].replace(" ", ""))

    def test_fetch_issues_by_states_board_method_delegates(self):
        cap = {}
        board = linear.LinearBoard(api_key="bound",
                                   http_post=_capturing_post(cap, _page([])))
        self.assertEqual(board.fetch_issues_by_states("team-1", ["s1"]), [])
        # the bound key + state-set filter reached the transport
        self.assertEqual(cap["headers"]["Authorization"], "bound")
        self.assertEqual(cap["body"]["variables"]["states"], ["s1"])


if __name__ == "__main__":
    unittest.main()
