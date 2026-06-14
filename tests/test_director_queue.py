import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.queue as dq  # noqa: E402


def _req(rid="req-1"):
    return {
        "request_id": rid,
        "ticket_id": "T-1",
        "session_id": "thr_1-turn_1",
        "kind": "commandApproval",
        "payload": {"command": ["rm", "-rf", "/tmp/x"]},
        "workspace_path": "/ws",
        "created_at": "2026-06-14T00:00:00Z",
    }


class DirectorQueueTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.base = Path(self.tmp) / "director-queue"

    def test_request_answer_roundtrip(self):
        self.assertTrue(dq.append_request(_req(), base=self.base))
        pending = dq.read_pending(base=self.base)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["kind"], "commandApproval")
        self.assertIsNone(dq.read_answer("req-1", base=self.base))

        dq.write_answer({
            "request_id": "req-1", "decision": "accept",
            "answered_by": "director", "answered_at": "2026-06-14T00:00:01Z",
        }, base=self.base)

        ans = dq.read_answer("req-1", base=self.base)
        self.assertEqual(ans["decision"], "accept")
        self.assertEqual(dq.read_pending(base=self.base), [])

    def test_request_dedupe_by_id(self):
        self.assertTrue(dq.append_request(_req(), base=self.base))
        self.assertFalse(dq.append_request(_req(), base=self.base))  # same id -> no-op
        self.assertEqual(len(dq.read_requests(base=self.base)), 1)

    def test_answer_is_atomic_overwrite(self):
        dq.write_answer({"request_id": "r", "decision": "accept",
                         "answered_by": "director", "answered_at": "t1"}, base=self.base)
        dq.write_answer({"request_id": "r", "decision": "decline",
                         "answered_by": "human", "answered_at": "t2"}, base=self.base)
        ans = dq.read_answer("r", base=self.base)
        self.assertEqual(ans["decision"], "decline")
        self.assertEqual(ans["answered_by"], "human")

    def test_wait_for_answer_times_out(self):
        got = dq.wait_for_answer("missing", base=self.base, timeout_s=0.3, poll_s=0.05)
        self.assertIsNone(got)

    def test_wait_for_answer_returns_when_present(self):
        dq.write_answer({"request_id": "r2", "decision": "accept",
                         "answered_by": "director", "answered_at": "t"}, base=self.base)
        got = dq.wait_for_answer("r2", base=self.base, timeout_s=0.3, poll_s=0.05)
        self.assertEqual(got["decision"], "accept")


if __name__ == "__main__":
    unittest.main()
