---
status: draft
last_verified: 2026-06-28
owner: harness
phase: symphony/06-graph-view-reskin
type: product-spec
description: Re-skin the Director dashboard's project-graph view to a higher-fidelity design language (HTML node-cards, wave labels, header done-fraction, state-aware SVG edges, a richer typed session overlay) by hand-rolling the render and DROPPING the vendored graph library — adopting the design without adopting a framework/build step, reusing the existing board.json producer / routes / SSE / answer-console backend unchanged.
---
# Project-graph view — design re-skin (drop the graph lib, keep the backend)

## Problem

The shipped project-graph view ([2026-06-26](2026-06-26-project-dependency-graph-view.md))
is functionally complete but visually thin: nodes are Cytoscape **canvas mini-labels**
("LIN-3 ·20560t"), edges are undifferentiated, there is no project-level done-fraction
readout (the prior spec's own AC3 was satisfied only qualitatively), the topological
"waves" are arranged but unlabeled, and the session overlay is a flat event list. A
higher-fidelity reference design exists (Figma-generated, operator-validated) that renders
the **same data model and the same wave-layering** as rich HTML cards with a header
progress bar, "wave N" labels, state-aware bezier edges, and a typed/animated session
overlay — observably better visual hierarchy and information density on the identical
backend.

The reference is authored as a React/Vite/Tailwind/shadcn app, but its actual design
substance imports **only React hooks + lucide icons + inline styles** — it uses none of
the scaffold's component library, and its layout is hand-rolled (`computeLayout` is the
same longest-path wave algorithm this repo already computes server-side in
`build_board_view`). So the design is framework-light in substance and ports to this
repo's constrained frontend without React.

This spec adopts the **design language**, not the stack. Adopting the React/Vite stack
would add a Node build toolchain + npm dependency tree to a Python-stdlib-only host
(ARCHITECTURE invariant 1) and is explicitly fenced out by ADR 0006 ("a framework / a
bundler / a CDN"); it buys no design quality the in-stack re-skin doesn't. The backend
this repo already shipped (the `board.json` producer, `/api/v1/board`, `/assets/*`, the
per-ticket SSE, `/api/v1/state`, the answer console, history) is reviewed (5 SATISFIED),
tested (279), and stack-agnostic — it is reused unchanged; only the PAGE's **graph render
block** is rewritten.

## Requirements

- **R1 — Node cards (HTML, not canvas).** Each board ticket renders as an
  absolutely-positioned HTML card (~168×74) showing: the `identifier`, a state badge,
  the `title` clamped to 2 lines, and — for an in-flight ticket — a `phase · Nt` line and
  a bottom token-activity bar. The card's border/background/glow are driven by the state
  palette (R-tokens below). A human sees a legible labeled card per ticket, not a dot.
- **R2 — Wave labels.** Each topological layer is labeled `wave N` across the top of the
  canvas, consuming the server-computed `layers`. A human can read off which tickets are
  parallel-schedulable (same wave) vs serially dependent (next wave).
- **R3 — Header done-fraction at a glance.** A header bar shows a `done / total` progress
  bar plus live `N active / N blocked / N failed` counts, derived from `/api/v1/board`
  (totals) merged with `/api/v1/state` (live lifecycle). This closes the prior spec's
  qualitative-only AC3.
- **R4 — State-aware edges.** Blocker edges render as SVG bezier curves colored by endpoint
  lifecycle (active=green, done=dim green, blocked=amber, backlog=dashed) with arrow
  markers, consuming the server-computed `edges`. A human can trace the active critical
  path by colour.
- **R5 — Richer session overlay.** The per-ticket overlay (opened on node click, reusing
  the existing per-ticket SSE) gains a telemetry strip (phase / turns / token readout) and
  renders each event **typed** — `turn_started`/`agent_message`/`tool_call`/`token_usage`/
  `turn_ended` mapped to a colour + glyph prefix — instead of a flat list. No change to the
  event *backend* (`director/ticket_events.py`, the `/api/v1/ticket/<id>/{events,stream}`
  routes); only the client rendering changes.
- **R6 — Hand-rolled render; drop the vendored graph library.** The graph is rendered with
  plain DOM + SVG positioned from the server's `layer`/`layers`/`edges` — no Cytoscape, no
  dagre. The three vendored assets (`cytoscape.min.js` 374KB, `dagre.min.js` 284KB,
  `cytoscape-dagre.js` 13KB ≈ 670KB) and their `/assets/*` routes are removed. Pan, zoom,
  fit, opt-in subtree-collapse, and frontier-focus are owned in-page (the reference shows
  these are ~100 lines total). A human can pan/zoom/fit a 100+-node board.
- **R7 — Preserve the control + telemetry surface (behaviorally unchanged).** The operator
  **answer console** (reply / done / blocked / escalate; mergeReview requeue / abandon; the
  CSRF token + loopback Origin/Host fence), the **live SSE paint**, the **history panel**,
  the rail sections, and the labeled empty-state all keep working exactly as before. The
  re-skin is visual: every write/stream/read contract and its tests stay green. Losing or
  weakening the write surface is a spec failure.
- **R8 — Architecture invariants hold (and ADR 0006 shrinks).** Still a loopback
  (`127.0.0.1`) read-only instrument, no new exec/write surface, no build step, a single
  stdlib-Python-served PAGE, `LINEAR_API_KEY` Director-side. Because the re-skin serves
  **fewer** vendored bytes (ideally zero — see open-factor triage on icons/fonts), ADR 0006's
  vendored-asset relaxation is narrowed or retired, not widened.

## Design

### Files
- **`director/dashboard.py`** — rewrite the PAGE's **graph render block** (currently the
  `<script src="/assets/cytoscape*">` tags + `nodeStyle()`/`paintGraph()`/`loadBoard()`,
  dashboard.py ~320–671) and its CSS; restructure the `<style>`/`<body>` to the header +
  canvas + rail + overlay layout. **Keep** the answer-console (`renderPending`/`answer`/
  `btn(...)`), history (`renderHistory`), root-page poll/SSE plumbing, and the per-ticket
  drill SSE (`openDrill`) blocks — only their *styling* may change, not their contracts.
  Shrink `_ASSETS`/`_asset` and the asset routes per R6.
