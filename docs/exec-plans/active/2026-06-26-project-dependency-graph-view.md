---
status: active
last_verified: 2026-06-26
owner: harness
type: exec-plan
description: Build the project dependency-graph view — orchestrator persists a whole-board snapshot, the dashboard renders it as a layered DAG (layers = waves) painted live from status.json with a click-to-open per-ticket session overlay, powered by a single vendored offline graph library.
base_commit: 9fc404d7b53d70f16af40c827e6ad856582ec553
review_level: full
---
# Project dependency-graph view — build

## Goal

A human running a Director daemon (or just after one polls) opens
`http://127.0.0.1:<port>/` and sees **the whole project as a layered DAG**: every
ticket on the configured Linear board is a node, blocker edges connect them, and
nodes are arranged in topological layers where **same layer = parallel-schedulable,
next layer = serial dependency** (the orchestrator's own wave model, made visible).
Each node is painted with its **live lifecycle** (backlog / ready / in-flight /
blocked / done / failed) merged from `status.json`; in-flight nodes show a live token
fill; blocked/cycle nodes are marked. Clicking a node opens an **overlay anchored to
it** that streams that ticket's live session events (in-flight) or replays its
recorded timeline (terminal), reusing the existing per-ticket SSE. Completed subtrees
collapse, and the board pans/zooms on a 100+-node graph. The whole graph library is
**served from a local checked-in asset — no CDN, no network fetch at render time**.
If `board.json` is absent/torn the page degrades to the existing flat-list side rail
and the live `status` overlay still works — the graph is additive, never a gate.
Definition of done = acceptance criteria 1–10 of the spec demonstrably pass and the
gate is GREEN.

## Context

Builds from the product-spec
[project-dependency-graph-view](../../product-specs/2026-06-26-project-dependency-graph-view.md)
— that spec owns the design (R1–R9, components, contracts); this plan owns the build
order and proof. **Do not re-derive the spec.** Required reading for a novice:

- The existing observability substrate this view sits on:
  - `director/status.py` — the run snapshot (`StatusWriter`, `read_status`,
    `build_view`-feeding `snapshot()`); the atomic temp+`os.replace` write grain and
    the `NoopStatusWriter` off-path precedent this plan mirrors for `BoardWriter`.
  - `director/dashboard.py` — the localhost stdlib `http.server`: `build_view`,
    `_Handler._route`/`_ROUTES`, the SSE `_stream_loop`, the per-ticket
    `/api/v1/ticket/{id}/(events|stream)` routes + the inline `PAGE` drill-down JS
    (the overlay this plan re-homes onto a node), the `_DashboardServer` server-held
    dirs, and the CSRF-fenced `POST /api/v1/answer` (unchanged).
  - `director/ticket_events.py` — the per-ticket session-event JSONL + `read_events`
    + `derive_timeseries` (the overlay's data source; unchanged).
  - `director/board/linear.py` — `fetch_issues_by_states` (paginated, reused with the
    FULL state-id set), `_normalize_candidate` (produces `{id, identifier, title,
    state, state_type, labels, blockers:[{id,state_type}]}` — already carries the DAG
    edges via `_parse_blockers`), and `workflow_states` (all states, resolved at
    orchestrator startup).
  - `director/orchestrator.py` — the poll loops (`run_forever` daemon poll-tick,
    `run_once`/`run_until_drained` batch polls), the `status`/`events` writer
    constructor wiring (`orchestrator.py:383,389`), and the wall-clock-anchored
    monotonic reconcile cadence (the throttle pattern this plan reuses for the board
    snapshot).
  - `director/config.py` — `DEFAULTS["director"]` + the resolve/alias discipline
    (ARCHITECTURE invariant 5) for the new `board_snapshot_interval_s` knob.
- ARCHITECTURE.md "Host runtime (`director/`) invariants" — invariant 1 (stdlib-only,
  **Python**-scoped), 3 (loopback/fixed-route/zero-traversal/read-only-by-default), 4
  (pure core, thin transport), 5 (declarative knobs). The vendored-JS-asset relaxation
  is scoped against invariant 1 and recorded as ADR 0006 (M2).
- RELIABILITY.md R9 (atomic snapshot writes), R12 (instrument extractors are total),
  R14 (read-API listeners fail soft).
- The predecessor specs (observability-dashboard / -polish / per-ticket-session-event-
  stream) for the producer/store/consumer file-bridge rationale.

## Approach (self-generated alternatives)

**Where the topology/layer math lives:**
- A: pure server-side `build_board_view` assigns the layer (longest-path over the
  blocker DAG); the client merges board×status×events and the vendored lib renders the
  given rank. — Keeps the meaningful "serial vs parallel" computation pure and
  unit-testable, matches the scheduler's wave model, honors invariant 4. Slightly more
  server code.
- B: ship raw nodes; let dagre compute layers in the browser. — Less server code, but
  the load-bearing semantic (layer = wave) becomes untestable browser state and drifts
  from the orchestrator's model; violates invariant 4.
- **Chosen: A** — the layer is a product semantic (it *is* the wave), so it belongs in
  a pure, tested function, not in the renderer.

**Build order / risk sequencing** (the dominant unknown is whether the vendored
library can do layered-DAG + node-anchored overlay + subtree-collapse **offline in a
no-bundler single page** — PLANS.md "unknowns get PoC milestones"):
- A: bottom-up producer-first (pure core → wiring → routes → UI), defers the library
  unknown to the end — risk discovered late.
- B: **front-load the library feasibility as an early spike against a static fixture
  board**, in parallel with the (unknown-free) pure core, so the dominant risk is
  retired before the producer wiring and full UI are invested.
- **Chosen: B** — M1 pure core (no unknowns) and M2 library-spike (the unknown) are
  independent; proving the lib early against a fixture means M3/M4 build on a known-good
  rendering substrate. The spike's keepers (vendored asset, asset route, `/api/v1/board`,
  ADR) stay; only the static fixture is throwaway, replaced by the real producer in M3.

This refines the spec's suggested milestone order (which deferred the lib to M3): the
ExecPlan owns the build cut, and the lib is the risk to retire first.

## Assumptions & open questions (self-interrogation)

- Assumption: **Cytoscape.js + cytoscape-dagre + cytoscape-expand-collapse load as
  local UMD files in a no-bundler single page and render layered offline.** What breaks
  if wrong: R6/M2. Mitigation: M2 is a feasibility spike *before* the full UI invest; if
  the stacked-extension UMD path fails offline, the recorded fallback is dagre-d3 (layout
  only, more render code) or the hand-rolled vanilla-SVG layered layout (the option not
  chosen at brainstorming) — both keep R1–R5/R7–R9 intact, only R6's library identity
  changes. Record the resolution in the Decision log.
- Assumption: `fetch_issues_by_states(team, ALL_state_ids)` returns every issue with its
  `blockers` populated — verified: it runs `_normalize_candidate` → `_parse_blockers`
  over `_CANDIDATE_FIELDS` (which includes `inverseRelations`). The orchestrator already
  holds all state ids (`workflow_states(team)` at startup, `orchestrator.py:55`).
- Assumption: a whole-board fetch at poll cadence is acceptable load — bounded by
  `board_snapshot_interval_s` (default = poll interval, spec R9), so the board is never
  fetched faster than the dispatch poll already polls.
- Open: how to prove the live whole-board snapshot without flaking on a real board →
  resolved: M1/M3 unit + integration tests drive a `FakeBoard` (the existing
  zero-network test double); the M5 behavioral pass uses a real dogfood daemon run
  (DIRECTOR_RUNBOOK) for the cross-runtime + live-paint proof.
- Open: graph as `/` centerpiece vs a new `/graph` route → resolved (spec R4): the graph
  is the `/` centerpiece, existing lists relocate to a collapsible side rail; the
  existing JSON routes stay byte-unchanged (superset preserved).
- Open: node set when a ticket is claimed between board refreshes → resolved (spec R4):
  the client unions board nodes with any status-only ticket so a just-claimed ticket
  appears immediately.
- No genuine product-direction/taste fork remains open — the two (whole-board scope,
  vendored library) were escalated and answered before the spec was written.

## Milestones

- **M1 — `board_snapshot.py` pure core + writer + tests (no unknowns; foundation).**
  Scope: the whole producer logic surface, stdlib-only, mirroring `status.py`. At the
  end there newly exists `director/board_snapshot.py` with: pure
  `build_board_view(nodes, *, now) -> {nodes, edges, layers, generated_at}` (topological
  layer = longest-path-from-roots over the blocker DAG, cycle-safe with an `in_cycle`
  flag and no hang, orphan → layer 0, plus `edges` and the layer-grouped `layers` rank
  hint); `BoardWriter`/`NoopBoardWriter` (`write(nodes)` → atomic temp+`os.replace` of
  `{nodes, generated_at}`, swallow-all → `last_error`); `read_board(base) -> dict|None`
  (tolerant: missing/torn/unreadable → `None`); `_root`/`_board_path` honoring
  `$DIRECTOR_BOARD_DIR` then the `.claude/harness/director-board` default. Run:
  `python3 -m pytest tests/test_board_snapshot.py -q`. Expect: layer assignment correct
  on chain / diamond / parallel-fan fixtures; a **cycle fixture returns without hanging**
  and flags members `in_cycle`; an orphan lands at layer 0; `BoardWriter` round-trips
  through `read_board`; a torn final line and an absent file both read as `None`.

- **M2 — Library feasibility spike: vendor offline + asset route + `/api/v1/board` +
  ADR (retire the dominant unknown).** Scope: prove R6 end-to-end against a *static
  fixture* board before investing in the producer/UI. At the end there newly exists:
  `director/assets/` holding the checked-in Cytoscape + cytoscape-dagre +
  cytoscape-expand-collapse UMD files; a **fixed asset route** in `dashboard.py` (a
  constant `{route → vetted file}` map, served with the right content-type, zero
  request-derived path); the `GET /api/v1/board` route returning
  `build_board_view((read_board() or {}).get("nodes", []))`; a throwaway fixture
  `board.json` (or a `--board-dir` pointing at a fixture) to render against; and
  `docs/adr/0006-observability-vendored-asset.md` + a one-sentence ARCHITECTURE
  invariant-1 scope note (R7) registered in `docs/adr/index.md`. Run: serve the
  dashboard against the fixture and drive it with the `playwright-cli` skill. Expect: a
  layered DAG renders from the fixture; a node `tap` opens an overlay; a subtree
  collapses; pan/zoom work; **browser devtools show no external (CDN) network request**
  (offline-vendored proof); `GET /assets/<lib>.js` serves the file and `/assets/../…` →
  404. If the offline stacked-UMD path fails, record the fallback decision here and
  proceed with it (assumptions §1).

- **M3 — Orchestrator poll-tick wiring + config knob + live whole-board snapshot proof.**
  Scope: replace the fixture with the real producer. At the end the orchestrator
  constructs a `BoardWriter` (NoopBoardWriter when the status surface is off → off-path
  byte-identical) and, in the `run_forever` poll tick (and the `run_once` /
  `run_until_drained` batch polls), throttled by a monotonic `last_board_snapshot`
  against the new `config.DEFAULTS["director"]["board_snapshot_interval_s"]` (default =
  poll interval, aliased — no parallel literal), fetches the full board
  (`fetch_issues_by_states(team, all_state_ids)`) and calls `board_writer.write`; the
  fetch+write is exception-total at the callback boundary (skips one snapshot, never
  gates the poll). Run: `python3 -m pytest tests/test_orchestrator*.py tests/test_config.py -q`
  driving a `FakeBoard` with a multi-state blocker DAG. Expect: after a poll tick,
  `board.json` exists with every fixture issue and its blockers; a `NoopBoardWriter` run
  produces **byte-identical** orchestration (no snapshot written, dispatch unchanged); a
  raising `FakeBoard.fetch_issues_by_states` skips the snapshot without raising into the
  poll; the knob resolves through `config` and an `inspect.signature` drift test pins it.

- **M4 — Graph-view UI restructure: real merge, node painting, re-homed overlay.** Scope:
  turn the M2 spike into the real centerpiece view. At the end `dashboard.py`'s inline
  `PAGE` builds the Cytoscape graph from the **live** `/api/v1/board` × `/api/v1/state`
  merge (lifecycle painted per node — backlog/ready/in-flight/blocked/done/failed, live
  token fill on in-flight, `in_cycle` cluster highlight), **unions** status-only tickets,
  and wires `node.on('tap')` to the existing per-ticket overlay logic re-homed from the
  bottom drill panel to a node-anchored panel (in-flight → `/ticket/{id}/stream` live;
  terminal → `/ticket/{id}/events` recorded replay; close → close EventSource); the
  existing `in_flight`/`stuck`/`recent`/`pending` lists relocate into a **collapsible
  side rail** (the fenced `POST /api/v1/answer` operator controls unchanged); all values
  via `textContent`. Run: drive with `playwright-cli` against a live `FakeBoard`/daemon.
  Expect: nodes recolor live as a ticket moves claimed→running→done; clicking a running
  node streams its events into a node-anchored overlay; clicking a done node replays its
  recorded timeline; the side rail still answers a pending request.

- **M5 — Scale, degradation, and the full behavioral + cross-runtime pass.** Scope: the
  completion-gate behavioral acceptance. At the end: completed subtrees collapse by
  default with frontier-focus on a 100+-node board; `board.json` absent/torn degrades to
  the side-rail lists ("no board snapshot yet") with the `status` overlay still live; the
  view renders pre-run from a first-poll snapshot. Run: a real dogfood daemon run
  (DIRECTOR_RUNBOOK) once with a codex worker and once with `--worker claude`, driven via
  `playwright-cli`; plus the absent-board degradation case. Expect: spec acceptance 3–8
  all observably pass on both runtimes, identical UI path; the 100+-node board stays
  navigable; capture the transcript/screenshots into Outcomes.

## Progress log
- [x] (2026-06-26) Plan authored; spec committed (8bc18d8); base_commit 9fc404d.
- [x] (2026-06-26) **M1 done.** `director/board_snapshot.py` (pure `build_board_view`
  with Kahn longest-path layering + cycle/orphan/dangling-safe `in_cycle`,
  `BoardWriter`/`NoopBoardWriter` atomic write, tolerant `read_board`, `main()` read
  surface) + `tests/test_board_snapshot.py` (18 tests: chain/diamond/parallel layering,
  cycle-no-hang, self-block, descendant-of-cycle, dangling-drop, projection, garbage
  tolerance, writer round-trip, torn/absent read, Noop off-path). `pytest` 18/18 GREEN;
  `main()` smoke correct (a→b edge, b@layer1); full gate GREEN.
- [x] (2026-06-26) **M2 done — library feasibility RETIRED (the dominant unknown).**
  Vendored `director/assets/{cytoscape.min.js, dagre.min.js, cytoscape-dagre.js}`
  (pinned, offline). `dashboard.py`: fixed `_ASSETS` route + `_asset` handler,
  `GET /api/v1/board` (build_board_view over read_board), `/graph` spike page (loads
  the libs from local /assets, renders the layered DAG, node tap → session overlay
  over the existing /ticket/<id>/events route, dbltap → manual descendant-hide collapse),
  `window.cy` introspection hook, `--board-dir`. ADR 0006 + ARCHITECTURE invariant-1
  scope note + adr/index registered. **9 new dashboard tests** (board route shape,
  graph page references LOCAL assets + no "cdn", each vendored asset served as JS,
  unknown/traversal asset → 404, POST → 405) — 75/75 dashboard+board tests GREEN.
  **Live playwright proof (offline):** `window.cy.nodes()===8 / edges===7`, status
  "8 tickets · 7 deps · 4 waves", dagre layered layout offline (L1=20 < L2=119 < L4=217
  — serial deepens rightward, diamond apex furthest right), in_cycle=[LIN-7,LIN-8],
  console shows assets+board served from 127.0.0.1 (only error = favicon 404, benign),
  **no CDN/external request**. Render + offline + routes = PROVEN; interactive tap/
  collapse capture was blocked by playwright env flakiness (page reset between calls) —
  handlers are wired + the consumed events route is unit-tested; the full interactive
  behavioral pass is M5's scope.
- [x] (2026-06-26) **M3 done — orchestrator persists the whole board.** `config.py`:
  `board_snapshot_interval_s` knob (None = track `poll_interval_s`; config-only, fail-loud
  on a bad value). `board_snapshot.py`: `BoardSnapshotter` (injected fetch thunk + writer +
  throttle, fires first-call-then-per-interval, exception-total) + `NoopBoardSnapshotter`.
  `orchestrator.py`: all three poll loops (`run_once`/`run_until_drained`/`run_forever`)
  take `board_snapshotter=None` (→ Noop, byte-identical off-path) and call `maybe_snapshot`
  at the poll point; `main()` builds the real one (whole-board fetch = `fetch_issues_by_states`
  over ALL `workflow_states` ids, so backlog/done/etc. appear), shares the `--no-status`
  switch, writer in the status-dir sibling `director-board`. **+11 tests** (BoardSnapshotter
  throttle/exception-total/Noop; config default/override/malformed; run_once + run_until_drained
  persist the whole board incl. blocker DAG; Noop off-path writes nothing). 274/274 suite GREEN;
  `--mock --once` smoke writes a real `board.json`. Off-path proven byte-identical.
- [ ] **M4 — next.** graph-view UI restructure (promote graph to `/`) + live `/api/v1/board`×
  `/api/v1/state` node painting + re-homed session overlay + side rail.
- [ ] M5 — scale/collapse + playwright behavioral + cross-runtime pass.

## Surprises & discoveries
- 2026-06-26 (M2): **`cytoscape-expand-collapse` is the wrong tool.** It collapses
  *compound* (parent/child nesting) nodes, not DAG-successor subtrees — so "collapse a
  completed subtree" can't use it. DAG subtree collapse is a one-liner manual
  descendant-hide (`node.successors('node').style('display', …)`). Dropped the library
  (−31 KB vendor weight); the spike corrected the spec's R6 library list. Vendor set is
  now the minimum for a crossing-minimized layered layout: cytoscape + dagre +
  cytoscape-dagre.
- 2026-06-26 (M2): **`cytoscape-dagre` registered + laid out OFFLINE on the first try**
  from local `/assets/*` UMD bundles in a no-bundler single page — the dominant unknown,
  retired. dagre's ranks matched the server's longest-path layers (L1<L2<L4).
- 2026-06-26 (M2): **playwright env is flaky here** — the page intermittently reset to
  blank between separate `playwright-cli` invocations (`body.innerHTML.length===0`), and
  a screenshot captured a blank frame. Render was proven authoritatively via the live
  cytoscape instance state (`window.cy.nodes().length===8`, dagre positions) instead;
  per the playwright-cli skill ("stop after 2–3 failed browser attempts") the interactive
  tap/collapse live-capture is deferred to M5's behavioral pass (handlers are wired; the
  events route they call is unit-tested). Not a product defect — a harness/env artifact.

