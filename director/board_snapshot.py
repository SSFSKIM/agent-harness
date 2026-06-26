"""Whole-board snapshot producer (Phase 5 observability — project graph view).

`director/status.py` answers *"what is the run doing in aggregate?"* over the
tickets ONE run touched; this module answers the missing project-wide question —
*"what does the WHOLE board look like, and how do its tickets depend on each
other?"*. The orchestrator already polls Linear every tick and every candidate
ticket already carries `blockers: [{id, state_type}]` (the DAG predecessor edges,
`director/board/linear.py:_parse_blockers`) — the orchestration reasons over
exactly this DAG to compute **waves**. This module PERSISTS the entire board as an
atomic `board.json` snapshot the dashboard renders as a layered DAG, exactly as
`status.json`/`runs.jsonl`/`<ticket>.jsonl` already bridge the orchestrator and the
(separate) dashboard process.

Design owner: docs/product-specs/2026-06-26-project-dependency-graph-view.md
(R1-R3). Built per docs/exec-plans/active/2026-06-26-project-dependency-graph-view.md
(M1). Read-only local files: no network, no human key, no new exec surface — the
dashboard reads this; the LINEAR_API_KEY stays Director-side. Mirrors the
`status.py` grain: atomic temp+`os.replace` write (RELIABILITY R9, no torn read), a
`Noop` writer for byte-identical off-path, and a tolerant read (missing/torn →
None, never raises — visibility is an instrument, never a gate, R3).

Key property: `build_board_view` is PURE (no socket, no IO) and assigns the
**topological layer = wave** to each node — so *same layer ⇒ schedulable in
parallel, consecutive layer ⇒ serial dependency*. The meaningful "serial vs
parallel" computation lives here (testable), not in the browser renderer
(ARCHITECTURE invariant 4). Cycle- and orphan-safe (R2/R12 totality): a blocker
cycle (the orchestrator's own stuck-cycle case) never hangs or raises — it is
flagged, not crashed.

Store (.claude/harness/director-board/board.json):
  {"nodes": [<raw candidate dicts>], "generated_at"}   # raw on write, derived on read

Derived view (build_board_view, served at GET /api/v1/board):
  {"nodes": [{id, identifier, title, state, state_id, labels, blockers, layer, in_cycle}],
   "edges": [{from, to}],            # blocker_id -> ticket_id, both in-set
   "layers": [[id, ...], ...],       # node-ids grouped by layer (render rank hint)
   "generated_at"}
"""
from __future__ import annotations

import datetime
import json
import os
import tempfile
from collections import deque
from pathlib import Path
from typing import Callable

# The graph-relevant projection of a candidate ticket — the `description`/`prompt`
# bloat is dropped from the served view (it is kept in the raw stored snapshot).
_NODE_FIELDS = ("id", "identifier", "title", "state", "state_id", "labels")


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _root(base: Path | str | None = None) -> Path:
    """Board root. Explicit `base` wins (tests); else $DIRECTOR_BOARD_DIR; else a
    sibling of the status/queue/events/history dirs under .claude/harness/ (already
    gitignored). Kept separate so each producer owns its own store (D-34 grain)."""
    if base is not None:
        return Path(base)
    env = os.environ.get("DIRECTOR_BOARD_DIR")
    if env:
        return Path(env)
    return Path(".claude/harness/director-board")


def _board_path(root: Path) -> Path:
    return root / "board.json"


def _project_node(node: dict) -> dict:
    """A raw candidate ticket -> the graph-relevant node (drop description/prompt
    bloat; keep the blocker edges). Tolerant: a missing field is just None/[]."""
    out = {k: node.get(k) for k in _NODE_FIELDS}
    blockers = node.get("blockers")
    out["blockers"] = blockers if isinstance(blockers, list) else []
    return out


