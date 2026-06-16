---
status: active
last_verified: 2026-06-16
owner: harness
base_commit: b3a69d3
review_level: standard
---
# Director observability dashboard (live read-only web view)

## Goal
A human can run `python3 -m director.dashboard` and, in a browser at
`http://127.0.0.1:<port>/`, watch a live Director run without entering the
Director session: the page polls `GET /api/v1/state` ~1s and re-renders the run
header (pass #, started_at, terminal badge, **and the now-shipped cost/usage —
cumulative tokens, runtime seconds, rate-limit**), in-flight tickets
(ticket·phase·attempt/wave), stuck tickets (← blocker ids), the recent-outcomes
tail (✓/✗ + **per-ticket tokens/session**), and the pending Director queue
(kind·ticket·summary). Definition of done, observable: with a seeded status dir
the page shows all five blocks and the telemetry; undefined route → `404`,
wrong method on a defined route → `405`, both as a `{"error":{code,message}}`
JSON envelope; no existing runtime module changes; `python3
plugin/scripts/check.py` is GREEN.

## Context
- **Product-spec (owns the design — do not re-derive):**
  `docs/product-specs/2026-06-16-director-observability-dashboard.md`. R1-R6,
  D-1..D-6, and the **상태/재배치 note's "구체 계약 (이 빌드)" paragraph** are the
  authoritative contract. That paragraph supersedes the body's older
  `/api/snapshot` notation with the Symphony-§13.7 alignment: `GET
  /api/v1/state`, `404`/`405`, `{"error":{code,message}}` envelope,
  `counts`+`generated_at` blocks, and the pass-through telemetry fields.
- **Why now:** this renderer was deliberately re-sequenced *behind*
  `docs/exec-plans/completed/2026-06-16-worker-telemetry-capture.md` because a
  renderer is downstream of producer state. That slice shipped (commit `26e374a`,
  live-pinned to codex-cli 0.139.0), so `status.json`'s `run` now carries
  `codex_totals{input,output,total,seconds_running}` + `rate_limits`, and each
  `recent` row carries `tokens{input,output,total}|null` + `session_id` +
  `last_message`. The renderer's whole reason to exist now is to surface that.
- **Producer contract this plan consumes (verified at `b3a69d3`):**
  - `director/status.py:248` `read_status(base=None) -> dict|None` — tolerant:
    missing/torn file → `None`, never raises. Snapshot schema in its docstring
    (status.py:17): `run` (with `codex_totals`+`rate_limits`), `in_flight`,
    `recent` (with `tokens`/`session_id`/`last_message`), `stuck`, `updated_at`.
  - `director/queue/__init__.py:192` `read_pending(base=None) -> list[dict]` —
    unanswered requests = the Director's work surface. Request shape
    `{request_id, ticket_id, session_id, kind, payload, workspace_path,
    created_at}`. Payload-by-kind (verified): `commandApproval`→`{command(list),
    cwd, reason}`; `fileChange`→`{changes, reason}`;
    `userInput`/`elicitation`→`{questions}`; `turnReview`→`{final_message,...}`
    (decider.py:114); `mergeRequest`→`{pr, branch, self_description, guidance,
    attempt}`; `mergeReview`→`{pr, branch, result, reason, disposition,
    attempt}`.
  - Both readers are pure (no mutation), take a `base=` override, and default to
    `.claude/harness/director-status` / `.claude/harness/director-queue`.
- **Grain (verified):** the repo is **stdlib-only** — no `pyproject.toml`/
  `requirements.txt`, zero third-party imports under `director/`, tests are
  `python3 -m unittest discover`. There is **no existing HTTP server** in the
  repo; this is the first stdlib listener. New surface MUST stay stdlib-only
  (`http.server`, `urllib`, `json`, `threading`) — core-belief "boring tech /
  internalize dependencies" (no flask/fastapi/textual).
- Sibling CLI pattern to mirror: `director.status`/`director.watch`/
  `director.merger` are all `python3 -m director.<mod>` + `--status-dir`/
  `--queue-dir` args.

## Approach (self-generated alternatives)
- **A — server-side HTML render.** Handler builds the HTML with the live data
  each request; no client JS. Tradeoff: the testable logic is entangled with
  string templating; tests must scrape HTML; no clean data contract; harder to
  evolve to SSE later. Rejected.
- **B — JSON endpoint + thin client render (chosen).** A pure
  `build_view(status_dir, queue_dir) -> dict` is the entire logic surface and is
  unit-tested **without a socket** (assert the data structure). The HTTP layer is
  a ~2-route shim over it; the page is one inline HTML string whose vanilla JS
  polls `/api/v1/state` and re-renders the DOM. Tradeoff: a little client JS, but
  it is framework-free and inline (offline-OK). This is the spec's D-6 and gives
  the cleanest testability lever and the cleanest future SSE upgrade (reuse
  `build_view`). **Chosen.**
