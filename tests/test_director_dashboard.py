import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.dashboard as dash  # noqa: E402
import director.queue as dq  # noqa: E402
import director.status as ds  # noqa: E402

_FIXED_NOW = "2026-06-16T00:00:00+00:00"
_PATH_STATE = "/api/v1/state"  # the versioned read-only data route (asserted as a literal)


def _ticket(tid, ident):
    return {"id": tid, "identifier": ident, "title": "t"}


def _seed_run(status_dir):
    """A run with one in-flight ticket and one terminated ticket carrying telemetry —
    so the snapshot has codex_totals/rate_limits on run and tokens/session_id on a
    recent row, exercising build_view's pass-through."""
    w = ds.StatusWriter(base=status_dir)
    w.wave(1)
    w.claimed(_ticket("T1", "ABC-1"), wave=1, attempt=1)
    w.dispatched(_ticket("T1", "ABC-1"))
    w.claimed(_ticket("T2", "ABC-2"), wave=1, attempt=1)
    w.terminal(_ticket("T2", "ABC-2"),
               {"ticket": "ABC-2", "status": "completed", "final_state": "done",
                "attempts": 1, "turns": 2,
                "telemetry": {"tokens": {"input": 60, "output": 40, "total": 100},
                              "session_id": "thr_x-turn_y", "last_message": "all done",
                              "rate_limits": {"remaining": 9}}})


class BuildViewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.status_dir = Path(self.tmp) / "director-status"
        self.queue_dir = Path(self.tmp) / "director-queue"

    def _view(self):
        return dash.build_view(status_dir=self.status_dir, queue_dir=self.queue_dir,
                               now=lambda: _FIXED_NOW)

    def test_view_schema_and_telemetry_passthrough(self):
        # A real snapshot + a pending request → view dict per the spec contract, with
        # the producer telemetry riding through run/recent untouched.
        _seed_run(self.status_dir)
        dq.append_request({"request_id": "r1", "ticket_id": "T1", "kind": "turnReview",
                           "payload": {"final_message": "please review my work"}},
                          base=self.queue_dir)
        v = self._view()
        self.assertEqual(set(v), {"run", "in_flight", "stuck", "recent", "pending",
                                  "counts", "generated_at"})
        self.assertEqual(v["generated_at"], _FIXED_NOW)
        # run telemetry pass-through (computed by the producer, not the renderer)
        self.assertEqual(v["run"]["codex_totals"]["input"], 60)
        self.assertEqual(v["run"]["codex_totals"]["output"], 40)
        self.assertEqual(v["run"]["codex_totals"]["total"], 100)
        self.assertIn("seconds_running", v["run"]["codex_totals"])
        self.assertEqual(v["run"]["rate_limits"], {"remaining": 9})
        # in-flight structure rides through
        self.assertEqual(len(v["in_flight"]), 1)
        self.assertEqual(v["in_flight"][0]["identifier"], "ABC-1")
        # recent row carries per-ticket telemetry
        self.assertEqual(len(v["recent"]), 1)
        self.assertEqual(v["recent"][0]["tokens"], {"input": 60, "output": 40, "total": 100})
        self.assertEqual(v["recent"][0]["session_id"], "thr_x-turn_y")
        self.assertEqual(v["recent"][0]["last_message"], "all done")
        # pending reduced to the glance-able shape, summary filled by kind
        self.assertEqual(v["pending"], [{"request_id": "r1", "ticket_id": "T1",
                                         "kind": "turnReview",
                                         "summary": "please review my work"}])
        # counts == array lengths
        self.assertEqual(v["counts"], {"in_flight": 1, "stuck": 0,
                                       "recent": 1, "pending": 1})

    def test_no_run_is_tolerant(self):
        # No status.json (no run) and an empty queue → run:None, zero counts, valid dict.
        v = self._view()
        self.assertIsNone(v["run"])
        self.assertEqual(v["in_flight"], [])
        self.assertEqual(v["recent"], [])
        self.assertEqual(v["pending"], [])
        self.assertEqual(v["counts"], {"in_flight": 0, "stuck": 0, "recent": 0, "pending": 0})
        self.assertEqual(v["generated_at"], _FIXED_NOW)

    def test_torn_status_json_yields_run_none(self):
        # A garbage status.json (torn/partial write) → read_status returns None → run:None,
        # never an exception (R3 tolerance).
        self.status_dir.mkdir(parents=True, exist_ok=True)
        (self.status_dir / "status.json").write_text("{not json", encoding="utf-8")
        v = self._view()
        self.assertIsNone(v["run"])

    def test_summary_by_kind(self):
        # Each kind's summary is pulled from its verified payload shape (tolerant).
        cases = [
            ({"request_id": "a", "kind": "commandApproval",
              "payload": {"command": ["rm", "-rf", "/tmp/cache"]}}, "rm -rf /tmp/cache"),
            ({"request_id": "b", "kind": "mergeReview",
              "payload": {"result": "escalated", "reason": "conflict"}}, "escalated conflict"),
            ({"request_id": "c", "kind": "fileChange",
              "payload": {"reason": "edit config"}}, "edit config"),
            ({"request_id": "d", "kind": "elicitation",
              "payload": {"questions": "which env?"}}, "which env?"),
            ({"request_id": "e", "kind": "weirdKind", "payload": {}}, "weirdKind"),
        ]
        for req, _ in cases:
            req.setdefault("ticket_id", "T1")
            dq.append_request(req, base=self.queue_dir)
        v = self._view()
        got = {p["request_id"]: p["summary"] for p in v["pending"]}
        for req, expected in cases:
            self.assertEqual(got[req["request_id"]], expected)

    def test_malformed_payload_summary_never_raises(self):
        # A non-dict / missing payload → empty summary, no exception (R6 — telemetry/
        # rendering is instrumentation, never a gate).
        dq.append_request({"request_id": "m1", "ticket_id": "T1",
                           "kind": "turnReview", "payload": "not a dict"},
                          base=self.queue_dir)
        dq.append_request({"request_id": "m2", "ticket_id": "T1", "kind": "turnReview"},
                          base=self.queue_dir)  # no payload key at all
        v = self._view()
        summaries = {p["request_id"]: p["summary"] for p in v["pending"]}
        self.assertEqual(summaries["m1"], "")
        self.assertEqual(summaries["m2"], "")


class DashboardHTTPTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.status_dir = Path(self.tmp) / "director-status"
        self.queue_dir = Path(self.tmp) / "director-queue"
        _seed_run(self.status_dir)  # so /api/v1/state has real telemetry to serve
        self.httpd = dash.serve(0, self.status_dir, self.queue_dir)  # port 0 = ephemeral
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)

    def _req(self, path, method="GET"):
        url = f"http://127.0.0.1:{self.port}{path}"
        try:
            resp = urllib.request.urlopen(urllib.request.Request(url, method=method), timeout=2)
            return resp.status, resp.headers.get("Content-Type"), resp.read()
        except urllib.error.HTTPError as e:  # 404/405 land here
            return e.code, e.headers.get("Content-Type"), e.read()

    def test_state_route_returns_build_view_json(self):
        code, ctype, body = self._req(_PATH_STATE)
        self.assertEqual(code, 200)
        self.assertIn("application/json", ctype)
        data = json.loads(body)
        self.assertEqual(data["counts"]["recent"], 1)
        self.assertEqual(data["run"]["codex_totals"]["total"], 100)  # telemetry served live

    def test_root_route_returns_html(self):
        code, ctype, _ = self._req("/")
        self.assertEqual(code, 200)
        self.assertIn("text/html", ctype)

    def test_undefined_route_is_404_envelope(self):
        code, ctype, body = self._req("/nope")
        self.assertEqual(code, 404)
        self.assertIn("application/json", ctype)
        self.assertEqual(json.loads(body)["error"]["code"], 404)

    def test_wrong_method_on_defined_route_is_405_envelope(self):
        code, _, body = self._req(_PATH_STATE, method="POST")
        self.assertEqual(code, 405)
        self.assertEqual(json.loads(body)["error"]["code"], 405)

    def test_server_survives_bad_requests(self):
        # After a 404 and an odd-verb 405 the server still answers a good GET (tolerance).
        self._req("/nope")
        self._req("/", method="DELETE")
        code, _, _ = self._req(_PATH_STATE)
        self.assertEqual(code, 200)


if __name__ == "__main__":
    unittest.main()
