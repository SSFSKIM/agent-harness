import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.merge_preserve as mp  # noqa: E402


class ParseNumstatTest(unittest.TestCase):
    def test_parses_added_deleted_and_path(self):
        got = mp.parse_numstat("3\t1\tfoo.py\n10\t0\tbar/baz.py\n")
        self.assertEqual(got, {"foo.py": (3, 1), "bar/baz.py": (10, 0)})

    def test_binary_counts_become_zero_but_path_kept(self):
        # a binary file shows `-` for counts; we still key it so presence is tracked
        got = mp.parse_numstat("-\t-\timg.png\n")
        self.assertEqual(got, {"img.png": (0, 0)})

    def test_blank_and_malformed_lines_skipped(self):
        got = mp.parse_numstat("\n2\tonly-two-cols\n5\t2\tok.py\n")
        self.assertEqual(got, {"ok.py": (5, 2)})


class PreservationDeltaTest(unittest.TestCase):
    def test_identical_is_ok(self):
        d = {"a.py": (5, 0), "b.py": (2, 1)}
        r = mp.preservation_delta(d, dict(d))
        self.assertTrue(r["ok"])
        self.assertEqual(r["dropped_paths"], [])
        self.assertEqual(r["shrunk_paths"], [])

    def test_missing_path_is_dropped(self):
        intended = {"a.py": (5, 0), "b.py": (2, 0)}
        actual = {"a.py": (5, 0)}                    # b.py vanished from the merge
        r = mp.preservation_delta(intended, actual)
        self.assertFalse(r["ok"])
        self.assertEqual(r["dropped_paths"], ["b.py"])

    def test_deletion_only_path_missing_is_dropped(self):
        # the PR only removed lines from c.py; the merge lacks the change entirely → dropped
        r = mp.preservation_delta({"c.py": (0, 4)}, {})
        self.assertEqual(r["dropped_paths"], ["c.py"])
        self.assertFalse(r["ok"])

    def test_clear_shrink_is_flagged(self):
        # 10 added intended, 2 added actual: below half AND >= 3-line absolute drop
        r = mp.preservation_delta({"a.py": (10, 0)}, {"a.py": (2, 0)})
        self.assertEqual(r["shrunk_paths"], ["a.py"])
        self.assertFalse(r["ok"])

    def test_minor_reduction_is_not_flagged(self):
        # 10 -> 8: only a 2-line drop and above the half ratio — conservative, not flagged
        r = mp.preservation_delta({"a.py": (10, 0)}, {"a.py": (8, 0)})
        self.assertTrue(r["ok"])

    def test_below_ratio_but_tiny_absolute_not_flagged(self):
        # 4 -> 1: below half ratio but only a 3-line file; (4-1)=3 == _MIN_SHRINK → flagged.
        # Use 3 -> 1 to stay under the absolute floor: (3-1)=2 < 3 → NOT flagged.
        self.assertTrue(mp.preservation_delta({"a.py": (3, 0)}, {"a.py": (1, 0)})["ok"])

    def test_growth_is_ok(self):
        r = mp.preservation_delta({"a.py": (5, 0)}, {"a.py": (9, 0)})
        self.assertTrue(r["ok"])


