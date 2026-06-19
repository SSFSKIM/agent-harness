---
status: completed
last_verified: 2026-06-19
owner: harness
base_commit: 09c0fc8
review_level: standard
---
# Dashboard SSE + rate-limit representation — push, don't poll; legible throttle headroom

## Goal
The dashboard is **server-pushed** instead of fixed-interval polled, and the
rate-limit headroom is **legible** instead of a raw JSON dump. Observable
definition of done: (1) `GET /api/v1/stream` holds a `text/event-stream` open and
emits a `data:`-framed `build_view` the instant the snapshot changes (verifiable
with `curl -N` — an initial event, then a new event after a status mutation), and
the page consumes it via `EventSource`, **falling back to the existing ~1s poll**
if the stream is unavailable; (2) the run header renders rate limits as a
glance-able summary (e.g. "rate: 42% used · resets ~3m" + a small bar) for a
recognizable payload, degrading to a compact summary for an odd shape and rendering
nothing for `null` — never a raw `JSON.stringify`, never a crash. `GET /` and
`GET /api/v1/state` stay byte-compatible (the page gains the stream client + the
rate-limit helper; the read JSON is unchanged).

This is the v1 **dashboard** slice (spec R4–R6). The v1 **producer** slice
(Layer-2 token accrual, R1–R3) is DONE
(`docs/exec-plans/completed/2026-06-18-layer2-token-accrual.md`); Phase B
(cross-run history, R7–R8) is a separate later plan.

## Context
- **Product-spec (owns the design — do NOT re-derive):**
  `docs/product-specs/2026-06-18-observability-polish.md` (R4–R6 + Design §B/§C +
  D-1). This plan owns build order + milestones only.
- **Lineage:** the read-only dashboard
  `docs/exec-plans/completed/2026-06-16-director-observability-dashboard.md` (D-3
  left SSE as "upgrade if 1s feels laggy"; the human elected to build it, spec
  D-1); the operator-console write surface
  `docs/exec-plans/completed/2026-06-18-director-operator-console.md` (the handler
  shape SSE extends).
- **Grounding rules:** **RELIABILITY R14** — a read-API listener fails soft: a
  handler bug degrades to a structured response, a peer disconnect (full errno
  family) is a quiet drop, nothing reaches `socketserver.handle_error`/stderr. The
  `director/` invariants (stdlib-only · loopback/fixed-route listener · pure-core /
  thin-transport, the testability lever).
- **Producer contracts this build extends (verified at base_commit 09c0fc8):**
  - `director/dashboard.py` — `build_view(status_dir, queue_dir)` (the pure view,
    reused verbatim by the stream); `PAGE` (the inline page: `fmtTokens`, `render`,
    `poll`, `setInterval(poll, 1000)` at the bottom; the run header renders
    `run.rate_limits` as `"rate " + JSON.stringify(...)` at the `fmtTokens(ct)`
    block); `_Handler` (`protocol_version = "HTTP/1.0"`; `__getattr__`→`_dispatch`;
    `_dispatch` already catches `BrokenPipe/ConnectionReset/ConnectionAborted` +
    a catch-all 500; `_ROUTES = {"/", _STATE_PATH, _ANSWER_PATH}`; `_route`;
    `_send`; `_error`); `_DashboardServer` (carries `status_dir`/`queue_dir`/`token`);
    `serve`.
  - `_STATE_PATH = "/api/v1/state"`. Tests bind port 0 and drive over `urllib`
    (`tests/test_director_dashboard.py` HTTP-smoke pattern).

