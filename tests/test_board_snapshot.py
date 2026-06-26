import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.board_snapshot as bs  # noqa: E402

_T = lambda: "T"  # noqa: E731 — deterministic clock for the view stamp


def node(nid, blockers=(), **extra):
    """A raw candidate-shaped ticket: id + blockers ([{id,state_type}]) + extras."""
    n = {"id": nid, "identifier": nid.upper(), "title": f"t-{nid}",
         "state": "Todo", "state_id": "s", "labels": [],
         "blockers": [{"id": b, "state_type": "unstarted"} for b in blockers]}
    n.update(extra)
    return n


def layer_of(view, nid):
    return next(n["layer"] for n in view["nodes"] if n["id"] == nid)


def in_cycle(view, nid):
    return next(n["in_cycle"] for n in view["nodes"] if n["id"] == nid)


class BuildBoardViewTest(unittest.TestCase):
    def test_chain_layers_are_serial_depth(self):
        # a blocks b blocks c  ->  a@0, b@1, c@2 (each a serial wave deeper)
        view = bs.build_board_view([node("a"), node("b", ["a"]), node("c", ["b"])], now=_T)
        self.assertEqual((layer_of(view, "a"), layer_of(view, "b"), layer_of(view, "c")), (0, 1, 2))
        self.assertEqual({(e["from"], e["to"]) for e in view["edges"]}, {("a", "b"), ("b", "c")})
        self.assertEqual(view["layers"], [["a"], ["b"], ["c"]])
        self.assertEqual(view["generated_at"], "T")
        self.assertTrue(all(not n["in_cycle"] for n in view["nodes"]))

    def test_diamond_uses_longest_path(self):
        # a->b, a->c, b->d, c->d  ->  d is layer 2 (longest path a-b-d / a-c-d), not 1
        view = bs.build_board_view(
            [node("a"), node("b", ["a"]), node("c", ["a"]), node("d", ["b", "c"])], now=_T)
        self.assertEqual(layer_of(view, "a"), 0)
        self.assertEqual(layer_of(view, "b"), 1)
        self.assertEqual(layer_of(view, "c"), 1)
        self.assertEqual(layer_of(view, "d"), 2)
        self.assertEqual(view["layers"][1], ["b", "c"])  # same layer = parallel-schedulable

    def test_parallel_roots_and_orphan_are_layer_zero(self):
        # three independent roots + one fully isolated orphan all sit at layer 0
        view = bs.build_board_view([node("a"), node("b"), node("c"), node("orphan")], now=_T)
        self.assertEqual([layer_of(view, x) for x in ("a", "b", "c", "orphan")], [0, 0, 0, 0])
        self.assertEqual(view["layers"], [["a", "b", "c", "orphan"]])
        self.assertEqual(view["edges"], [])

    def test_cycle_does_not_hang_and_is_flagged(self):
        # a<->b mutual block: unresolvable -> both flagged in_cycle, no infinite loop
        view = bs.build_board_view([node("a", ["b"]), node("b", ["a"])], now=_T)
        self.assertTrue(in_cycle(view, "a"))
        self.assertTrue(in_cycle(view, "b"))
        # both still receive a (best-effort) layer and appear in `layers`
        self.assertIn("a", [x for band in view["layers"] for x in band])

    def test_self_block_is_a_cycle_of_one(self):
        view = bs.build_board_view([node("a", ["a"])], now=_T)
        self.assertTrue(in_cycle(view, "a"))
        self.assertEqual(view["edges"], [])  # no degenerate self-edge in the render

    def test_descendant_of_cycle_is_entangled(self):
        # c depends on a cycle (a<->b); c cannot be cleanly ordered -> flagged too
        view = bs.build_board_view(
            [node("a", ["b"]), node("b", ["a"]), node("c", ["a"]), node("root")], now=_T)
        self.assertFalse(in_cycle(view, "root"))   # the clean root is unaffected
        self.assertTrue(in_cycle(view, "c"))

    def test_dangling_blocker_is_dropped(self):
        # b is blocked by "ghost" which is NOT on the board -> edge dropped, b is a root
        view = bs.build_board_view([node("b", ["ghost"])], now=_T)
        self.assertEqual(view["edges"], [])
        self.assertEqual(layer_of(view, "b"), 0)
        self.assertFalse(in_cycle(view, "b"))

    def test_projection_drops_bloat_keeps_graph_fields(self):
        view = bs.build_board_view(
            [node("a", description="x" * 9999, prompt="huge", labels=["impl"])], now=_T)
        n = view["nodes"][0]
        self.assertNotIn("description", n)
        self.assertNotIn("prompt", n)
        self.assertEqual(n["identifier"], "A")
        self.assertEqual(n["labels"], ["impl"])
        self.assertEqual(n["blockers"], [])

    def test_tolerant_of_garbage(self):
        self.assertEqual(bs.build_board_view(None, now=_T),
                         {"nodes": [], "edges": [], "layers": [], "generated_at": "T"})
        # non-dict entries and an id-less node are skipped, never raise
        view = bs.build_board_view(["nope", 7, {"no_id": 1}, node("a")], now=_T)
        self.assertEqual([n["id"] for n in view["nodes"]], ["a"])

    def test_duplicate_ids_first_wins(self):
        view = bs.build_board_view([node("a", title="first"), node("a", title="second")], now=_T)
        self.assertEqual(len(view["nodes"]), 1)