def build_board_view(nodes, *, now: Callable[[], str] = _utcnow) -> dict:
    """Normalize a raw board node list into a layered-DAG view (R2) — PURE, no IO.

    Assigns each node its topological layer (longest path from a root over the
    blocker DAG = the orchestrator's wave depth) via Kahn's algorithm, so the layer
    *is* the schedulability rank: same layer ⇒ parallel, next layer ⇒ serial.

    Total / cycle-safe (R12): tolerant of `None`/garbage (→ well-formed empty view);
    a node missing a string `id` is skipped; a blocker pointing outside the in-set
    board (a dangling/cross-team edge) is dropped from `edges` so the rendered graph
    stays consistent; a blocker **cycle** (incl. a self-block) leaves its members
    topologically unresolved — they are placed in a single band after the acyclic
    max layer and flagged `in_cycle: true` (never an infinite loop, never a raise).
    Deterministic: layers and edges are sorted so the output is stable for a given
    input (a snapshot diff / a test can pin it)."""
    nodes = nodes if isinstance(nodes, list) else []

    # 1) Dedupe by id (first wins) + project to the graph-relevant fields.
    by_id: dict[str, dict] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("id")
        if not isinstance(nid, str) or not nid or nid in by_id:
            continue
        by_id[nid] = _project_node(n)
    ids = set(by_id)

    # 2) Predecessor sets (for the topo) + rendered edges (in-set, self-loops excluded
    #    from the render but KEPT in preds so a self-block stays unresolvable → in_cycle).
    preds: dict[str, set[str]] = {nid: set() for nid in by_id}
    edges: list[dict] = []
    for nid, node in by_id.items():
        for b in node.get("blockers") or []:
            bid = b.get("id") if isinstance(b, dict) else None
            if not isinstance(bid, str) or bid not in ids or bid in preds[nid]:
                continue                       # dangling (outside board) OR a duplicate
                                               # blocker entry — Linear may repeat a
                                               # `blocks` relation; one edge per pair so
                                               # the renderer never sees a dup element id.
            preds[nid].add(bid)                # self included (cycle-of-1 detection)
            if bid != nid:
                edges.append({"from": bid, "to": nid})   # no degenerate self-edge render

    # 3) Kahn's longest-path layering over the acyclic core.
    succ: dict[str, list[str]] = {nid: [] for nid in by_id}
    indeg: dict[str, int] = {}
    for nid in by_id:
        indeg[nid] = len(preds[nid])
        for p in preds[nid]:
            if p != nid:                       # a self-edge never decrements to 0 (stuck)
                succ[p].append(nid)
    layer: dict[str, int] = {}
    q: deque[str] = deque(sorted(n for n in by_id if indeg[n] == 0))
    for n in q:
        layer[n] = 0
    while q:
        n = q.popleft()
        for m in succ[n]:
            layer[m] = max(layer.get(m, 0), layer[n] + 1)   # finalized when indeg[m] hits 0
            indeg[m] -= 1
            if indeg[m] == 0:
                q.append(m)

    # 4) Whatever Kahn could not resolve is entangled in a blocker cycle (a member or a
    #    descendant) — flag it and band it after the acyclic max (best-effort, no hang).
    acyclic = set(layer)
    band = (max(layer.values()) + 1) if layer else 0
    for nid in by_id:
        layer.setdefault(nid, band)

    out_nodes = [{**node, "layer": layer[nid], "in_cycle": nid not in acyclic}
                 for nid, node in by_id.items()]
    max_layer = max(layer.values()) if layer else -1
    layers: list[list[str]] = [[] for _ in range(max_layer + 1)]
    for nid in by_id:
        layers[layer[nid]].append(nid)
    for lst in layers:
        lst.sort()
    edges.sort(key=lambda e: (e["to"], e["from"]))
    return {"nodes": out_nodes, "edges": edges, "layers": layers, "generated_at": now()}