## Approach (self-generated alternatives)
- **A — server-side change-detection stream over the SAME `build_view`, with a
  client `EventSource` + poll fallback** (the spec's design, D-1). New
  `GET /api/v1/stream` route; a `_stream_loop` helper (pure, injectable
  `view_fn`/`sleep`/`now`/`should_run`/`write`) emits a `data:` frame only when the
  serialized view changes, plus a periodic heartbeat; the page tries `EventSource`
  and falls back to `setInterval(poll, 1000)` if the stream never delivers.
- **B — a producer-side event bus** (orchestrator pushes changes to the dashboard).
  Rejected: the read-dashboard's whole bet is the file-backed snapshot as the single
  source of truth; an outbound channel from the orchestrator couples it to dashboard
  internals (spec Non-goals). Server-side re-read of the snapshot is decoupled.
- **C — replace the poll outright (no fallback).** Rejected: SSE can fail (older
  proxy, stream death, no `EventSource`); without a fallback the surface regresses
  to blank. The poll is kept as the degradation path (graceful).
- **Chosen: A.** Reuses the pure `build_view` (testability lever holds — the stream
  logic is unit-tested without a socket via the injectable loop), keeps the snapshot
  the single source of truth, and never regresses (poll fallback).

## Assumptions & open questions (self-interrogation)
- **Assumption:** `ThreadingHTTPServer` gives each connection its own thread
  (verified — the handler is already threaded), so a long-lived stream occupies one
  thread for its lifetime — fine for a single local operator (1–2 tabs). Its
  `daemon_threads` is True, so streams die with the process on shutdown.
- **Assumption:** SSE over HTTP/1.0 works by sending the stream headers WITHOUT
  `Content-Length` and keeping the socket open, flushing each frame; `EventSource`
  reads until close and auto-reconnects. The dedicated `_stream` path must NOT use
  `_send` (which sets `Content-Length`).
- **Assumption:** server-side change-detection by comparing the serialized
  `build_view` string is cheap enough at a ~0.5s server poll for a single operator
  (the view is small); only a *changed* view is pushed (less client re-render than
  the 1s poll), plus a heartbeat to detect a dead peer.
- **Open:** exact codex `rate_limits` shape → resolved per spec: the renderer is
  written tolerant (used-percent / remaining+limit / reset hints + compact-fallback),
  and the real shape is pinned against a live codex run in M3; the placeholder
  `{"remaining": 9}` and `null` are kept as degradation cases.
- **Open:** clean stream termination on `httpd.shutdown()` (vs. process exit) → the
  loop ends on the next write-after-disconnect or with the daemon thread on exit;
  a `should_run` predicate keeps it test-bounded. Not over-engineered (single local
  operator); recorded.
- **Open (escalate? no):** none is a taste/product fork — D-1 (build SSE) was the
  human call already settled in the spec.

## Milestones

- **M1 — SSE server route + `_stream_loop` (the logic core, headless).** Add
  `_STREAM_PATH = "/api/v1/stream"` to `_Handler._ROUTES` (`{"GET"}`) and route it
  to a new `_stream()`. Factor the push logic into a pure, injectable helper
  `_stream_loop(write, view_fn, *, sleep, now, should_run, heartbeat_s, poll_s)`:
  emit `data: <json>\n\n` only when the serialized view changes from the last sent,
  else a `: ping\n\n` heartbeat after `heartbeat_s`, sleeping `poll_s` between
  checks; any `write` raising the connection-errno family ends it (R14). `_stream()`
  sends SSE headers (`text/event-stream`, `Cache-Control: no-cache`, NO
  `Content-Length`) then runs the loop with `write = wfile.write+flush`,
  `view_fn = lambda: build_view(status_dir, queue_dir)`, real `sleep`/`now`, and an
  until-disconnect `should_run`. `_dispatch`'s existing fail-soft catch covers a
  mid-stream disconnect (R14). `GET /` and `_STATE_PATH` behavior byte-unchanged.
  At the end: the stream logic exists and is unit-tested without a socket.
  Run: `python3 -m unittest discover -s tests -p 'test_director_dashboard.py'`.
  Expect (new tests): `_stream_loop` driven with a fake `write`/`view_fn`/clock and a
  3-tick `should_run` emits an initial `data:` frame, NO frame on an unchanged tick
  until the heartbeat fires (`: ping`), and a fresh `data:` when the view changes; a
  `write` that raises `BrokenPipeError` ends the loop without propagating past the
  handler; plus an integration test (urllib opens `/api/v1/stream`, reads the initial
  `data:` event, asserts it parses to the current view, closes).

- **M2 — Client `EventSource` + poll fallback + rate-limit render (`PAGE`).**
  Extend `PAGE`'s script: a `startStream()` that, when `window.EventSource` exists,
  opens `EventSource('/api/v1/stream')`, renders each `e.data` (via the existing
  `render`), and — only if it errors *before* delivering anything — closes and calls
  the existing poll path; with no `EventSource`, it polls directly. The bottom
  `setInterval(poll, 1000); poll();` becomes the fallback `startStream()` entry (poll
  preserved verbatim as the degradation path). Add a tolerant `fmtRateLimits(rl)`
  helper and replace the run-header `"rate " + JSON.stringify(run.rate_limits)` with
  it: render "rate: NN% used" + a small bar when a used-fraction is recognizable
  (`used_percent`/`usedPercent`, or `remaining`+`limit`), append "· resets ~Xm" for a
  reset hint (`resets_in_seconds`/`reset_at`/`window_minutes`), degrade to a compact
  `key:value` summary for an odd shape, render nothing for `null`/`undefined`; never
  throw on a missing field. Values still via `textContent` (no `innerHTML`).
  At the end: the page is push-driven with a safety net and renders rate limits legibly.
  Run: the dashboard unit tests assert `PAGE` wires `EventSource('/api/v1/stream')`,
  retains the `poll` fallback, and contains `fmtRateLimits` used in the run header.
  Expect: tests green; `GET /` still 200 HTML (structure assertions hold).

- **M3 — Behavioral E2E + gate + docs.** Drive a real browser (`/playwright-cli`):
  serve the dashboard against a seeded status dir, confirm the page renders via the
  stream (not the 1s poll) and updates **on a snapshot mutation** without a reload;
  confirm the rate-limit tag renders legibly for a realistic payload (pin the real
  codex `rate_limits` shape here) and does not crash on `{"remaining": 9}` / `null`.
  Update the `docs/DIRECTOR.md` §10 line that currently says "re-polled ~1s … (no
  SSE…)" to describe the push + fallback. Capture output into the plan.
  Run: `python3 plugin/scripts/check.py` (GREEN, worktree manual gate) + the playwright drive.
  Expect: GREEN gate; the browser updates via SSE on a status change; rate limits legible.

