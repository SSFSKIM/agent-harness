---
status: accepted
last_verified: 2026-06-26
owner: harness
type: adr
tags: [observability, dashboard, architecture, invariant, vendoring]
description: The observability dashboard may vendor a single offline, checked-in JS asset set (a graph library) served from a fixed local route — a scoped relaxation of the dashboard's "single self-contained HTML, no external asset" grain. The Python stdlib-only invariant (ARCHITECTURE invariant 1) and offline operation both stay in force.
---
# Observability dashboard may vendor an offline, checked-in JS asset

## Decision

The Director observability dashboard (`director/dashboard.py`) **may serve a small set
of vendored, checked-in JavaScript assets** (a graph-rendering library) from a **fixed
local route** (`/assets/<name>`, the `_ASSETS` allowlist), read from `director/assets/`.
This is scoped to the **observability surface only**.

Two properties are **non-negotiable and preserved**:

1. **Offline.** The assets are checked into the repo and served from the local file —
   **never a CDN, never a network fetch at render time.** The dashboard remains usable
   air-gapped.
2. **Python stdlib-only (ARCHITECTURE invariant 1) is untouched.** That invariant scopes
   **Python third-party imports** under `director/` (no `pyproject.toml` /
   `requirements.txt`). A served `.js` file is not a Python import — `director/` still has
   zero third-party *Python* dependencies, no package manager, no build step.

What this **relaxes** is narrower: the dashboard's own self-imposed grain, documented in
its docstring as *"no framework, no bundler, no external asset — one self-contained HTML
string."* That string-purity grain becomes **"one page + a fixed set of local vendored
assets."** The asset route is a **constant `{route → filename}` map**, so the served
filename is never request-derived — zero traversal surface (ARCHITECTURE invariant 3
holds: fixed-route, read-only, no request-derived filesystem path).

**Vendored set** (pinned, provenance for re-vendoring):
- `cytoscape.min.js` — Cytoscape.js 3.30.4 (graph core: data-driven node styling, tap
  events, pan/zoom, incremental updates).
- `dagre.min.js` — dagre 0.8.5 (layered-DAG layout engine; the `cytoscape-dagre` peer).
- `cytoscape-dagre.js` — cytoscape-dagre 2.5.0 (the Cytoscape↔dagre layout adapter).

`cytoscape-expand-collapse` was **considered and dropped**: it collapses *compound*
(parent/child nesting) nodes, not DAG-successor subtrees — the wrong tool for "collapse a
completed subtree." DAG subtree collapse is hand-rolled (a descendant-hide on the node's
`successors()`), needing no extra library. The vendor set is therefore the **minimum**
that delivers a crossing-minimized layered layout.

## Why

- **The view is intrinsically a graph.** The project dependency-graph view
  ([project-dependency-graph-view spec](../product-specs/2026-06-26-project-dependency-graph-view.md))
  renders the whole board as a layered DAG with live painting, a node-anchored session
  overlay, pan/zoom, and subtree collapse on a 100+-node graph. A hand-rolled vanilla-SVG
  layout *can* do the ranking (the server already computes `layer = wave`), but **crossing
  minimization** (dagre's value) is what keeps a real board readable — that is a solved,
  well-tested problem not worth re-implementing by hand.
- **The relaxation is genuinely scoped and low-blast-radius.** It touches only a read-only,
  loopback, never-LAN-exposed instrument (invariant 3). It adds no Python dependency, no
  build pipeline, no CDN trust, no online requirement. The dashboard is explicitly *not*
  on the run's critical path (RELIABILITY: visibility never gates a run), so the surface
  that bears a vendored asset is the safest one in the system to bear it.
- **The human chose richness over the single-file grain, knowingly.** At design time the
  fork was put explicitly (hand-rolled vanilla SVG vs. vendor a library); the human chose
  to vendor. This ADR records that scoped choice so the relaxation is **explicit, not
  silent drift** ("Not in the repo = does not exist").

## Consequences

- **`ARCHITECTURE.md` invariant 1 gains a one-sentence scope note** pointing here: the
  stdlib-only rule is Python-scoped; the dashboard may serve a fixed set of offline,
  checked-in JS assets under `director/assets/` (this ADR).
- **Implemented by**
  [project-dependency-graph-view ExecPlan](../exec-plans/completed/2026-06-26-project-dependency-graph-view.md)
  M2: `director/assets/` (the three pinned bundles), the fixed `_ASSETS` route + `_asset`
  handler, and the `/graph` page that loads them locally. A dashboard test asserts the
  allowlist serves and any non-key/traversal-shaped asset path is a 404.
- **Re-vendoring is a manual, pinned step** (like [[worker-runtime-sync-is-manual-port]]):
  the versions above are the provenance; a bump is a deliberate re-download + re-commit,
  not an automatic dependency resolve. No `package.json`, no lockfile.
- **Scope fence.** This permits vendoring for the **observability dashboard** only. It is
  **not** a general license to add JS/Python dependencies elsewhere under `director/`; any
  other dependency remains a design change to justify (invariant 1).
- **Reversible.** If the vendored layout ever becomes a liability, the server already owns
  the meaningful computation (`build_board_view`'s `layer`), so a fallback to a hand-rolled
  preset SVG layout is a renderer swap, not a data-model change.
