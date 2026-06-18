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


def _boom(*_a, **_k):
    raise RuntimeError("boom")  # stand-in for any handler-internal bug


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

    def test_inflight_live_tokens_pass_through_and_run_total_is_live(self):
        # Layer-2 (R1/R2): an accrued in-flight ticket → build_view carries
        # in_flight[].tokens AND run.codex_totals reflects the LIVE (ended+in-flight) sum.
        w = ds.StatusWriter(base=self.status_dir)
        w.claimed(_ticket("T1", "ABC-1"), wave=1, attempt=1)
        w.accrue("T1", {"input": 200, "output": 200, "total": 400})
        v = self._view()
        self.assertEqual(v["in_flight"][0]["tokens"], {"input": 200, "output": 200, "total": 400})
        self.assertEqual(v["run"]["codex_totals"]["total"], 400)  # live, no ended ticket yet

    def test_page_renders_inflight_live_tokens(self):
        # M3: the in-flight row shows its live tokens (reusing fmtTokens) — the consumer
        # of the producer's new in_flight[].tokens field.
        self.assertIn("fmtTokens(e.tokens)", dash.PAGE)

    def test_page_uses_sse_with_poll_fallback_and_legible_rate(self):
        # M2 (R4/R6): the page prefers EventSource(/api/v1/stream), keeps the ~1s poll as
        # the fallback path, and renders rate limits via the tolerant helper — never the
        # raw JSON dump.
        self.assertIn('new EventSource("/api/v1/stream")', dash.PAGE)
        self.assertIn("fallbackPoll", dash.PAGE)
        self.assertIn("setInterval(poll, 1000)", dash.PAGE)        # fallback preserved
        self.assertIn("fmtRateLimits(run.rate_limits)", dash.PAGE)
        self.assertNotIn("JSON.stringify(run.rate_limits)", dash.PAGE)  # raw dump removed

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
            ({"request_id": "b2", "kind": "mergeRequest",
              "payload": {"pr": "#42", "branch": "feat/x"}}, "#42 feat/x"),  # else→pr/branch
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

    def test_valid_but_non_dict_status_json_yields_run_none(self):
        # read_status returns dict|None|MALFORMED: a valid-but-non-dict status.json
        # (a JSON list/string from a producer bug or hand-edit) comes back as-is, not
        # None. build_view must coerce it to "no run", never raise AttributeError on
        # .get (R3/R6 — a garbage-but-valid file is tolerated like a torn one).
        self.status_dir.mkdir(parents=True, exist_ok=True)
        (self.status_dir / "status.json").write_text('["not", "a", "dict"]', encoding="utf-8")
        v = self._view()  # must not raise
        self.assertIsNone(v["run"])
        self.assertEqual(v["counts"]["in_flight"], 0)

    def test_torn_queue_degrades_to_empty_pending(self):
        # The queue is JSONL-appended (no atomic temp+replace) and shared across
        # parallel processes, so a live reader can catch a half-written final line.
        # build_view must degrade to pending:[] rather than 500 the view (R3 + R5:
        # the tolerance lives in the dashboard, not in the unchanged queue module).
        _seed_run(self.status_dir)
        dq.append_request({"request_id": "ok", "ticket_id": "T1", "kind": "turnReview",
                           "payload": {"final_message": "fine"}}, base=self.queue_dir)
        # a torn trailing line mid-write (json.JSONDecodeError) AND a parseable line
        # missing request_id (read_pending does r["request_id"] -> KeyError): both must
        # degrade to "no pending", never escape build_view.
        with open(self.queue_dir / "requests.jsonl", "a", encoding="utf-8") as f:
            f.write('{"kind": "turnReview"}\n')            # valid JSON, no request_id
            f.write('{"request_id": "torn", "kind": "turnRev')  # torn trailing line
        v = self._view()
        self.assertEqual(v["pending"], [])  # tolerant: no crash, no partial garbage
        self.assertEqual(v["counts"]["pending"], 0)
        self.assertIsNotNone(v["run"])  # the rest of the view still renders

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

    def test_stream_route_pushes_initial_event(self):
        # M1 integration (R4): GET /api/v1/stream holds a text/event-stream open and
        # emits an initial data: frame = the current build_view. Read one frame, then
        # close (the server's next write fails → its stream loop ends cleanly, R14).
        url = f"http://127.0.0.1:{self.port}/api/v1/stream"
        resp = urllib.request.urlopen(url, timeout=2)
        self.assertIn("text/event-stream", resp.headers.get("Content-Type"))
        data = None
        for _ in range(10):
            line = resp.readline().decode("utf-8")
            if line.startswith("data:"):
                data = line[len("data:"):].strip()
                break
        resp.close()
        self.assertIsNotNone(data, "stream should emit an initial data: frame")
        view = json.loads(data)
        self.assertEqual(view["run"]["codex_totals"]["total"], 100)  # the seeded run, pushed

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

    def test_handler_fails_soft_to_500_envelope(self):
        # A handler-internal bug (build_view raising) must degrade to a structured 500
        # envelope the client JS already handles — never a dropped connection / stderr
        # traceback (read-only instrument, never a gate). And the server stays up.
        orig = dash.build_view
        dash.build_view = _boom
        try:
            code, ctype, body = self._req(_PATH_STATE)
        finally:
            dash.build_view = orig
        self.assertEqual(code, 500)
        self.assertIn("application/json", ctype)
        self.assertEqual(json.loads(body)["error"]["code"], 500)
        # listener survived the bug — a subsequent good request still answers
        self.assertEqual(self._req(_PATH_STATE)[0], 200)

    def test_page_wires_poller_and_telemetry(self):
        # The page is asserted by CONTRACT markers, not layout: it must poll the
        # versioned route on an interval (live, no reload) and reference the now-shipped
        # cost/usage telemetry fields — proving the renderer consumes the producer's
        # richness, which is the whole reason this slice was sequenced after telemetry.
        code, _, body = self._req("/")
        self.assertEqual(code, 200)
        html = body.decode("utf-8")
        self.assertTrue(html.lstrip().startswith("<!doctype html"))
        self.assertIn("/api/v1/state", html)  # polls the data route
        self.assertIn("setInterval", html)    # on an interval (D-3 polling, no SSE)
        for marker in ("codex_totals", "rate_limits", "seconds_running", "tokens"):
            self.assertIn(marker, html)

    def test_page_injects_token_and_action_controls(self):
        # M2: the page embeds the per-server CSRF token and wires the write path — a
        # token meta with the live token, the POST to the answer route with the token
        # header, and a control per answerable kind.
        code, _, body = self._req("/")
        self.assertEqual(code, 200)
        html = body.decode("utf-8")
        self.assertIn("__DIRECTOR_TOKEN__", dash.PAGE)          # placeholder in the template
        self.assertIn(f'content="{self.httpd.token}"', html)   # ...substituted live
        self.assertNotIn("__DIRECTOR_TOKEN__", html)
        self.assertIn("/api/v1/answer", html)
        self.assertIn("X-Director-Token", html)
        self.assertIn("renderPending", html)
        # the per-kind controls (button labels are JS args; kinds are branch literals)
        for marker in ('btn("reply"', 'btn("done"', 'btn("accept"', 'btn("decline"',
                       'btn("requeue"', 'btn("abandon"',
                       'kind === "turnReview"', 'kind === "mergeReview"'):
            self.assertIn(marker, html)