## Progress log
- [x] (2026-06-19) plan created; base_commit 09c0fc8; review_level standard
  (arch for the transport/handler shape; reliability for the R14 long-lived-stream
  fail-soft). No new write/exec surface → review-security not triggered (SSE is
  read-only push, unlike the operator-console write fence).
- [x] (2026-06-19) **M1 done** — SSE server core. `director/dashboard.py`: `import time`;
  `_STREAM_PATH`/`_STREAM_POLL_S`(0.5)/`_STREAM_HEARTBEAT_S`(15); pure injectable
  `_stream_loop(write, view_fn, *, sleep, now, should_run, heartbeat_s, poll_s)` (emit
  `data:` only on view CHANGE, `: ping` heartbeat on no-change, return on the disconnect
  errno family — R14); `_ROUTES` + `_route` gain `_STREAM_PATH:{GET}`; `_stream()` sends
  event-stream headers (NO Content-Length) then runs the loop with `wfile.write+flush`.
  4 TDD tests (initial+on-change, heartbeat, stops-on-disconnect; integration: urllib opens
  `/api/v1/stream`, reads the initial `data:` frame = current build_view). `GET /` +
  `/api/v1/state` byte-unchanged. 37 dashboard tests green.
- [x] (2026-06-19) **M2 done** — client + rate-limit render. `PAGE`: `startStream()` prefers
  `EventSource('/api/v1/stream')`, renders each pushed view, and falls back to the preserved
  `setInterval(poll,1000)` ONLY if the stream can't deliver (no EventSource / error before
  first event); a deliver-then-drop auto-reconnects (no double-poll). Tolerant `fmtRateLimits`
  (used_percent / remaining+limit → a text gauge + %, reset hint → "resets ~Xm", odd shape →
  compact key=value, null → ""); run header now uses it instead of `JSON.stringify`. 1 test
  (PAGE wires EventSource + keeps poll fallback + uses fmtRateLimits, raw dump gone). Full gate
  GREEN (490 tests).

- [x] (2026-06-19) **M3 done** — behavioral E2E + docs. `docs/DIRECTOR.md` §10 rewritten:
  server-pushed (SSE) with poll fallback + rate-limit gauge (replacing "re-polled ~1s … no SSE").
  **Behavioral check (web → playwright), PASS:** served the dashboard against a seeded status dir
  (one ended ticket carrying `rate_limits={used_percent:42, resets_in_seconds:180}` + a live
  in-flight ticket); the browser rendered **via SSE** (initial frame through `EventSource.onmessage`)
  showing `700 tok (in 420 / out 280)` and `rate ▮▮▮▮▯▯▯▯▯▯ 42% · resets ~3m`; mutating the
  snapshot (in-flight 600→1234) **pushed** the update to `1334 tok` + in-flight row `1234 tok`
  within ~1.5s with NO reload — confirmed across 3 successive mutations. (The window-marker
  no-reload check read "cleared" only because `playwright-cli eval` is isolated per invocation —
  verified separately; the page's sole update path is `onmessage → render()`, DOM-only, no reload
  in `PAGE`.) Rate-limit shape: a real codex run wasn't available in this environment, so the
  renderer is pinned tolerant (used_percent/remaining+limit/resets + compact fallback + null→"");
  the seeded representative payload renders the gauge, and `{"remaining":9}`/`null` degrade
  without error (unit-asserted). Full gate GREEN.

## Surprises & discoveries
- 2026-06-19: `playwright-cli eval` evaluates each invocation in an isolated context — a
  `window.__probe` set in one `eval` is gone in the next, so a cross-eval "did the page reload?"
  marker reads as cleared even when the page never reloaded. The no-reload property is instead
  established by construction (SSE `onmessage → render()` is DOM-only) + the functional push test.

