---
status: active
last_verified: 2026-06-27
owner: harness
type: exec-plan
description: Re-skin the Director dashboard's project-graph view to the higher-fidelity design language — HTML node-cards, wave labels, header done-fraction, state-aware SVG edges, a richer typed session overlay — by hand-rolling the render and dropping the vendored graph library, reusing the existing backend (board.json/routes/SSE/answer-console) unchanged.
base_commit: 407ebd5
review_level: full
---
# Project-graph view — design re-skin (build)

## Goal

A human opening `http://127.0.0.1:<port>/` sees the whole-board DAG rendered in the
**higher-fidelity design language** of the operator-validated reference: each ticket is an
**HTML node-card** (identifier + state badge + 2-line title + — for in-flight — `phase · Nt`
+ a token-activity bar), positioned in `wave N`-labeled topological layers; a **header** shows
a `done/total` progress bar + live `active/blocked/failed` counts; blocker edges are
**state-aware SVG bezier** curves (active=green, done=dim, blocked=amber, backlog=dashed);
clicking a node opens a **redesigned session overlay** (telemetry strip + typed event stream
over the existing per-ticket SSE). The graph is **hand-rolled DOM+SVG** — the vendored
Cytoscape/dagre bundles (~670KB) and their `/assets/*` routes are **gone**; the client
positions nodes purely from the server's `layer`/`layers`/`edges`. The operator **answer
console** (reply/done/blocked/escalate; requeue/abandon; CSRF + loopback fence), the live SSE
paint, the history panel, and the labeled empty-state all **still work**. No React/Vite, no
build step, stdlib-Python served single PAGE; ADR 0006's relaxation is narrowed/retired.
Definition of done = spec acceptance criteria 1–8 demonstrably pass and the gate is GREEN.

## Context

Builds from the product-spec
[2026-06-27-project-graph-view-reskin](../../product-specs/2026-06-27-project-graph-view-reskin.md)
— that spec owns the design (R1–R8, the durable design tokens, the render contract,
the 7-bucket mapping). **Do not re-derive the spec.** Required reading:

- The shipped backend this sits on (reused unchanged):
  [2026-06-26-project-dependency-graph-view](../completed/2026-06-26-project-dependency-graph-view.md)
  — `director/board_snapshot.py` (`build_board_view` → `{nodes,edges,layers}`; the server
  already computes the layering), the `/api/v1/board` route, `/api/v1/state` + `/api/v1/stream`
  SSE, the per-ticket `/api/v1/ticket/<id>/{events,stream}`.
- `director/dashboard.py` — the PAGE (lines ~255–672): the graph render block to REPLACE
  (`<script src="/assets/cytoscape*">` + `nodeStyle()`/`paintGraph()`/`loadBoard()`, ~320–671)
  and the blocks to PRESERVE (the answer console `renderPending`/`answer`/`btn(...)` ~416–439,
  history `renderHistory` ~459, root poll/SSE plumbing, the per-ticket drill `openDrill`
  ~470–531, the `__DIRECTOR_TOKEN__` meta + `_authorized` write fence). The `_ASSETS` map +
  `_asset` route + asset routes to SHRINK/REMOVE.
- `docs/adr/0006-observability-vendored-asset.md` — to amend (relaxation narrows/retires).
- The **running sample** I can drive playwright against: `python3 -m director.dashboard
  --port 8788 --board-dir <scratch>/sample-ui/board --status-dir …/status --events-dir …/events`
  (10-node/5-layer DAG, LIN-3 in-flight @20,560t, an 8-event stream) — the behavioral proof
  vehicle for every milestone (regenerate via the scratch `make_sample_ui.py`).

## Approach (self-generated alternatives)

- **A — Incremental in-place rewrite of the PAGE graph block.** Replace Cytoscape with
  hand-rolled DOM+SVG milestone by milestone, the page bootable & gate-green at each step
  (ugly-but-working → progressively styled). Tradeoff: a few transitional looks between
  milestones; smallest blast radius, every step verifiable on the sample.
- **B — Big-bang PAGE rewrite.** Rewrite the whole PAGE string at once, then wire. Tradeoff:
  fastest to the final look but a huge undifferentiated diff, hard to gate incrementally, and
  a preserved surface (answer console / CSRF) could break unnoticed inside the churn.
