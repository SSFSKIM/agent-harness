---
status: stable
last_verified: 2026-06-27
owner: harness
phase: symphony/05-project-graph-view
type: product-spec
description: A project-wide dependency-graph lens over the existing observability substrate — the orchestrator persists a whole-board snapshot (every ticket + its blocker DAG) the dashboard renders as a layered DAG (layers = waves, so serial-vs-parallel falls out of the scheduler's own model), with node state/telemetry painted live from status.json and a click-to-open session-stream overlay reusing the per-ticket SSE; a single vendored, offline graph library powers layout/pan/zoom/collapse.
---
# Project dependency-graph view (whole-board DAG + live session overlay)

Phase 5 **observability** track. Parent:
[Symphony 티켓 오케스트레이션 + 중앙 Director](2026-06-14-symphony-director-orchestration.md)
(line 199 "Phase 5 — observability surface"). This is the next consumer-richness
slice after the read dashboard
([observability-dashboard](2026-06-16-director-observability-dashboard.md)), the
telemetry producer ([worker-telemetry-capture](2026-06-16-worker-telemetry-capture.md)),
the operator console ([operator-console](2026-06-18-director-operator-console.md)),
the polish slice ([observability-polish](2026-06-18-observability-polish.md)), and
the per-ticket session-event stream
([per-ticket-session-event-stream](2026-06-24-per-ticket-session-event-stream.md),
which added the live drill-down this view re-anchors onto a graph node). It also
consumes, as a *view*, the dependency DAG the orchestration already reasons over
([dag-aware-orchestration](2026-06-14-dag-aware-orchestration.md)).

## Problem

Every observability slice so far answers a **run-scoped, flat-list** question. The
dashboard's surface is a set of lists — `in_flight`, `stuck`, `recent` (last 20),
`pending` queue — scoped to **the tickets one run touched**. Three things a human
steering a multi-ticket project wants are absent:

1. **The whole project, not one run.** `status.json` only ever contains tickets the
   active run claimed/finished; the full board — backlog, ready, in-other-states,
   done — is never surfaced. There is no "프로젝트 전체 진행상황" view: what fraction
   of the project is done, where the active frontier sits, what is still ahead.
2. **The dependency structure (serial vs parallel) is in the data but thrown away.**
   Every candidate ticket already carries `blockers: [{id, state_type}]` — the DAG
   predecessor edges (`director/board/linear.py:_parse_blockers`). The orchestrator
   reasons over exactly this DAG to compute **waves** (dag-aware-orchestration). But
   the dashboard renders it only as a one-line `stuck` string (`LIN-30 ← LIN-12,
   LIN-20`). The serial/parallel topology the user explicitly wants to *see* is the
   first thing the flat-list view discards.
3. **No spatial home for the live session stream.** The per-ticket SSE drill-down
   (per-ticket-session-event-stream) exists and works, but it opens as a panel
   appended to the bottom of a list — disconnected from *where that ticket sits in
   the project*.

Crucially, **the data and the streaming already exist** — `board/linear.py` can
fetch the whole board with blocker edges, `status.json` carries the live run
telemetry, and `<ticket>.jsonl` + the ticket SSE already stream the play-by-play.
What is missing is a single **lens**: a project-wide, dependency-shaped rendering
that paints the live state onto the topology and lets a node open its own session
stream. This is not new telemetry; it is a new *view* over the existing substrate.

## Requirements

Each is independently verifiable (a human can check it).

- **R1 — Whole-board snapshot producer (best-effort, atomic).** The orchestrator
  persists the **entire configured board** (not just the run's working set) as an
  atomic snapshot `board.json`, refreshed at poll cadence. Each node carries
  `{id, identifier, title, state, state_id, labels, blockers:[{id,state_type}]}` —
  the shape `_normalize_candidate` already produces (the ticket's own lifecycle is the
  human-readable `state` name + its `state_id`; `state_type` rides each blocker edge).
  The snapshot is produced by
  fetching every workflow state's issues (reusing `board.fetch_issues_by_states`
  with the full state-id set the orchestrator already resolved at startup via
  `workflow_states`). Atomic temp+`os.replace` (the `status.py` grain, RELIABILITY
  R9) so a reader never sees a torn snapshot. Best-effort by contract (R3 posture):
  a fetch or write failure is swallowed (`last_error`), never raised — a board
  snapshot must never gate dispatch. A `NoopBoardWriter` is the default so
  orchestration is byte-identical when the surface is off.

- **R2 — Pure board view with layer (= wave) assignment.** A pure
  `build_board_view(nodes) -> {nodes, edges, layers, generated_at}` derives, from
  the blocker DAG, a **topological layer per node** (longest path from a root over
  the blocker edges) — the same notion of "wave" the orchestrator dispatches by, so
  **same layer ⇒ schedulable in parallel, consecutive layer ⇒ serial dependency**.
  `edges` is the flattened blocker relation (`{from: blocker_id, to: ticket_id}`);
  `layers` is the node-ids grouped by layer (a render-ready rank hint). Pure, fully
  unit-testable without a browser or a socket (ARCHITECTURE invariant 4). **Cycle-
  and orphan-safe (R12 totality):** a blocker cycle (the orchestrator's own
  stuck-cycle case) must not hang or raise — cycle members get a best-effort layer
  and a `in_cycle: true` flag; an orphan (no blockers, no dependents) is a layer-0
  isolated node.

- **R3 — Tolerant board read + `/api/v1/board` route.** `read_board(base) -> dict |
  None` returns the stored snapshot dict `{nodes, generated_at}` or `None`
  (missing/torn/unreadable → `None`, never raises — the `read_status` contract). A new
  **read-only GET `/api/v1/board`** on the existing dashboard returns
  `build_board_view((read_board() or {}).get("nodes", []))`. Like every other GET
  route it is unfenced and reads only a server-held dir (no request-derived path).

- **R4 — Graph view as the dashboard centerpiece.** The single page renders the
  board as a **layered DAG** (the vendored library, R6): layers flow left→right,
  each node a ticket. A node's **lifecycle** (backlog / ready / in-flight / blocked /
  done / failed) is encoded by colour/border, derived by merging `board.json`
  (topology + Linear state) with the live `status.json` overlay (`in_flight` phase /
  attempt / wave / live tokens, `recent` terminal outcomes, `stuck`). The node set is
  the **union** of board nodes and any `status` ticket not yet in the latest board
  snapshot (so a just-claimed ticket appears immediately, before the next board
  refresh). Project progress reads off the graph: the done-fraction, the lit active
  frontier, the critical path still ahead. The existing flat lists (`in_flight` /
  `stuck` / `recent` / `pending` operator console) **relocate into a collapsible side
  rail** — the graph is the map, the rail is the decision inbox. No fake per-ticket
  "percent done": progress is qualitative (phase + live token fill + turn count),
  project-level progress is the done-fraction of the DAG.