class BoardWriterTest(unittest.TestCase):
    def test_write_roundtrips_through_read(self):
        with tempfile.TemporaryDirectory() as d:
            w = bs.BoardWriter(base=d, now=_T)
            w.write([node("a"), node("b", ["a"])])
            self.assertIsNone(w.last_error)
            snap = bs.read_board(base=d)
            assert snap is not None  # narrow Optional + a real "snapshot exists" check
            self.assertEqual(snap["generated_at"], "T")
            self.assertEqual([n["id"] for n in snap["nodes"]], ["a", "b"])
            # the stored artifact is RAW (close to source) — derivation runs on read
            self.assertNotIn("layer", snap["nodes"][0])
            view = bs.build_board_view(snap["nodes"], now=_T)
            self.assertEqual(layer_of(view, "b"), 1)

    def test_write_tolerates_non_list(self):
        with tempfile.TemporaryDirectory() as d:
            w = bs.BoardWriter(base=d, now=_T)
            w.write("not a list")
            snap = bs.read_board(base=d)
            assert snap is not None
            self.assertEqual(snap["nodes"], [])

    def test_read_missing_is_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(bs.read_board(base=d))

    def test_read_torn_is_none(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "board.json").write_text('{"nodes": [{"id": "a"', encoding="utf-8")
            self.assertIsNone(bs.read_board(base=d))

    def test_atomic_no_tmp_left_behind(self):
        with tempfile.TemporaryDirectory() as d:
            bs.BoardWriter(base=d, now=_T).write([node("a")])
            leftovers = [p.name for p in Path(d).iterdir() if p.suffix == ".tmp"]
            self.assertEqual(leftovers, [])

    def test_noop_writer_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            w = bs.NoopBoardWriter()
            w.write([node("a")])
            self.assertIsNone(w.last_error)
            self.assertEqual(list(Path(d).iterdir()), [])
            self.assertIsNone(bs.read_board(base=d))


class _RecWriter:
    """A BoardWriter stand-in that records the node lists it was handed."""
    def __init__(self):
        self.writes = []
        self.last_error = None

    def write(self, nodes):
        self.writes.append(nodes)


class BoardSnapshotterTest(unittest.TestCase):
    def test_first_call_snapshots_then_throttles(self):
        w = _RecWriter()
        s = bs.BoardSnapshotter(fetch=lambda: [node("a")], writer=w, interval_s=10)
        self.assertTrue(s.maybe_snapshot(100.0))      # first call always fires (prompt fresh snapshot)
        self.assertFalse(s.maybe_snapshot(105.0))     # within interval → throttled
        self.assertTrue(s.maybe_snapshot(110.0))      # interval elapsed → fires again
        self.assertFalse(s.maybe_snapshot(111.0))
        self.assertEqual(len(w.writes), 2)            # exactly the two un-throttled calls wrote

    def test_fetch_failure_is_swallowed_and_still_throttles(self):
        w = _RecWriter()
        def boom():
            raise RuntimeError("board down")
        s = bs.BoardSnapshotter(fetch=boom, writer=w, interval_s=10)
        self.assertTrue(s.maybe_snapshot(100.0))      # attempted, never raises
        self.assertEqual(w.writes, [])                # fetch failed → nothing written
        self.assertEqual(w.last_error, "board down")  # recorded on the writer
        self.assertFalse(s.maybe_snapshot(105.0))     # clock advanced even on failure → throttled (no hammer)

    def test_write_failure_is_swallowed(self):
        class BoomWriter:
            last_error = None
            def write(self, nodes):
                raise RuntimeError("disk full")
        s = bs.BoardSnapshotter(fetch=lambda: [node("a")], writer=BoomWriter(), interval_s=10)
        self.assertTrue(s.maybe_snapshot(100.0))      # never raises into the poll

    def test_noop_snapshotter_never_fires(self):
        s = bs.NoopBoardSnapshotter()
        self.assertFalse(s.maybe_snapshot(100.0))
        self.assertFalse(s.maybe_snapshot(1e9))


class RootResolutionTest(unittest.TestCase):
    def test_explicit_base_beats_env(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(bs._root(d), Path(d))

    def test_default_is_under_claude_harness(self):
        import os
        old = os.environ.pop("DIRECTOR_BOARD_DIR", None)
        try:
            self.assertEqual(bs._root(None), Path(".claude/harness/director-board"))
        finally:
            if old is not None:
                os.environ["DIRECTOR_BOARD_DIR"] = old


if __name__ == "__main__":
    unittest.main()