## Decision log
- 2026-06-26: Layer math is server-side and pure (`build_board_view`), not browser-
  computed — the layer *is* the scheduler's wave, a product semantic that must be tested
  (Approach A; invariant 4).
- 2026-06-26 (M2): Vendor set reduced to **3** (cytoscape + dagre + cytoscape-dagre);
  `cytoscape-expand-collapse` dropped (compound-only, wrong for DAG subtree collapse →
  manual descendant-hide). Recorded in ADR 0006.
- 2026-06-26 (M2): M2 is an additive **`/graph` spike page** — the flat-list `/` is
  untouched; M4 promotes the graph to `/`. Keeps M2 low-risk (no disturbance to the
  shipped page) and the keepers (assets/route/board-route/ADR) survive into M4.
- 2026-06-26 (M2): Exposed `window.cy` on the graph page — an introspection hook for
  debugging and the behavioral test (`window.cy.nodes()`, `emit('tap')`); harmless on a
  read-only localhost instrument.
- 2026-06-26 (M3): `BoardSnapshotter` takes an injected **fetch thunk** (not the board
  object) — decouples the throttle/cadence logic from the board interface, so it is
  pure-testable with a fake fetch (no network) and `main()` owns the "whole board" query
  shape. Throttle clock advances even on a failed fetch (best-effort, no hammer).