class SSEStreamLoopTest(unittest.TestCase):
    """M1: the SSE push logic is a pure, injectable loop — unit-tested without a socket
    (the read-dashboard testability lever). Emits a `data:` frame only when the view
    CHANGES, a `: ping` heartbeat after no-change, and stops on a write disconnect (R14)."""

    def test_emits_initial_frame_then_only_on_change(self):
        frames = []
        views = iter([{"a": 1}, {"a": 1}, {"a": 2}])  # initial · unchanged · changed
        n = {"i": 0}
        def should_run():
            keep = n["i"] < 3
            n["i"] += 1
            return keep
        dash._stream_loop(frames.append, lambda: next(views), sleep=lambda _: None,
                          now=lambda: 0.0, should_run=should_run, heartbeat_s=15.0, poll_s=0.0)
        datas = [f for f in frames if f.startswith(b"data:")]
        self.assertEqual(len(datas), 2)              # initial + the change; the unchanged tick emitted nothing
        self.assertIn(b'"a": 1', datas[0])
        self.assertIn(b'"a": 2', datas[1])

    def test_heartbeat_after_no_change(self):
        frames = []
        clock = {"t": 0.0}
        n = {"i": 0}
        def should_run():
            clock["t"] += 20.0       # advance past heartbeat each tick
            keep = n["i"] < 3
            n["i"] += 1
            return keep
        dash._stream_loop(frames.append, lambda: {"same": 1}, sleep=lambda _: None,
                          now=lambda: clock["t"], should_run=should_run,
                          heartbeat_s=15.0, poll_s=0.0)
        datas = [f for f in frames if f.startswith(b"data:")]
        pings = [f for f in frames if f == b": ping\n\n"]
        self.assertEqual(len(datas), 1)              # only the initial state
        self.assertEqual(len(pings), 2)              # then heartbeats while unchanged

    def test_stops_on_write_disconnect_without_raising(self):
        calls = {"n": 0}
        def write(_b):
            calls["n"] += 1
            raise BrokenPipeError()                  # peer gone mid-write
        n = {"i": 0}
        def should_run():
            keep = n["i"] < 5
            n["i"] += 1
            return keep
        dash._stream_loop(write, lambda: {"a": 1}, sleep=lambda _: None, now=lambda: 0.0,
                          should_run=should_run, heartbeat_s=15.0, poll_s=0.0)  # must NOT raise
        self.assertEqual(calls["n"], 1)              # returned on the first failed write (R14)