- **C — reuse `director.watch` event stream as the live channel (SSE now).**
  Tradeoff: long-lived stream + subprocess lifecycle, more moving parts, and the
  snapshot is already a single source of truth so 1s re-read is trivial and
  bulletproof. Deferred to a later additive upgrade (spec Open Q / D-3). Rejected
  for v1.

Chosen: **B** — pure `build_view` core + thin `http.server` shim + inline polling
page. Mirrors the spec's D-3 (polling), D-5 (127.0.0.1, read-only), D-6 (JSON +
client render).

## Assumptions & open questions (self-interrogation)
- Assumption: the persisted `run.codex_totals.seconds_running` (frozen at the
  producer's last flush) is "live enough" for an ambient view — the producer
  flushes on every transition, so it advances whenever anything happens. What
  breaks if wrong: between transitions the runtime clock looks frozen. Acceptable
  for v1 (the spec scopes live mid-turn accrual to a deferred Layer-2); the page
  also shows `updated_at`/`generated_at` so staleness is visible.
- Assumption: `build_view` passing `run`/`in_flight`/`stuck`/`recent` through
  unchanged is sufficient to surface telemetry — confirmed by the producer schema
  (the fields ride inside those objects). The renderer computes nothing; it only
  shapes `pending` + `counts` + `generated_at`. What breaks if wrong: a missing
  field renders blank — tolerable (client guards with `?.`/defaults).
- Assumption: a `ThreadingHTTPServer` on `127.0.0.1` is an acceptable new surface
  because it is read-only, fixed-route (no request-derived file paths → zero
  traversal), and localhost-bound (D-5/R3). The genuine new risk is the listener
  itself; that is the reliability/arch review's "new I/O boundary" lens.
- Open: `error.code` value for the envelope → resolved autonomously as the **HTTP
  status int** (`404`/`405`) with a human `message`; Symphony only fixes the
  `{code,message}` shape, not the code's type. Recorded in Decision log.
- Open: pending `summary` truncation length → resolved as **140 chars**
  (glance-able, not a full payload dump). Decision log.
- Open: default port → **8787** (spec D-5 names it), `--port` overrides; bind
  failure surfaces immediately (no retry loop), per spec error-handling.

## Milestones

- **M1 — `build_view` pure data core (the whole logic surface, no socket).**
  Scope: add `director/dashboard.py` with `build_view(status_dir=None,
  queue_dir=None, *, now=_utcnow) -> dict` and a private `_summarize_request` /
  `_summary_for(kind, payload)`. `build_view` reads `read_status(base=status_dir)`
  (tolerant → `{}` when None) and `read_pending(base=queue_dir)`, and returns
  `{run, in_flight, stuck, recent, pending, counts, generated_at}` where: `run` is
  the snapshot's `run` (None when no run — passes telemetry through untouched);
  `in_flight`/`stuck`/`recent` pass through (telemetry rides inside them);
  `pending` is each request reduced to `{request_id, ticket_id, kind, summary}`;
  `counts` is `{in_flight, stuck, recent, pending}` lengths; `generated_at` is
  `now()`. `_summary_for` is **tolerant** (kind-keyed best-effort, missing keys →
  `""`, truncated to 140): `turnReview`→`final_message`;
  `mergeReview`/`mergeRequest`→`result`+`reason` else `pr`/`branch`;
  `commandApproval`→joined `command` else `reason`; `fileChange`→`reason`;
  `userInput`/`elicitation`→`questions` text; else→`kind`. At the end:
  `director/dashboard.py` exists with a fully-tested pure core, no HTTP yet.
  Run: `python3 -m unittest discover -s tests -p "test_director_dashboard.py" -v`.
  Expect: new `tests/test_director_dashboard.py` cases pass — (a) a real
  `StatusWriter` snapshot with `codex_totals`/`recent[].tokens` + an
  `append_request`'d pending item yields the view dict per schema with telemetry
  present in the pass-through and `summary` filled per kind; (b) no-run / torn
  status.json → `run is None`, `counts.in_flight == 0`, still a valid dict (R3);
  (c) `counts` equals the array lengths; (d) a malformed/missing payload → empty
  `summary`, never raises (R6 tolerance).

- **M2 — HTTP shim + `serve` + `main` (Symphony-aligned transport).** Scope: add
  to `director/dashboard.py` a `BaseHTTPRequestHandler` subclass with exactly two
  defined routes — `GET /` → `200 text/html` (the M3 page string; a placeholder
  constant until M3) and `GET /api/v1/state` → `200 application/json` =
  `json.dumps(build_view(...))`; an **undefined path → `404`** and a **defined
  path with a non-GET method → `405`** (override `do_GET`/`do_POST` or dispatch on
  `command`), each emitting `{"error":{"code":<status int>,"message":<str>}}` as
  `application/json`. The handler reads `status_dir`/`queue_dir` from **server
  attributes set at construction** (never derived from the request → zero path
  traversal); `log_message` is silenced. `serve(port=8787, status_dir=None,
  queue_dir=None) -> ThreadingHTTPServer` binds `127.0.0.1` only; a bind failure
  propagates immediately (no retry). `main(argv=None)` parses
  `--port`/`--status-dir`/`--queue-dir` and serves forever
  (`python3 -m director.dashboard`). At the end: the server runs and answers all
  four route/method cases. Run: same test file. Expect: an HTTP smoke test that
  binds **port 0**, then via `urllib.request` asserts `GET /api/v1/state` → 200 +
  parseable JSON matching `build_view`, `GET /` → 200 `text/html`, `GET /nope` →
  404 + error envelope, and `POST /api/v1/state` → 405 + error envelope; the
  server stays up across all of them (tolerance).

- **M3 — inline page renders structure + the cost/usage payoff.** Scope: replace
  the M2 placeholder with one `PAGE` HTML string constant — minimal dark
  terminal-ish CSS + ~40 lines of vanilla JS that `setInterval(fetch
  '/api/v1/state', ~1000ms)` and re-renders the DOM (no framework, no external
  asset, no bundler — all inline, offline-OK). Render: a header line (run pass #,
  started_at, a terminal badge when `run.stopped_reason`, **and the telemetry:
  `codex_totals` input/output/total tokens, `seconds_running`, and a compact
  `rate_limits` readout**); in-flight (ticket·phase·attempt/wave); stuck (ticket ←
  blocker ids); recent (✓ for done / ✗ otherwise + **per-row `tokens.total` and
  short `session_id`**); pending Q (kind·ticket·summary); and a "last updated"
  from `generated_at`. `run === null` → "no active run" (pending still shown). At
  the end: the page renders all five blocks plus telemetry. Run: same test file +
  a live check. Expect: a unit test asserts the served `GET /` body contains the
  poller (`/api/v1/state`, `setInterval`) and the telemetry section markers
  (e.g. `codex_totals`/`tokens`/`rate`), proving the page wires to the contract
  without scraping layout.

- **M4 — docs, gate, live proof.** Scope: add a `docs/DIRECTOR.md` section
  "Watching a run live (the observability dashboard)" — the human runs `python3
  -m director.dashboard` in a side window/browser to watch a run read-only; acting
  on pending items still goes through the Director (D-2/D-5). At the end: docs
  describe the surface; the diff touches only `director/dashboard.py`,
  `tests/test_director_dashboard.py`, `docs/DIRECTOR.md` (R5 — zero changes to
  `status.py`/`watch.py`/`orchestrator.py`/`queue`). Run: `python3
  plugin/scripts/check.py` → GREEN. Live (the real acceptance): seed a temp
  status dir with a `StatusWriter` carrying `codex_totals` + a `recent` row with
  `tokens`, plus an `append_request` pending item; launch `python3 -m
  director.dashboard --port <p> --status-dir <d> --queue-dir <q>`; open it with
  the `/playwright-cli` skill and confirm the five blocks + tokens/runtime/rate
  render and the page updates on a re-flush. Expect: a screenshot/observation
  showing the live cost/usage — the payoff of sequencing the renderer after the
  producer.

## Progress log
- [ ] (2026-06-16) Plan authored against reconciled spec (base_commit b3a69d3).
      Next: M1 build_view + tests.

## Surprises & discoveries

## Decision log
- 2026-06-16: Build from the spec's "구체 계약" note paragraph (the authoritative
  Symphony-§13.7 contract), not the body's superseded `/api/snapshot` — the spec
  reconcile commit (b3a69d3) made this explicit.
- 2026-06-16: `error.code` = HTTP status int (404/405); Symphony fixes only the
  `{code,message}` shape. `summary` truncated to 140 chars. Port default 8787.
- 2026-06-16: Approach B (JSON endpoint + thin client render) over server-side
  HTML — pure `build_view` is unit-testable without a socket (D-6 testability).
- 2026-06-16: review_level=standard — the new risk is a localhost read-only
  listener (new I/O boundary): arch + reliability. Security surface is fenced by
  design (127.0.0.1, fixed routes, no request-derived paths, read-only) and not
  in the security-persona trigger set (no hooks/.harness.json/.claude-lints/
  .harnessignore touched).

## Feedback (from completion gate)

## Outcomes & retrospective