class _FakeProc:
    def __init__(self, returncode, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


class NumstatFromCmdTest(unittest.TestCase):
    def test_success_parses_stdout_and_uses_argv(self):
        seen = {}

        def run(argv, **kw):
            seen["argv"] = argv
            seen["kw"] = kw
            return _FakeProc(0, "4\t0\tx.py\n")

        got = mp.numstat_from_cmd(["git", "diff", "--numstat", "a..b"], cwd="/ws", run=run)
        self.assertEqual(got, {"x.py": (4, 0)})
        # argv is a list (no shell) and cwd is threaded through
        self.assertEqual(seen["argv"], ["git", "diff", "--numstat", "a..b"])
        self.assertEqual(seen["kw"]["cwd"], "/ws")

    def test_nonzero_exit_fails_closed(self):
        self.assertIsNone(mp.numstat_from_cmd(["gh", "pr", "diff"],
                                              run=lambda *a, **k: _FakeProc(1, "")))

    def test_exception_fails_closed(self):
        def boom(*a, **k):
            raise FileNotFoundError("gh not found")
        self.assertIsNone(mp.numstat_from_cmd(["gh"], run=boom))


class ClassifyChecksTest(unittest.TestCase):
    def test_empty_rollup_is_green(self):
        self.assertEqual(mp.classify_checks([]), "green")
        self.assertEqual(mp.classify_checks(None), "green")

    def test_all_success_is_green(self):
        roll = [{"status": "COMPLETED", "conclusion": "SUCCESS"},
                {"state": "SUCCESS"}]
        self.assertEqual(mp.classify_checks(roll), "green")

    def test_a_failure_is_failing(self):
        roll = [{"status": "COMPLETED", "conclusion": "SUCCESS"},
                {"status": "COMPLETED", "conclusion": "FAILURE"}]
        self.assertEqual(mp.classify_checks(roll), "failing")

    def test_in_progress_is_pending(self):
        roll = [{"status": "IN_PROGRESS"}, {"status": "COMPLETED", "conclusion": "SUCCESS"}]
        self.assertEqual(mp.classify_checks(roll), "pending")

    def test_failure_beats_pending(self):
        roll = [{"status": "IN_PROGRESS"}, {"status": "COMPLETED", "conclusion": "FAILURE"}]
        self.assertEqual(mp.classify_checks(roll), "failing")

    def test_status_context_state_failure(self):
        self.assertEqual(mp.classify_checks([{"state": "FAILURE"}]), "failing")


def _hygiene_run(*, rollup=None, threads=None, rollup_rc=0, graphql_rc=0, seen=None):
    """A fake subprocess.run that answers the two gh calls pr_hygiene makes: the graphql
    thread query vs the statusCheckRollup view (dispatched by argv)."""
    def run(argv, **kw):
        if seen is not None:
            seen.append(argv)
        if "graphql" in argv:
            return _FakeProc(graphql_rc, json.dumps(threads) if threads is not None else "")
        return _FakeProc(rollup_rc, json.dumps(rollup) if rollup is not None else "")
    return run


def _threads(*resolved_flags):
    nodes = [{"isResolved": r} for r in resolved_flags]
    return {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": nodes}}}}}


_PR = "https://github.com/o/r/pull/5"


class PrHygieneTest(unittest.TestCase):
    def test_green_when_checks_pass_and_threads_resolved(self):
        run = _hygiene_run(rollup={"statusCheckRollup": [{"state": "SUCCESS"}]},
                           threads=_threads(True, True))
        self.assertEqual(mp.pr_hygiene(_PR, require_threads=True, run=run), "green")

    def test_failing_checks(self):
        run = _hygiene_run(rollup={"statusCheckRollup": [{"state": "FAILURE"}]})
        self.assertEqual(mp.pr_hygiene(_PR, require_threads=True, run=run), "failing")

    def test_pending_short_circuits_threads(self):
        seen = []
        run = _hygiene_run(rollup={"statusCheckRollup": [{"status": "IN_PROGRESS"}]}, seen=seen)
        self.assertEqual(mp.pr_hygiene(_PR, require_threads=True, run=run), "pending")
        self.assertFalse(any("graphql" in a for a in seen))   # no thread query on pending

    def test_unresolved_thread_fails_when_knob_on(self):
        run = _hygiene_run(rollup={"statusCheckRollup": [{"state": "SUCCESS"}]},
                           threads=_threads(True, False))
        self.assertEqual(mp.pr_hygiene(_PR, require_threads=True, run=run), "failing")

    def test_unresolved_thread_ignored_when_knob_off(self):
        seen = []
        run = _hygiene_run(rollup={"statusCheckRollup": [{"state": "SUCCESS"}]},
                           threads=_threads(False), seen=seen)
        self.assertEqual(mp.pr_hygiene(_PR, require_threads=False, run=run), "green")
        self.assertFalse(any("graphql" in a for a in seen))   # knob off → no thread query

    def test_fail_closed_when_checks_unreadable(self):
        run = _hygiene_run(rollup_rc=1)
        self.assertEqual(mp.pr_hygiene(_PR, require_threads=True, run=run), "failing")

    def test_fail_closed_when_threads_unreadable(self):
        run = _hygiene_run(rollup={"statusCheckRollup": [{"state": "SUCCESS"}]}, graphql_rc=1)
        self.assertEqual(mp.pr_hygiene(_PR, require_threads=True, run=run), "failing")


class UnresolvedThreadCountTest(unittest.TestCase):
    def test_counts_unresolved(self):
        run = _hygiene_run(threads=_threads(True, False, False))
        self.assertEqual(mp.unresolved_thread_count(_PR, run=run), 2)

    def test_bad_url_is_none(self):
        self.assertIsNone(mp.unresolved_thread_count("not-a-pr-url",
                                                     run=_hygiene_run(threads=_threads())))

    def test_gh_error_is_none(self):
        self.assertIsNone(mp.unresolved_thread_count(_PR, run=_hygiene_run(graphql_rc=1)))


if __name__ == "__main__":
    unittest.main()