class ValidatorUnitTest(unittest.TestCase):
    def test_validate_disposition(self):
        ok = [{"kind": "reply", "reply": "do X"},
              {"kind": "escalate", "reason": "taste"},
              {"kind": "terminal", "outcome": {"status": "done"}},
              {"kind": "terminal", "outcome": {"status": "blocked"}}]
        for d in ok:
            self.assertIsNone(dash._validate_disposition(d), d)
        bad = ["nope", {}, {"kind": "weird"}, {"kind": "reply", "reply": "  "},
               {"kind": "terminal"}, {"kind": "terminal", "outcome": {"status": "huh"}}]
        for d in bad:
            self.assertIsNotNone(dash._validate_disposition(d), d)

    def test_host_is_local(self):
        for v in ("127.0.0.1:8787", "localhost", "http://127.0.0.1:8787",
                  "http://localhost:8787", "[::1]:8787"):
            self.assertTrue(dash._host_is_local(v), v)
        for v in (None, "", "evil.com:80", "http://evil.com", "10.0.0.5:8787"):
            self.assertFalse(dash._host_is_local(v), v)


_VALID = "__USE_VALID__"


class AnswerRouteTest(unittest.TestCase):
    """The write path: POST /api/v1/answer resolves a pending request via director_min,
    fenced (token + origin), idempotent (409), validated (400) — the M1 surface."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.status_dir = Path(self.tmp) / "director-status"
        self.queue_dir = Path(self.tmp) / "director-queue"
        self.httpd = dash.serve(0, self.status_dir, self.queue_dir)
        self.port = self.httpd.server_address[1]
        self.token = self.httpd.token
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)

    def _pend(self, req):
        req.setdefault("ticket_id", "T1")
        dq.append_request(req, base=self.queue_dir)

    def _post(self, payload, *, token=_VALID, origin=None, raw=None):
        url = f"http://127.0.0.1:{self.port}/api/v1/answer"
        data = raw if raw is not None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        tok = self.token if token == _VALID else token
        if tok is not None:
            headers["X-Director-Token"] = tok
        if origin is not None:
            headers["Origin"] = origin
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=2)
            return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_turn_review_reply_written_and_unblocks(self):
        self._pend({"request_id": "r1", "kind": "turnReview",
                    "payload": {"final_message": "A or B?"}})
        code, body = self._post({"request_id": "r1", "kind": "turnReview",
                                 "disposition": {"kind": "reply", "reply": "do A"}})
        self.assertEqual(code, 200, body)
        self.assertTrue(body["written"])
        ans = dq.read_answer("r1", base=self.queue_dir)
        self.assertEqual(ans["disposition"], {"kind": "reply", "reply": "do A"})
        self.assertEqual(ans["answered_by"], "console")
        self.assertNotIn("r1", [r["request_id"] for r in dq.read_pending(base=self.queue_dir)])

    def test_terminal_requires_outcome_status(self):
        self._pend({"request_id": "rt", "kind": "turnReview", "payload": {}})
        bad = self._post({"request_id": "rt", "kind": "turnReview",
                          "disposition": {"kind": "terminal"}})
        self.assertEqual(bad[0], 400)
        self.assertIsNone(dq.read_answer("rt", base=self.queue_dir))  # nothing written
        ok = self._post({"request_id": "rt", "kind": "turnReview",
                         "disposition": {"kind": "terminal", "outcome": {"status": "done"}}})
        self.assertEqual(ok[0], 200)

    def test_command_approval_decision(self):
        self._pend({"request_id": "c1", "kind": "commandApproval",
                    "payload": {"command": ["ls"]}})
        self.assertEqual(self._post({"request_id": "c1", "kind": "commandApproval",
                                     "decision": "yolo"})[0], 400)  # bad enum
        code, _ = self._post({"request_id": "c1", "kind": "commandApproval",
                              "decision": "accept"})
        self.assertEqual(code, 200)
        self.assertEqual(dq.read_answer("c1", base=self.queue_dir)["decision"], "accept")

    def test_user_input_answers(self):
        self._pend({"request_id": "u1", "kind": "userInput",
                    "payload": {"questions": "which env?"}})
        code, _ = self._post({"request_id": "u1", "kind": "userInput",
                              "answers": {"env": "staging"}})
        self.assertEqual(code, 200)
        self.assertEqual(dq.read_answer("u1", base=self.queue_dir)["answers"], {"env": "staging"})

    def test_merge_review_abandon_and_requeue(self):
        self._pend({"request_id": "m1", "kind": "mergeReview",
                    "payload": {"pr": "#7", "branch": "feat/x", "attempt": 1,
                                "result": "conflict"}})
        code, _ = self._post({"request_id": "m1", "kind": "mergeReview",
                              "action": "abandon", "note": "drop it"})
        self.assertEqual(code, 200)
        self.assertIn("merge_review_disposition", dq.read_answer("m1", base=self.queue_dir))
        # requeue posts a fresh mergeRequest at attempt+1
        self._pend({"request_id": "m2", "kind": "mergeReview",
                    "payload": {"pr": "#8", "branch": "feat/y", "attempt": 1}})
        code, body = self._post({"request_id": "m2", "kind": "mergeReview",
                                 "action": "requeue", "note": "rebase then merge"})
        self.assertEqual(code, 200, body)
        self.assertIsNotNone(dq.read_answer("m2", base=self.queue_dir))  # review consumed
        # a fresh mergeRequest was enqueued for the retry (attempt 2)
        mrs = [r for r in dq.read_requests(base=self.queue_dir) if r.get("kind") == "mergeRequest"]
        self.assertTrue(any((r.get("payload") or {}).get("attempt") == 2 for r in mrs))

    def test_merge_review_human_action(self):
        # the API-level `human` resolution (no UI button — API superset; record it works)
        self._pend({"request_id": "mh", "kind": "mergeReview", "payload": {"pr": "#1", "attempt": 1}})
        code, _ = self._post({"request_id": "mh", "kind": "mergeReview", "action": "human"})
        self.assertEqual(code, 200)
        self.assertEqual(dq.read_answer("mh", base=self.queue_dir)["merge_review_disposition"]["action"], "human")

    def test_merge_review_requeue_refused_is_not_reported_as_success(self):
        # at max_attempts, requeue_merge REFUSES and leaves the review open — the console
        # must NOT return a written-success envelope for that no-op (review fix).
        self._pend({"request_id": "mcap", "kind": "mergeReview",
                    "payload": {"pr": "#9", "branch": "b", "attempt": 3}})  # 3 = default cap
        code, body = self._post({"request_id": "mcap", "kind": "mergeReview",
                                 "action": "requeue", "note": "again"})
        self.assertEqual(code, 400)
        self.assertIn("refused", body["error"]["message"])
        # the review is left OPEN (still pending), not silently consumed
        self.assertIn("mcap", [r["request_id"] for r in dq.read_pending(base=self.queue_dir)])

    def test_merge_request_not_answerable(self):
        self._pend({"request_id": "mr", "kind": "mergeRequest",
                    "payload": {"pr": "#9", "branch": "b"}})
        self.assertEqual(self._post({"request_id": "mr", "kind": "mergeRequest"})[0], 409)

    def test_missing_token_is_403_and_leaves_pending(self):
        self._pend({"request_id": "f1", "kind": "turnReview", "payload": {}})
        code, _ = self._post({"request_id": "f1", "kind": "turnReview",
                              "disposition": {"kind": "escalate"}}, token=None)
        self.assertEqual(code, 403)
        self.assertIsNone(dq.read_answer("f1", base=self.queue_dir))  # not answered
        self.assertEqual(self._post({"request_id": "f1", "kind": "turnReview",
                                     "disposition": {"kind": "escalate"}},
                                    token="wrong")[0], 403)

    def test_foreign_origin_is_403(self):
        self._pend({"request_id": "o1", "kind": "turnReview", "payload": {}})
        code, _ = self._post({"request_id": "o1", "kind": "turnReview",
                              "disposition": {"kind": "escalate"}},
                             origin="http://evil.example")
        self.assertEqual(code, 403)

    def test_already_answered_is_409(self):
        self._pend({"request_id": "a1", "kind": "turnReview", "payload": {}})
        self.assertEqual(self._post({"request_id": "a1", "kind": "turnReview",
                                     "disposition": {"kind": "escalate"}})[0], 200)
        self.assertEqual(self._post({"request_id": "a1", "kind": "turnReview",
                                     "disposition": {"kind": "escalate"}})[0], 409)

    def test_unknown_request_is_404(self):
        self.assertEqual(self._post({"request_id": "ghost", "kind": "turnReview",
                                     "disposition": {"kind": "escalate"}})[0], 404)

    def test_kind_mismatch_is_400(self):
        self._pend({"request_id": "k1", "kind": "turnReview", "payload": {}})
        self.assertEqual(self._post({"request_id": "k1", "kind": "commandApproval",
                                     "decision": "accept"})[0], 400)

    def test_malformed_body_is_400_and_server_survives(self):
        self.assertEqual(self._post(None, raw=b"not json")[0], 400)
        # server still serves a good GET afterward (fail-soft, R7)
        resp = urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/v1/state", timeout=2)
        self.assertEqual(resp.status, 200)


if __name__ == "__main__":
    unittest.main()
