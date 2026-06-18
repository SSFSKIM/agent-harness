import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.notify as notify  # noqa: E402
import director.queue as dq  # noqa: E402

_NOSLEEP = lambda _s: None  # noqa: E731


class WebhookPayloadTest(unittest.TestCase):
    def test_payload_shape_and_summary(self):
        req = {"request_id": "r1", "kind": "turnReview", "ticket_id": "T1",
               "created_at": "2026-06-18T00:00:00+00:00",
               "payload": {"final_message": "A or B?"}}
        p = notify.webhook_payload(req)
        self.assertEqual(set(p), {"request_id", "kind", "ticket_id", "summary", "created_at"})
        self.assertEqual(p["request_id"], "r1")
        self.assertEqual(p["kind"], "turnReview")
        self.assertEqual(p["summary"], "A or B?")  # per-kind summary (turnReview→final_message)

    def test_payload_tolerates_missing_payload(self):
        p = notify.webhook_payload({"request_id": "r2", "kind": "turnReview"})
        self.assertEqual(p["summary"], "")  # no payload → empty summary, no raise


class WebhookNotifierTest(unittest.TestCase):
    def test_2xx_true_non2xx_false_and_raise_false(self):
        self.assertTrue(notify.make_webhook_notifier("http://x", http_post=lambda *_: 200)({}))
        self.assertTrue(notify.make_webhook_notifier("http://x", http_post=lambda *_: 204)({}))
        self.assertFalse(notify.make_webhook_notifier("http://x", http_post=lambda *_: 500)({}))

        def boom(*_):
            raise OSError("dead url")
        # a transport error is swallowed → False, never raises (fail-soft)
        self.assertFalse(notify.make_webhook_notifier("http://x", http_post=boom)({}))


class RunLoopTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.q = Path(self.tmp) / "queue"

    def _pend(self, rid, kind, **payload):
        dq.append_request({"request_id": rid, "ticket_id": "T1", "kind": kind,
                           "payload": payload}, base=self.q)

    def test_fires_once_per_new_human_request_and_skips_non_human(self):
        self._pend("r1", "turnReview", final_message="m1")
        self._pend("r2", "commandApproval", command=["ls"])
        self._pend("mr", "mergeRequest", pr="#1")          # NOT human-bound → never posted
        posts = []
        notify.run(lambda e: (posts.append(e["request_id"]), True)[1],
                   queue_dir=self.q, max_ticks=3, sleep=_NOSLEEP)
        # 3 ticks, but each human-bound rid fires exactly once (dedup); mergeRequest skipped
        self.assertEqual(sorted(posts), ["r1", "r2"])

    def test_failed_post_retries_then_abandons(self):
        self._pend("r1", "turnReview", final_message="m")
        calls = []
        notify.run(lambda e: (calls.append(e["request_id"]), False)[1],  # always fails
                   queue_dir=self.q, max_ticks=10, retry_cap=3, sleep=_NOSLEEP)
        # retried up to the cap (3 attempts) across the 10 ticks, then abandoned — never
        # hammered forever, and the loop survived every failure (no exception escaped).
        self.assertEqual(calls.count("r1"), 3)

    def test_transient_failure_then_recovers(self):
        self._pend("r1", "turnReview", final_message="m")
        seq = [False, True]  # fail once, then succeed
        posts = []

        def flaky(e):
            posts.append(e["request_id"])
            return seq.pop(0) if seq else True
        notify.run(flaky, queue_dir=self.q, max_ticks=5, retry_cap=5, sleep=_NOSLEEP)
        # one failed attempt + one successful = 2 calls, then deduped (seen) → no more
        self.assertEqual(posts.count("r1"), 2)

    def test_torn_queue_is_fail_soft(self):
        # an unreadable queue read must not raise out of the loop (no pending this tick)
        notify.run(lambda e: True, queue_dir=self.q / "does-not-exist",
                   max_ticks=2, sleep=_NOSLEEP)  # must simply return


class ResolveUrlTest(unittest.TestCase):
    def test_precedence_cli_env_dotenv(self):
        import os
        self.assertEqual(notify._resolve_webhook_url("http://cli"), "http://cli")  # cli wins
        prev = os.environ.pop("DIRECTOR_WEBHOOK_URL", None)
        os.environ["DIRECTOR_WEBHOOK_URL"] = "http://env"
        try:
            self.assertEqual(notify._resolve_webhook_url(None), "http://env")     # env next
        finally:
            os.environ.pop("DIRECTOR_WEBHOOK_URL", None)
            if prev is not None:
                os.environ["DIRECTOR_WEBHOOK_URL"] = prev
        d = tempfile.mkdtemp()
        p = Path(d) / ".env"
        p.write_text('DIRECTOR_WEBHOOK_URL="http://dotenv"\n', encoding="utf-8")
        self.assertEqual(notify._resolve_webhook_url(None, env_path=p), "http://dotenv")


class MainTest(unittest.TestCase):
    def test_missing_url_errors(self):
        # no --webhook and no env → SystemExit (argparse error), never a silent no-op
        import os
        prev = os.environ.pop("DIRECTOR_WEBHOOK_URL", None)
        try:
            with self.assertRaises(SystemExit):
                notify.main(["--once", "--queue-dir", "/tmp/nope-notify"])
        finally:
            if prev is not None:
                os.environ["DIRECTOR_WEBHOOK_URL"] = prev

    def test_non_http_scheme_rejected(self):
        # a misconfigured file:// (etc.) URL fails loud at startup, never honored
        with self.assertRaises(SystemExit):
            notify.main(["--once", "--webhook", "file:///etc/passwd"])


if __name__ == "__main__":
    unittest.main()