class BoardWriter:
    """Persist the whole-board node list as an atomic snapshot (best-effort, R1).

    `write(nodes)` stores the RAW candidate dicts under `{nodes, generated_at}` —
    the layer/edge derivation (`build_board_view`) runs on READ, keeping the stored
    artifact close to source. Atomic temp+`os.replace` (RELIABILITY R9) so a live
    dashboard reader never sees a torn snapshot. Best-effort by contract (R3): any
    write failure is swallowed (recorded in `last_error`), never raised — a board
    snapshot must never gate the orchestrator's poll."""

    def __init__(self, base: Path | str | None = None, *, now: Callable[[], str] = _utcnow):
        self._root = _root(base)
        self._now = now
        self.last_error: str | None = None

    def write(self, nodes) -> None:
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            snap = {"nodes": list(nodes) if isinstance(nodes, list) else [],
                    "generated_at": self._now()}
            fd, tmp = tempfile.mkstemp(dir=str(self._root), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(snap, f, ensure_ascii=False, sort_keys=True)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, _board_path(self._root))
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
        except Exception as exc:  # best-effort: visibility NEVER gates the poll (R1/R3).
            self.last_error = str(exc)


class NoopBoardWriter:
    """Records nothing — the default when the board surface is off (library calls /
    tests), so orchestration is byte-identical (the `NoopStatusWriter` precedent)."""

    last_error = None

    def write(self, *a, **k) -> None:
        return None


def read_board(base: Path | str | None = None) -> dict | None:
    """The stored snapshot `{nodes, generated_at}`, or None if there is no snapshot
    yet / it is unreadable. Tolerant by contract (R3): a missing file (no snapshot)
    and an unparseable/torn file both yield None rather than raising — the dashboard
    reads "no board yet" and degrades to its flat-list rail."""
    p = _board_path(_root(base))
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None  # torn/garbled/non-UTF-8 → "no board"; never raise (R12 totality)


class BoardSnapshotter:
    """Throttled whole-board snapshot driver the orchestrator's poll loops call once per
    tick. Encapsulates the cadence so the loops carry no snapshot bookkeeping (the
    `_RunState`/StatusWriter precedent: the loop calls a method, the object owns the state).

    `fetch` is an injected thunk `() -> list[node]` (main wires it to the whole-board
    read — every workflow state's issues with their blocker DAG); decoupling from the
    board interface keeps this pure-testable (a fake fetch, no network). `maybe_snapshot`
    fires the FIRST time it is called (so a fresh run / pre-run gets a snapshot promptly),
    then at most once per `interval_s`. Exception-total (R1/R12): a failing fetch/write is
    swallowed — a board snapshot must NEVER gate the orchestrator's poll. The throttle
    clock advances even on failure, so a persistently-failing board is retried at the
    cadence, never hammered."""

    def __init__(self, fetch: Callable[[], list], writer, interval_s: float):
        self._fetch = fetch
        self._writer = writer
        self._interval = interval_s
        self._last: float | None = None     # monotonic of the last attempt (None = never)

    def maybe_snapshot(self, now: float) -> bool:
        """Snapshot if due (`now` = a monotonic clock). Returns True if it attempted a
        snapshot this call, False if throttled. Never raises."""
        if self._last is not None and (now - self._last) < self._interval:
            return False
        self._last = now
        try:
            self._writer.write(self._fetch())
        except Exception as exc:  # best-effort: visibility NEVER gates the poll (R1/R3).
            self._writer.last_error = str(exc)
        return True


class NoopBoardSnapshotter:
    """Snapshots nothing — the default when the board surface is off (the `--no-status`
    switch, library calls, tests), so the poll loops are byte-identical (the
    `NoopStatusWriter`/`NoopBoardWriter` precedent)."""

    def maybe_snapshot(self, now: float) -> bool:
        return False


def main(argv=None) -> int:
    """Read surface: dump the current board as the layered-DAG view (read-only)."""
    import argparse

    ap = argparse.ArgumentParser(
        prog="director.board_snapshot",
        description="Read the whole-board snapshot as a layered-DAG view.")
    ap.add_argument("--board-dir", default=None, help="board dir override")
    args = ap.parse_args(argv)
    snap = read_board(base=args.board_dir) or {}
    view = build_board_view(snap.get("nodes", []) if isinstance(snap, dict) else [])
    print(json.dumps(view, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