- **R5 — Click-a-node → session-stream overlay.** Clicking a node opens an overlay
  panel **anchored to that node** that renders its session timeline + telemetry strip
  by reusing the existing per-ticket routes: an in-flight node opens an `EventSource`
  to `/api/v1/ticket/{id}/stream` (live); a terminal node renders its **recorded**
  timeline from `/api/v1/ticket/{id}/events` (the JSONL persists, so a finished ticket
  replays its full play-by-play). Closing the overlay closes the `EventSource`
  (bounded open connections). Every value via `textContent` (the existing XSS-safe
  discipline). This is the per-ticket-session-event-stream drill-down, re-homed from a
  bottom panel to a graph node.

- **R6 — One vendored, offline graph library (scoped invariant relaxation).** Layout
  (layered ranks), pan, zoom, and **collapse of completed subtrees** are powered by a
  single graph library **vendored as a checked-in, self-contained asset** under
  `director/assets/` and served from a **fixed** dashboard route — **no CDN, no
  bundler, no network fetch at render time** (offline-OK is preserved; only the
  dashboard's "single self-contained HTML *string*" self-grain relaxes to "one page +
  one local asset"). The Python **stdlib-only invariant (ARCHITECTURE invariant 1) is
  untouched** — it scopes Python imports, not a served JS file. This relaxation is
  recorded as an ADR and an invariant-1 scope clarification (R7). The asset route is
  fixed-map (route → known vendored file), so it adds **zero traversal surface**
  (invariant 3): a request-derived/`..` path → 404.

- **R7 — The relaxation is recorded, not silent.** A new ADR
  (`docs/adr/0006-observability-vendored-asset.md`) records the decision: the
  observability dashboard MAY vendor a single offline, checked-in JS asset, scoped to
  the observability surface; offline operation and the Python stdlib-only invariant
  remain in force. `ARCHITECTURE.md` invariant 1 gains a one-sentence scope note
  pointing at the ADR. ("Not in the repo = does not exist.")

- **R8 — Scales to a real board + degrades cleanly.** The view is usable on a
  100+-node board: it auto-fits on load and pan/zoom navigate the rest, with
  subtree-collapse and active-frontier focus **available, off by default** (a
  deliberate taste call — the full graph is shown first, the operator opts into
  clutter-reduction; M5a). If `board.json` is absent/torn the page
  **degrades to the existing side-rail lists** ("no board snapshot yet") and the live
  `status` overlay still works — the graph is additive, never a gate (R3 posture). The
  view also works **pre-run** (board snapshot exists from the first poll, even with no
  active dispatch — a static topology + Linear states).

- **R9 — Uniform across runtimes & board-snapshot cost is bounded.** The full path
  works identically for a codex and a `--worker claude` worker (the overlay reuses the
  runtime-agnostic ticket stream, R7 of the predecessor spec). The whole-board fetch
  is throttled by a `board_snapshot_interval_s` knob (default = the poll interval) so
  a large board never hammers Linear faster than the dispatch poll already does.

## Design

Additive throughout. One new producer module + one orchestrator wiring point + new
dashboard read routes/asset + a UI restructure of the single page. The worker
protocol, guardrail, `decider.py`, `merger.py`, `queue/`, `status.py`,
`ticket_events.py`, and `history.py` are **unchanged**. The layer obeys the
established R3 invariant: a read-only instrument, never a gate.

### Data flow

```
orchestrator poll tick (run_forever / run_once / run_until_drained)
  │  has `states` (all workflow states) from board.workflow_states(team) at startup
  │  every board_snapshot_interval_s:
  │    nodes = board.fetch_issues_by_states(team, ALL_state_ids)   # reuse, paginated
  │    self.board_writer.write(nodes)                              # atomic board.json
  ▼
.claude/harness/director-board/board.json     ← project SKELETON (slow: topology + Linear state)
.claude/harness/director-status/status.json   ← LIVE overlay   (fast: in_flight/recent/tokens/stuck)
.claude/harness/director-events/<id>.jsonl     ← session stream (exists)
  │
  ▼  dashboard (separate process, reads local files only — never touches Linear)
GET /api/v1/board   → build_board_view(read_board().nodes)   {nodes,edges,layers}
GET /api/v1/state   → build_view(...)                  (unchanged; the live overlay)
GET /api/v1/ticket/{id}/(events|stream)                (unchanged; the overlay source)
GET /assets/<lib>.js → fixed vendored asset            (new, offline)
  │
  ▼  client merges board (topology) × state (paint) × events (overlay) → layered DAG
```

`board.json` is the only new backend artifact; the LINEAR_API_KEY stays Director-side
and the dashboard still issues **no network** call ([[cc-codex-appserver-drop-in-verified]]
keeps the key Director-side).

### Components & files

- **NEW `director/board_snapshot.py`** — the whole producer surface, stdlib-only,
  pure helpers + a best-effort writer, mirroring `status.py`/`ticket_events.py`:
  - `build_board_view(nodes, *, now) -> dict` (R2) — pure: topological layer
    assignment (longest-path-from-roots over the blocker DAG), `edges`, `layers`,
    cycle/orphan handling (`in_cycle` flag, no hang). The meaningful "serial vs
    parallel" computation lives here (pure, testable), **not** in the browser lib —
    the lib renders the rank; this assigns it (invariant 4).
  - `BoardWriter` / `NoopBoardWriter` (R1) — `write(nodes)` does atomic temp+
    `os.replace` of the snapshot dict `{nodes, generated_at}` (the layer/edge
    derivation `build_board_view` is applied **on read**, keeping the stored artifact
    close to source); swallow-all `try/except` → `last_error`.
  - `read_board(base=None) -> dict | None` (R3) — returns `{nodes, generated_at}` or
    `None`; the `read_status` tolerance.
  - `_root` / `_board_path` + `$DIRECTOR_BOARD_DIR` override and the
    `.claude/harness/director-board` default (sibling of status/queue/events/history;
    already covered by the `.claude/harness/` gitignore).

- **`director/orchestrator.py`** — construct one `BoardWriter` (NoopBoardWriter when
  the status surface is off → off-path byte-identical, the `events`/`status`
  precedent). In the poll tick of `run_forever` (and the batch `run_once` /
  `run_until_drained` polls), throttled by `board_snapshot_interval_s` against a
  monotonic `last_board_snapshot` (the wall-clock-anchored cadence pattern invariant 7
  already uses for reconcile), fetch the full board and call `board_writer.write`. The
  fetch+write is exception-total at this boundary (the `_enqueue_usage`/`events.record`
  R12/R14 reasoning) — a hiccup skips one snapshot, never gates the poll. ~1 field +
  the throttled call + constructor wiring. **No change to claim/dispatch/reconcile.**

- **`director/config.py`** — add `board_snapshot_interval_s` to `DEFAULTS["director"]`
  (default = the poll interval), resolved like every other knob (invariant 5); aliased
  wherever a module needs the literal (no parallel literal).

- **`director/dashboard.py`** — additive:
  - `board_dir` field on `_DashboardServer` (set in `serve`, like
    `status_dir`/`events_dir`); `read_board` import.
  - `GET /api/v1/board` route → `build_board_view(read_board(board_dir) or [])`
    (R3). Added to `_ROUTES` (GET-only, unfenced).
  - A **fixed asset route** (R6): a small constant map `{"/assets/<lib>.js": <path
    under director/assets/>}` served with the right content-type; no request-derived
    path (invariant 3) — an unknown/`..` asset path → 404 via the existing
    `_route` 404 default.
  - The inline `PAGE` is restructured (R4/R5): the graph canvas becomes the
    centerpiece; the existing `in_flight`/`stuck`/`recent`/`pending` render functions
    **move into a collapsible side rail** (the operator-console answer controls are
    unchanged — same fenced `POST /api/v1/answer`); new JS builds the Cytoscape graph
    from `/api/v1/board` + `/api/v1/state`, paints nodes by merged lifecycle, and wires
    `node.on('tap')` to the existing ticket-overlay `EventSource` logic (re-homed, not
    rewritten). `main()` gains `--board-dir`.
  - The existing routes/streams (`/`, `/api/v1/state`, `/stream`, `/history`,
    `/ticket/*`, `/answer`) are byte-unchanged — the graph is a *new consumer* of the
    same data.

- **NEW `director/assets/`** — the vendored library (R6): Cytoscape.js +
  `cytoscape-dagre` (layered layout) + `cytoscape-expand-collapse` (subtree collapse),
  as checked-in self-contained UMD file(s). Offline; served only via the fixed route.

- **NEW `docs/adr/0006-observability-vendored-asset.md`** (R7) + a one-sentence scope
  note on `ARCHITECTURE.md` invariant 1 pointing at it; register in `docs/adr/index.md`.

- **Tests** — `tests/test_board_snapshot.py` (build_board_view: layer assignment on a
  diamond/chain/parallel fixture, **cycle-safe no-hang**, orphan→layer-0, edges/layers
  shape; BoardWriter atomic round-trip + torn/absent tolerance; read_board) and
  dashboard-test extensions (`/api/v1/board` shape; the **fixed asset route** serves
  the file and a traversal/`..` asset path → 404; board-absent degradation path).

- **Docs** — `docs/DIRECTOR_RUNBOOK.md` / `docs/DIRECTOR.md` dashboard section (the
  graph view + the new routes); register this spec in `docs/product-specs/index.md`;
  cross-link the predecessor observability specs.

### Key behaviors & edge cases

- **Stale-board vs live-status skew.** `board.json` refreshes at poll cadence, so it
  can lag `status.json` by up to one `board_snapshot_interval_s`. The client always
  prefers `status` for live fields and **unions** in any status-only ticket (R4), so a
  just-claimed ticket is never invisible while the board catches up.
- **Cycle / stuck.** A blocker cycle is exactly the orchestrator's stuck-cycle case;
  `build_board_view` flags cycle members (`in_cycle`) and the view renders them as a
  highlighted strongly-connected cluster — turning the existing `stuck` signal into a
  *visible* one. Never hangs (R2/R12).
- **Best-effort, off-path-clean.** Fetch/write failures swallowed (R1/R3);
  `NoopBoardWriter` when off → orchestration byte-identical (the `NoopStatusWriter`
  precedent). board.json absent → side-rail degradation (R8).
- **Traversal.** The asset route is a fixed constant map; `/api/v1/board` reads a
  server-held dir; the overlay reuses the already-sanitized `/ticket/{id}/*` routes —
  zero new request→path mapping beyond a vetted-fixed asset name (invariant 3).
- **Volume.** Board nodes are small dicts; hundreds are a small payload. The render
  cost is bounded by auto-fit + pan/zoom, with opt-in subtree-collapse + frontier-focus (R8).
- **Read-only.** No new write/act route. The only writes remain the existing fenced
  operator-console answers in the side rail (invariant 3).

### Verification (testability seams)

- `build_board_view` and `read_board` are **pure / tolerant**, unit-tested on fixture
  boards with no socket (the `build_view` precedent).
- `BoardWriter` atomicity and tolerance are unit-tested on a fixture dir (`base=`).
- The `/api/v1/board` + fixed-asset + traversal-404 routes are driven over `urllib`
  in the dashboard tests (the existing route-test harness).
- The **live behavioral pass** uses the `playwright-cli` skill (the dashboard is a
  runnable web surface): graph renders, node click → overlay streams, collapse a
  done subtree, pan/zoom, board-absent degradation, and **devtools shows no external
  network fetch** (offline-vendored proof).

## Non-goals (YAGNI / scope fence)

- **Editing the board from the graph.** No drag-to-rewire dependencies, no state
  changes, no ticket creation from the canvas — a read-only instrument. The only
  actions stay the existing fenced operator-console answers in the side rail.
- **Multi-team / cross-project board.** One configured board (`director.team`).
- **Board history / DAG time-travel / run-over-run topology replay.** Current
  snapshot only (the `status.json` "current run only" grain). The sole "replay" is a
  terminal node's recorded session timeline (R5), which is free (the JSONL persists).
- **Graph search / advanced filtering** beyond collapse + frontier-focus + pan/zoom.
- **A new write/act route, or any change to the worker protocol, decider, merger,
  guardrail, board ownership, `status.py`, or `ticket_events.py`.** Capture-and-render
  only; the producer is one new module + one orchestrator poll-tick call.
- **A second graph library or a build pipeline.** Exactly one vendored, checked-in,
  offline asset (R6) — a bundler/CDN is explicitly excluded.
- **Persisting `board.json` as cross-run analytics.** Current-snapshot store, like
  `status.json`; rotation/retention is deferred exactly as `history.py` defers it.

## Acceptance criteria

1. A daemon run against a Linear team with a multi-ticket blocker DAG produces
   `.claude/harness/director-board/board.json`; `build_board_view` over it assigns
   layers matching the blocker topology (same layer = parallel-schedulable, next layer
   = serial), survives a fixture **cycle without hanging**, and places an orphan at
   layer 0. (Unit test over fixtures.)
2. `curl -s http://127.0.0.1:<port>/api/v1/board | jq` returns
   `{nodes:[{id,identifier,title,state,state_id,labels,blockers,layer,in_cycle}], edges,
   layers, generated_at}`.
3. Driving the dashboard with `playwright-cli`: `/` renders the project DAG; done
   nodes are dimmed, in-flight nodes are lit with a live token fill, blocked/cycle
   nodes are marked; the active frontier and the done-fraction are visible at a glance.
4. Clicking an in-flight node opens an overlay anchored to it that streams that
   ticket's live session events; clicking a terminal node renders its recorded
   timeline; closing the overlay closes the connection.
5. Collapse a completed subtree, pan, and zoom work on a 100+-node board; browser
   devtools show **no external (CDN) network request** — the graph library is served
   from the local fixed asset route.
6. `GET /assets/<vendored>.js` serves the checked-in asset; any request-derived /
   `..` / unknown asset path → `404` (no file outside `director/assets/`).
7. `board.json` absent/torn → the page degrades to the side-rail lists ("no board
   snapshot yet") and the live `status` overlay still works — never an error, never a
   gate. The view also renders pre-run from a first-poll board snapshot.
8. The same flow (3–4) succeeds with a `--worker claude` worker (R9).
9. The gate is GREEN (`python3 plugin/scripts/check.py`) with the new
   `board_snapshot` + dashboard unit tests; the off-path (`NoopBoardWriter`) leaves
   orchestration byte-identical.
10. The vendoring decision is recorded as `docs/adr/0006-observability-vendored-asset.md`
    with the ARCHITECTURE invariant-1 scope note; **review-arch** blesses the
    relaxation as scoped and offline-preserving.

## Open factors — triage

Resolved by the human (the two scope-defining forks), recorded here:

- **Graph scope = the whole Linear board** (not the run's working set) — the user's
  "프로젝트 전체 진행상황" intent. ⇒ R1 whole-board producer + the `board.json` feed.
- **Vendor a graph library** (vs hand-rolled vanilla SVG) — the user accepted the
  richer interaction at the cost of the single-file grain. ⇒ R6/R7 (scoped, offline,
  ADR-recorded).

Decided on the merits (mechanical/technical — no taste fork):

- **Library = Cytoscape.js + cytoscape-dagre + cytoscape-expand-collapse.** Purpose-
  built for an interactive layered DAG with data-driven node styling, `tap` events for
  the overlay, pan/zoom, incremental data updates without a relayout, and subtree
  collapse — and it is **vanilla** (no React/framework pulled in) with a vendorable UMD
  bundle. Alternatives considered: `dagre-d3` (more bespoke render code), `elkjs`
  (heavier, async layout), `mermaid` (re-renders the whole diagram from text on each
  change → wrong for a live-streaming, click-to-overlay surface). The vendored bundle
  weight is the one cost (a few hundred KB checked in) — accepted given the explicit
  vendoring decision; this is the one technical choice a reviewer may still veto.
- **Layer = wave, drawn left→right.** Mirrors the orchestrator's dispatch model so the
  picture *is* the scheduler's model; orientation is a UI default the viewer can flip.
- **No fake per-ticket "percent".** Per-ticket progress is qualitative (phase + live
  token fill + turns); project progress is the DAG done-fraction (R4).
- **Board refresh at poll cadence**, throttled by `board_snapshot_interval_s` (default
  = poll interval) so a large board never out-paces the existing dispatch poll (R9).
- **Graph is the `/` centerpiece**, existing lists → collapsible side rail (R4) — the
  user's "지도 + 결정 inbox" framing.

No genuine product-direction / taste fork remains open — the two such forks were
escalated and answered before drafting.

## Hand-off

ExecPlan in `docs/exec-plans/completed/2026-06-26-project-dependency-graph-view.md`
references this spec and owns the build. Suggested milestone order (the ExecPlan
owns the final cut): (M1) `board_snapshot.py` pure core + writer + tests; (M2)
orchestrator poll-tick wiring + config knob + a **live whole-board snapshot proof**
(a real daemon poll writes a correct `board.json`); (M3) `/api/v1/board` + the fixed
vendored-asset route + the ADR/ARCHITECTURE note; (M4) the graph-view UI restructure
+ node painting + the re-homed session overlay; (M5) scale/collapse + the
`playwright-cli` behavioral pass (incl. the offline-no-CDN proof) + the cross-runtime
check. `review_level: full` — the dashboard is the live exec surface, the diff adds a
new asset-serving route and **relaxes an architecture invariant**, so **review-arch**
(the relaxation) and **review-security** (the new served-asset route) are in budget
alongside the always-on spec-compliance + code-quality and the reliability persona.