- **`director/assets/`** — delete `cytoscape.min.js`, `dagre.min.js`, `cytoscape-dagre.js`.
  Add nothing if icons/fonts resolve to inline-SVG/system-stack (open-factor triage).
- **`tests/test_director_dashboard.py`** — update PAGE-marker assertions: drop the
  Cytoscape/asset markers (and flip the `/assets/*` route tests to assert they're gone /
  404), add the new render markers (node-card, `wave`, header progress, the hand-rolled
  `window.__graph` hook); **keep every preserved-surface assertion** (answer btns,
  `renderPending`, `__DIRECTOR_TOKEN__`, `/api/v1/stream`, `renderHistory`, empty-state).
- **`director/board_snapshot.py`** — unchanged (pure core + producer). The client consumes
  its existing `/api/v1/board` view verbatim.
- **`docs/adr/0006-observability-vendored-asset.md`** — amend: the relaxation narrows
  (fewer/zero vendored bytes) or is retired; record the supersession.

### Design tokens (durable — captured here so the spec, not the external Figma export, is the source)
State palette (`state_type → {border, bg, text, glow}`; `state_type` is derived client-side
from the node's `state` name via the existing `lifecycleFromState`, extended to the 7 buckets):
```
done        border #16a34a  bg rgba(22,163,74,.07)   text #86efac  glow rgba(22,163,74,.18)
in_progress border #00d68f  bg rgba(0,214,143,.08)   text #6ee7b7  glow rgba(0,214,143,.30)
ready       border #3b82f6  bg rgba(59,130,246,.07)  text #93c5fd  glow rgba(59,130,246,.18)
backlog     border #2d3748  bg rgba(45,55,72,.25)    text #4a5568  glow transparent
blocked     border #d97706  bg rgba(217,119,6,.09)   text #fcd34d  glow rgba(217,119,6,.22)
failed      border #ef4444  bg rgba(239,68,68,.09)   text #fca5a5  glow rgba(239,68,68,.22)
in_cycle    border #a855f7  bg rgba(168,85,247,.09)  text #d8b4fe  glow rgba(168,85,247,.22)
```
Layout: `NODE_W 168, NODE_H 74, H_GAP 56, V_GAP 16, PAD 40`; layer stride = `NODE_W+H_GAP`,
node stride = `NODE_H+V_GAP`; a layer's nodes are vertically centered against the tallest layer.
Page: bg `#070711`, mono accent `#00d68f`, header height 44. Event-type styles:
`thinking #475569 "···"`, `tool_call/tool_use #93c5fd "▶"`, `tool_result #86efac "←"`,
`agent_message/text #c4c4d8 "◆"`, `error #fca5a5 "✕"`. (These map onto our real
`ticket_events` kinds — `turn_started`/`turn_ended` render as faint rule lines.)

### Render contract (client ← server, all existing)
- `GET /api/v1/board` → `{nodes:[{id,identifier,title,state,state_id,labels,blockers,layer,
  in_cycle}], edges:[{from,to}], layers:[[id,…]], generated_at}`. The client **does not
  recompute topology** — it positions node `id` at `x = PAD + layer·stride`, `y =` its
  centered index within `layers[layer]`, and draws each `edge` as an SVG bezier. This is
  strictly simpler than the Figma reference (which recomputes `computeLayout`) because the
  server already did the layering (invariant 4).
- `GET /api/v1/state` (+ the `/api/v1/stream` SSE) → live paint merge: in-flight tickets get
  the `in_progress` treatment + token readout; recent→done/failed; stuck→blocked; `in_cycle`
  nodes get the cycle ring. Same merge logic as today, new DOM target.
- **7-bucket mapping (unambiguous).** Live state wins (in_flight→in_progress, recent→done/
  failed, stuck→blocked); else `in_cycle:true`→in_cycle; else the `state` name maps via the
  existing `lifecycleFromState` (done/in_progress/blocked/cancelled). The remaining todo-ish
  split — **ready vs backlog — is derived from blocker-doneness** (all blockers resolved/done
  → `ready`, else `backlog`), matching the orchestrator's own eligibility, NOT from a Linear
  state-type field (the node carries `state`/`state_id`, not a node-level `state_type`).
- Token readout: our telemetry is an **absolute** token count, not a 0..1 context fraction
  (unlike the reference mock). The node shows the count (`·{total}t`) + an in-flight pulse;
  the proportional fill-bar is bound to a fraction only if a context denominator exists
  (it does not today → omitted, see Non-goals), never a fabricated ratio.

### Behaviors, errors, edge cases
- Absent/torn `board.json` → the labeled empty-state (R7), rail still live (unchanged).
- A node in `layers` but with no live state → painted from its `state` name alone.
- A just-claimed in-flight ticket not yet in the board snapshot → unioned as a transient
  node (the existing `paintGraph` behavior), now a transient-styled card.
- Cycle members (`in_cycle:true`) → cycle ring + banded after the acyclic max layer (the
  server already bands them; the client just styles them).
- Large board: ~150 DOM cards + ~200 SVG paths is well within browser budget; no
  virtualization (YAGNI; the reference targets the same 100+-node scale with DOM).

### Verification / testability
- Backend untouched → `build_board_view` + board-route + producer tests stay green as-is.
- New render is testable two ways: (a) PAGE-marker assertions (node-card class, `wave`
  label text, header `done`/progress markers, typed-overlay markers) — the `assertIn`-on-PAGE
  pattern already used; (b) a live single-eval behavioral check against a **new
  introspection hook** `window.__graph` (replacing `window.cy`) exposing
  `{nodes:[{id,layer,cls,label}], edges}` so a `playwright-cli` single-eval can assert the
  rendered/painted state without screenshots (per the flaky-env memory). The hand-rolled
  positioning math (layer→x/y) is the one piece of client logic worth a focused check.

## Non-goals
- **No React / Vite / Tailwind / shadcn / any framework or build step.** (Invariant 1; ADR 0006.)
- **No backend/data/route/SSE changes.** `board.json` shape, the producer, `/api/v1/board`,
  `/api/v1/state`, the per-ticket events + stream, `/api/v1/answer`, `/api/v1/history` are
  all reused verbatim. (If a real need surfaces, it's a *separate* spec.)
- **No context-window fraction bar** — we have no reliable denominator; show the absolute
  count, never a fabricated ratio.
- **No graph search / advanced filtering** beyond the existing collapse + frontier-focus + pan/zoom.
- **No icon/font dependency** — inline SVG / system stacks only (triage below).
- **Not** a pixel-perfect clone of the Figma export — adopt the design *language*, bound to
  this system's real telemetry and control surface.

## Acceptance criteria
1. `/` renders the board as HTML node-cards (identifier + state badge + 2-line title), one
   per ticket, positioned in `wave N`-labeled topological layers — verified live via
   `window.__graph` single-eval (node count, per-node layer + lifecycle class).
2. The header shows a `done/total` progress bar + live active/blocked/failed counts that
   move with `/api/v1/state`.
3. Blocker edges render as state-colored SVG bezier curves with arrow markers; a
   blocked-target edge is visibly distinct (amber/dashed) from an active one (green).
4. An in-flight ticket shows the `in_progress` card treatment + `·{total}t` readout + pulse,
   updating from the SSE state stream.
5. Clicking a node opens the redesigned overlay: a telemetry strip + typed event stream
   (distinct colour/glyph per event kind), streaming live for an in-flight ticket and
   replaying for a terminal one — over the unchanged per-ticket SSE.
6. `director/assets/` no longer contains the Cytoscape/dagre bundles; `/assets/cytoscape.min.js`
   (etc.) returns 404; the page references no `/assets/*` graph lib and no CDN.
7. The operator answer console (reply/done/blocked/escalate; requeue/abandon; CSRF+loopback
   fence), the history panel, the live SSE paint, and the labeled empty-state all still work
   — the preserved-surface tests pass unchanged.
8. The gate is GREEN; `python3 -m director.dashboard` serves with **zero** build step and
   stdlib-only Python; ADR 0006 is amended to reflect the narrowed/retired relaxation.

## Open factors (triaged)
- **Graph engine — Cytoscape-restyle vs hand-roll (drop the lib): DECIDED hand-roll.** Rich
  HTML cards (the dominant visual win) are native to DOM and effectively impossible as
  Cytoscape canvas nodes; the server already provides layers/edges so client topology work
  is trivial; dropping 670KB *shrinks* the architectural footprint (R6/R8). Trade accepted:
  we own pan/zoom/collapse (reference shows ~100 lines) vs Cytoscape's free large-graph
  perf — acceptable at board scale. (Operator already chose "re-skin in our stack", incl.
  the drop-the-lib option.)
- **Token treatment — fraction bar vs count: DECIDED count.** Our telemetry is absolute;
  no honest 0..1 denominator → show `·{total}t` + pulse, omit the proportional bar.
- **Icons — lucide-react vs inline: DECIDED inline.** lucide-react is React; inline the ~10
  glyphs used (state icons, chevrons, the GitBranch header mark) as small SVG or unicode —
  no new asset/dependency (supports R8's "zero vendored bytes" goal).
- **Fonts — Inter/vendored vs system: DECIDED system stack** (`system-ui` + `ui-monospace`)
  — no font vendoring (YAGNI, avoids re-introducing an asset).
- **Collapse / frontier-focus — keep? DECIDED keep, opt-in** (consistent with the shipped
  R8 taste call; now hand-rolled show/hide instead of a Cytoscape extension).

None of these is a product-taste fork requiring escalation — each has a clear technical
best answer, and the one genuine direction fork (re-skin in-stack vs re-platform to React
vs incremental) was already settled with the operator before this spec.

## Hand-off
The ExecPlan ([execplan skill]) links this spec, builds from this design, and owns the
build order (suggested: tokens+layout scaffold in the PAGE → node-cards+edges render off
`/api/v1/board` → header done-fraction + live paint merge → overlay redesign → drop the
vendored assets + routes + amend ADR 0006 → marker/behavioral tests green → live single-eval
proof). It does not re-derive this spec. The 2026-06-26 backend plan stays `completed`; this
re-skin supersedes only the **frontend render**, not the producer/routes/SSE it sits on.