- 2026-06-26 (M3): "Whole board" = `fetch_issues_by_states` over **all** `workflow_states`
  ids (not just the logical ready/started/done map), so backlog/canceled/in-review tickets
  appear too — the project view, not the dispatch view. Re-resolves the id set each snapshot
  (cheap at the throttled cadence; handles a state added mid-run).
- 2026-06-26 (M3): `board_snapshot_interval_s` is **config-only** (no CLI flag, unlike
  poll/reconcile) — a deployment-tuning knob, not a per-invocation one; `None` tracks
  `poll_interval_s` so a host that retunes the poll cadence gets matching snapshot cadence
  for free. Shares the `--no-status` visibility switch (no separate disable knob, YAGNI).
- 2026-06-26: Library feasibility front-loaded as an M2 spike against a static fixture —
  the offline no-bundler stacked-UMD render is the dominant unknown, retired before the
  producer wiring and full UI invest (Approach B). Keepers (asset, route, ADR) survive
  the spike; only the fixture is throwaway.
- 2026-06-26: ADR 0006 + the ARCHITECTURE invariant-1 scope note land in M2 (with the
  vendored asset), not M3 — the relaxation materializes the moment the asset is
  introduced, so the record co-lands with it (R7; "not in repo = does not exist").
- 2026-06-26: `board.json` stores the raw `{nodes, generated_at}`; the layer/edge
  derivation runs on read (`build_board_view`), keeping the stored artifact close to
  source (matches the spec R3 contract fix).

## Feedback (from completion gate)

## Outcomes & retrospective