## Decision log
- 2026-06-19: review_level = **standard** (arch + reliability). SSE adds a long-lived
  read listener — reliability owns R14 (disconnect = quiet drop, no stderr, never a
  gate); arch owns the transport shape (pure `_stream_loop` + thin `_stream` over the
  reused `build_view`). No `hooks/`/`.harness.json`/write-surface change → no security
  persona (contrast the operator-console write fence).
- 2026-06-19: keep the ~1s poll as the FALLBACK, not delete it (spec C rejected) — SSE
  must never regress the surface to blank when the stream can't hold.
- 2026-06-19: change-detection by serialized-view comparison server-side (not an
  orchestrator event bus) — keeps the file-backed snapshot the single source of truth
  (spec Non-goals: no producer push channel).

## Feedback (from completion gate)
Four reviews (Claude personas — Codex worker unreliable, CLAUDE.md fallback). All
**SATISFIED**, zero P1s. Three P2s fixed inline (two double-flagged); three minor P2s + two
proposed rules recorded fix-forward.
- **spec-compliance (SATISFIED):** R4–R6 traced to code; scope clean (R1–R3 pre-exist, R7–R8
  absent). P2: reset-field drift (spec said `reset_at`, code does `reset_in_seconds`) → **FIXED**
  (spec §C aligned to the duration-based set; `reset_at`/absolute degrades to no-suffix, tolerated).
- **review-arch (SATISFIED):** loopback/fixed-route/pure-core invariants honored; testability
  lever held (`_stream_loop` unit-tested without a socket). P2 (also flagged by reliability):
  `should_run=lambda:True` had no shutdown exit → **FIXED** (a `_DashboardServer.serving` Event,
  cleared by a `shutdown()` override, backs `should_run` so an in-process shutdown ends quiet
  streams ≤ poll_s). Proposed rule → tech-debt: SSE framing convention (no Content-Length, `\n\n`,
  Cache-Control) unwritten.
- **review-reliability (SATISFIED):** R14 holds end-to-end (full errno family caught per write,
  nothing reaches stderr; read-only; tolerant build_view). P2 #1: deliver-then-permanent-death
  froze stale with no hint → **FIXED** (onerror-after-delivered shows "stream reconnecting…").
  P2 #2: shutdown gap (same as arch) → FIXED. Proposed rule → tech-debt: a long-lived read stream
  must force a bounded heartbeat so a silently-dead peer is detected (code honors it; unwritten).
- **review-code-quality (SATISFIED):** clean decomposition (pure loop / thin shim / liveness flag
  / client helpers), no duplication, comments load-bearing. Two trivial P2s **FIXED** inline
  (compact-fallback prefix aligned `"rate: "`→`"rate "`; an explanatory comment on the onmessage
  malformed-frame catch). One P2 → tech-debt: `fmtRateLimits` has no *executable* test (the
  inline-page JS can't be Python-unit-tested without a JS runtime) — covered by PAGE-presence
  asserts + the M3 playwright render; the inline-page testability ceiling is pre-existing.

## Outcomes & retrospective
**Shipped:** the dashboard is **server-pushed** and rate limits are **legible**. New
`GET /api/v1/stream` holds a `text/event-stream` open and pushes a `data:`-framed `build_view`
the instant the snapshot changes (server-side change-detect over the same pure `build_view`),
via a pure injectable `_stream_loop` (emit-on-change + heartbeat + R14 quiet-drop) and a thin
`_stream()` shim bounded on a `serving` liveness flag; the page consumes it with `EventSource`
and **falls back to the ~1s poll** if the stream can't hold (never blank). `fmtRateLimits`
renders a glance-able gauge + "resets ~Xm", tolerant of an odd/`null` payload (no raw JSON dump).
**Goal met:** behaviorally proven in-browser — the page rendered via SSE and **pushed** a
snapshot mutation (700→1334 tok) without reload, with the rate gauge legible; `GET /` +
`/api/v1/state` byte-compatible. Gate GREEN (491 tests).
**Retrospective:**
- The read-dashboard's testability lever paid off again: pulling the push logic into a pure
  `_stream_loop` (injectable write/view/clock/should_run) meant the change-detect + heartbeat +
  disconnect behavior was unit-tested without a socket — only a ~14-line `_stream` shim is
  socket-bound. The same trick the producer slice used for `build_view`.
- Two reviewers independently flagged the `should_run`-shutdown gap — a clean "feedback twice →
  promote" signal — so the liveness flag was worth fixing inline (and it tidied test thread
  hygiene: `shutdown()` now ends lingering stream threads promptly). Both proposed rules
  (streaming heartbeat-liveness; SSE framing convention) are recorded for promotion.
- The honest gap: the client JS (`fmtRateLimits`/`startStream`) stays untestable from Python —
  the single-HTML-string page is the architectural ceiling. The playwright E2E is the only
  executable coverage of the render; recorded as tech-debt, consistent with the existing pattern.