- **C — Standalone static prototype first, then port.** Build the new render as a static HTML
  against fixture data, iterate visually with playwright, then port into dashboard.py.
  Tradeoff: de-risks layout/visual in isolation but duplicates work and delays integration.
- **Chosen: A**, seeded by C's instinct — the *first* milestone proves the hand-rolled render
  core against the **live sample dashboard** (reusing the running :8788 sample as the
  fixture), so layout/pan-zoom is de-risked early without a throwaway prototype, then the
  design system + paint + overlay layer on incrementally. Every milestone stays bootable,
  gate-green, and playwright-verifiable on the sample; the security-sensitive write console
  is preserved continuously rather than reconstructed (B's risk). (Mirror in Decision log.)

## Assumptions & open questions (self-interrogation)

- Assumption: the server's `/api/v1/board` already returns `layer`/`layers`/`edges` good
  enough to position without client topology work — **true** (verified: the shipped
  `build_board_view` returns all three; the sample renders 5 layers). If wrong, the client
  would need its own layering — but it isn't.
- Assumption: ~150 DOM cards + ~200 SVG paths render acceptably (no virtualization needed) —
  taken as given (the reference targets the same 100+-node scale with DOM); what breaks if
  wrong: a very large board janks → revisit with a viewport cull (out of scope now).
- Assumption: dropping the `/assets/*` graph-lib routes breaks only the `AssetRouteTest` +
  the root-page cytoscape markers — those are updated *within* the milestone that drops them,
  keeping each milestone gate-green.
- Open: token readout is an **absolute count**, not a 0..1 context fraction → resolved (spec):
  show `·{total}t` + pulse, omit the proportional bar (no honest denominator).
- Open: ready-vs-backlog has no node-level Linear state-type → resolved (spec): derive from
  blocker-doneness (all blockers done → ready, else backlog).
- Open: icons/fonts → resolved (spec): inline SVG/unicode glyphs + system font stacks, no new
  vendored asset (so the page can reach **zero** served assets → ADR 0006 can retire).
- No Taste/Style escalation pending — the one product fork (re-skin in-stack vs re-platform)
  was settled with the operator before the spec; remaining calls are technical + recorded.

## Milestones

- **M1 — Hand-rolled render core; rip out the graph library.** Replace the Cytoscape graph
  block in the PAGE with a hand-rolled renderer: fetch `/api/v1/board`, position each node
  `id` at `x = PAD + layer·stride`, `y =` its centered index within `layers[layer]`, render
  nodes as absolutely-positioned `<div>` cards (minimal styling this milestone) and edges as
  SVG bezier `<path>`s; hand-rolled pan (drag) / zoom (wheel) / fit on a transformed canvas
  inner div; expose `window.__graph = {nodes:[{id,layer,cls,label}], edges}` (replacing
  `window.cy`). DELETE `director/assets/{cytoscape.min.js,dagre.min.js,cytoscape-dagre.js}`,
  remove the `<script src="/assets/...">` tags, shrink `_ASSETS`/`_asset` + the asset routes,
  and update `tests/test_director_dashboard.py` (`AssetRouteTest` → assert `/assets/cytoscape.min.js`
  is 404; root-page test → drop cytoscape markers, add `window.__graph`/node-card markers).
  Everything else (rail, overlay, answer console, SSE, history) keeps working with current
  styling. At the end: the page renders the sample board as positioned cards + edges with no
  graph lib. Run: `python3 plugin/scripts/check.py` (GREEN) + drive the :8788 sample with
  `playwright-cli` → single-eval `window.__graph` has 10 nodes positioned by layer + 8 edges,
  and `curl /assets/cytoscape.min.js` → 404, page source contains no `cdn`.
- **M2 — Design system + node-cards + page chrome.** Apply the spec's design tokens: the
  7-bucket state palette (border/bg/text/glow), the full card anatomy (identifier + state
  badge + 2-line clamped title + in-flight `phase · Nt` + bottom token bar), glow/pulse for
  in-flight/failed, dimmed done nodes; the header bar (GitBranch mark + `project-dependency-graph`
  + LIVE + `done/total` progress bar + `N active / N blocked / N failed` counts from
  board∪state); `wave N` layer labels; the legend + zoom controls; inline SVG/unicode glyphs +
  system fonts (no new asset). At the end: the sample renders as the reference's visual
  language. Run: gate GREEN + playwright eval → a node's classes/label match its state, the
  header shows `done/total`, `wave` labels present, `/assets` dir has no JS.
- **M3 — Live paint merge + state-aware edges + opt-in focus/collapse.** Wire the live paint
  to the new DOM: merge `/api/v1/state` (+ the `/api/v1/stream` SSE) — in_flight→in_progress
  card + `·{total}t` + pulse, recent→done/failed, stuck→blocked, `in_cycle`→cycle ring, a
  just-claimed unioned transient; the 7-bucket mapping incl. ready-vs-backlog by
  blocker-doneness. State-aware edge coloring/markers. Hand-rolled frontier-focus (dim settled
  done) + subtree-collapse (dbl-click), opt-in, surviving a repaint. At the end: with the
  sample `status.json`, LIN-3 paints in_progress + token readout + pulse, edges colour by
  endpoint state, focus dims done nodes. Run: gate GREEN + playwright eval → LIN-3 class
  `in_progress`+label `·20560t`, a blocked-target edge is amber/dashed vs an active green edge.
- **M4 — Session overlay redesign (preserve the write console).** Restyle the per-ticket
  overlay to the reference: header (identifier + state badge + live dot), a telemetry strip
  (phase / turns / token readout), and **typed** event rendering — each `ticket_events` kind
  (`turn_started`/`agent_message`/`tool_call`/`token_usage`/`turn_ended`) → a colour + glyph
  prefix + ts — streaming live (in-flight) / replayed (terminal) over the UNCHANGED per-ticket
  SSE; labels footer. The operator **answer console** (reply/done/blocked/escalate;
  requeue/abandon) is re-homed into the new layout with its CSRF token + loopback fence and
  `renderPending` contract intact. At the end: tapping a sample node streams typed events; the
  answer console still POSTs `/api/v1/answer` with the token. Run: gate GREEN (the preserved
  answer/history/SSE marker tests pass unchanged) + playwright → node-tap overlay shows typed
  events; a `reply` POST carries `__DIRECTOR_TOKEN__`.
- **M5 — ADR amend + cleanup + behavioral acceptance + completion gate.** Amend ADR 0006
  (the relaxation narrows to zero served graph-lib bytes / retires; record supersession) + the
  ARCHITECTURE invariant-1 scope note; remove any dead asset-serving code; final marker/behavioral
  test sweep. Behavioral: a full `playwright-cli` pass over the sample proving spec AC1–8 (the
  offline/no-CDN proof, the preserved write console, the 404'd asset routes) captured into
  Outcomes. At the end: spec AC1–8 demonstrably pass, the gate is GREEN, ADR/ARCH reflect the
  narrowed relaxation. Run: gate GREEN; then the completion-gate review panel (review_level:
  full → spec-compliance → code-quality + arch + reliability + security).

## Progress log
- [ ] (2026-06-27) Plan created from the spec; base_commit 407ebd5, review_level full.

## Surprises & discoveries

## Decision log
- 2026-06-27: Chose incremental in-place rewrite (Approach A) seeded by C — the hand-rolled
  render core is proven against the live :8788 sample first (de-risk layout/pan-zoom without a
  throwaway prototype), then design/paint/overlay layer on incrementally; the page stays
  bootable + gate-green + playwright-verifiable and the security-sensitive answer console is
  preserved continuously, not reconstructed (rejecting B's big-bang churn risk).
- 2026-06-27: Client does NOT recompute topology — it consumes the server's `layer`/`layers`/
  `edges` from `/api/v1/board` and only positions (the reference recomputes; we don't need to,
  invariant 4). This makes the hand-roll *simpler* than the reference, not harder.
- 2026-06-27: `review_level: full` — the rewrite touches the live dashboard exec surface and
  re-homes the security-sensitive answer console (CSRF/loopback fence must survive), narrows an
  architecture invariant + ADR 0006, and the render must stay total/degrading — so arch +
  reliability + security risk personas are all in budget alongside the always-on two.

## Feedback (from completion gate)

## Outcomes & retrospective
