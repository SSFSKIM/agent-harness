---
status: active
last_verified: 2026-06-18
owner: harness
base_commit: 82449c23fee34e9795834881f7e482492f4bb16e
review_level: standard
---
# Director operator console — build

## Goal
A human can answer a Director run from a browser and be pinged when one parks —
without attaching to the session. Concretely, observable:
1. `python3 -m director.dashboard` serves (still `127.0.0.1`) a page that, for
   each pending Director-queue request, shows a kind-appropriate **action
   control**; submitting it `POST`s `/api/v1/answer`, which writes the answer via
   the canonical `director_min` writer so the blocked worker's `wait_for_answer`
   unblocks — demonstrated by reproducing the LIN-22 lights-out loop with the
   `turnReview` answered **from the browser** instead of `answer_turn` by hand.
2. `POST /api/v1/answer` is fenced: a request missing the per-server CSRF token or
   carrying a foreign `Origin` → `403`; an already-answered request → `409`; a
   malformed body → `400`; the server keeps serving after each.
3. `python3 -m director.notify --webhook <url>` fires exactly one HTTP `POST` per
   new human-bound pending request (`{request_id, kind, ticket_id, summary,
   created_at}`), deduped by `request_id`, fail-soft on a dead URL.
4. `GET /` and `GET /api/v1/state` are byte-unchanged; orchestrator / `queue` /
   `status` / `run.py` / `decider.py` are untouched; `python3
   plugin/scripts/check.py` is GREEN.

## Context
- **Product-spec (owns the design — do NOT re-derive):**
  `docs/product-specs/2026-06-18-director-operator-console.md` (R1–R8, D-1..D-7).
  This plan owns execution order + build choices only.
- **Lineage:** the read-only dashboard
  `docs/exec-plans/completed/2026-06-16-director-observability-dashboard.md`
  (this extends `director/dashboard.py`); the lights-out model
  `docs/memory/adr/0003-lights-out-director.md` (this is its human-reachability
  half); the manual loop this productizes is the LIN-22 live test (Monitor →
  `director_min.answer_turn`).
- **Producer contracts this build consumes (verified at base_commit):**
  - `director/director_min.py` — the canonical answer writers:
    `answer(request_id, decision=…|answers=…, base=)`,
    `answer_turn(request_id, disposition, base=)`,
    `answer_merge_review(request_id, disposition, base=)`,
    `requeue_merge(review, *, note, base=…) -> {requeued, attempt, …}`.
  - `director/queue/__init__.py` — `read_pending(base)` (unanswered requests),
    `read_answer(request_id, base) -> dict|None` (the idempotency pre-check),
    `write_answer` (atomic temp+`os.replace`; reached only via `director_min`),
    `APPROVAL_DECISIONS = (accept, decline, acceptForSession, cancel)`.
  - `director/decider.py:disposition_from_answer` — the disposition contract a
    `turnReview` answer must satisfy (`kind ∈ terminal|reply|escalate`; an empty
    `reply` is invalid). Mirror its validation client-side so we never write an
    answer the decider will reject as `escalate`.
  - `director/watch.py:new_pending(pending, seen, kinds) -> list` — the pure
    once-per-`request_id` dedup + kind filter the notifier reuses.
  - `director/dashboard.py` — `build_view`, `PAGE`, `_Handler` (`__getattr__`
    funnels every `do_<VERB>` → `_dispatch` → `_route`), `_DashboardServer`
    (carries `status_dir`/`queue_dir`), `serve`.
  - Request kinds (from `worker/approval.py` + `decider.py` + `merger.py`):
    human-answerable = `turnReview`, `commandApproval`, `fileChange`,
    `userInput`, `elicitation`, `mergeReview`; **not** answerable = `mergeRequest`
    (merger worklist), `runReport` (informational).

## Approach (self-generated alternatives)
- **A — extend `dashboard.py` for the write path + a separate `director/notify.py`
  for the webhook** (the spec's design). POST route reuses the existing
  `_route`/`_dispatch` funnel; notifier is its own tail process reusing
  `watch.new_pending`.
- **B — fold the notifier into the dashboard server** (the long-lived server also
  tails + webhooks). Rejected: notification would then depend on a browser
  polling the page, and it couples network egress into the read server (spec D-4).
- **C — add `--webhook` to `director.watch`** instead of a new module. Rejected
  per spec D-4: keep egress isolated from watch's Monitor-stdout emitter; share
  only the pure `new_pending`.
- **Chosen: A.** Matches the spec; smallest blast radius (read paths untouched);
  egress isolated; each piece independently testable.
- *Route shape:* single `POST /api/v1/answer` kind-dispatched (spec D-1), not
  per-kind routes — one validator seam mirroring `_summary_for`'s kind switch.

## Assumptions & open questions (self-interrogation)
- **Assumption:** the `director_min` writer shapes are exactly what the worker /
  merger consume (verified by reading both sides) — so routing the POST body
  through them cannot drift from the queue contract. If wrong, answers would be
  written that no consumer accepts (caught by the live M4 check).
- **Assumption:** browser same-origin policy + a per-server token embedded in the
  served HTML is sufficient CSRF defense for a `127.0.0.1` single-operator surface
  (a foreign page can't read the token; its `Origin` won't match). No auth system
  (spec D-3 / non-goal).
- **Assumption:** `requeue_merge` needs the full pending `review` dict; the console
  obtains it by matching `request_id` in `read_pending` (the pending row carries
  `payload`/`workspace_path`/`ticket_id`) — no new queue read shape.
- **Open:** webhook payload richness → resolved per spec (minimal
  `{request_id, kind, ticket_id, summary, created_at}` v1; deep-link deferred).
- **Open:** config knob for the webhook URL → resolved NO (spec D-5: URL is
  secret-bearing → `$DIRECTOR_WEBHOOK_URL`/`--webhook`, kept in `.env`, never
  `.harness.json`).
- **Open (escalate? no):** none of the above is a taste/product fork — the one
  product fork (notification channel) was settled in the spec (D-6, webhook).

## Milestones

- **M1 — Answer route + fencing (the logic core).** Add `POST /api/v1/answer` to
  `director/dashboard.py`: parse `{request_id, kind, …}`, look the request up in
  `read_pending` (→ `404` unknown / `409` already-answered via `read_answer` /
  `400` kind-mismatch), validate the kind-specific payload against the downstream
  writer's contract (disposition `kind`/non-empty-`reply`; decision ∈
  `APPROVAL_DECISIONS`; answers is a dict; mergeReview action ∈
  `requeue|abandon|human`), then dispatch to the matching `director_min` writer.
  Fence it: `_DashboardServer` mints `token = secrets.token_urlsafe(32)`; a POST
  requires header `X-Director-Token == server.token` AND an `Origin`/`Host`
  resolving to `127.0.0.1`/`localhost` → else `403`. Keep `_route` GET behavior
  byte-identical; POST on an undefined route → `404`, other verbs unchanged. All
  handler/writer errors fail-soft (structured `4xx`/`5xx`, server survives).
  At the end: the write path + fence exist and are unit-tested headlessly.
  Run: `python3 -m unittest discover -s tests -p 'test_director_dashboard.py'`.
  Expect: new tests pass — a POST per answerable kind writes the right
  `answers/<rid>.json` shape (asserted by reading it back / by spying the
  `director_min` call); `mergeRequest`/unknown kind → refused; missing/foreign
  token → `403`; already-answered → `409`; malformed body → `400`.

- **M2 — Per-kind action UI.** Extend `build_view` so each `pending` entry also
  carries the minimal payload its control needs (e.g. `commandApproval` → the
  command; `turnReview` → `final_message`+`outcome`), staying tolerant. Extend
  `PAGE`: render a kind-appropriate control per pending item (approve/decline
  buttons; a disposition selector + reply/escalate textarea for `turnReview`;
  requeue-note / abandon for `mergeReview`), each issuing the M1 POST with the
  `X-Director-Token` header (token injected into the page); on success the item
  clears on the next ~1s poll. Every value still written via `textContent` (no
  `innerHTML`) — producer text never parsed as markup.
  At the end: the page drives the write path end to end in a browser.
  Run: the dashboard unit tests assert `PAGE` contains the token injection + the
  per-kind control scaffolding; the live browser drive is the M4 behavioral check.
  Expect: tests green; `GET /` body still 200 HTML (structure assertions hold).

- **M3 — Park notifier (`director/notify.py`).** New module: pure
  `webhook_payload(req) -> {request_id, kind, ticket_id, summary, created_at}`
  (summary via the same per-kind logic as the dashboard — extract the shared
  `_summary_for` or a thin equivalent); `make_webhook_notifier(url,
  http_post=…) -> notify(event) -> bool`; a tail loop reusing
  `watch.new_pending(pending, seen, kinds=_HUMAN_KINDS)` that fires the notifier
  once per new human-bound `request_id`, with bounded-retry fail-soft (leave a
  failed `request_id` unseen to retry next tick, up to N attempts, then mark seen
  + log "abandoned"; never raise out of the loop). CLI:
  `python3 -m director.notify --webhook <url> [--queue-dir …] [--poll …] [--once]`;
  URL falls back to `$DIRECTOR_WEBHOOK_URL`.
  At the end: an independent park-notify channel exists.
  Run: `python3 -m unittest discover -s tests -p 'test_director_notify.py'`.
  Expect: `webhook_payload` shape asserted; a new human-bound request → exactly
  one POST (captured via a fake `http_post`); a still-pending request on the next
  tick does not re-fire; a `http_post` that raises → bounded retry, the loop
  survives (no exception escapes), and a non-human kind (`mergeRequest`) is never
  POSTed.

- **M4 — Docs + behavioral E2E + gate.** Add a `docs/DIRECTOR.md` section: how to
  run the console + notifier, what it answers, the `$DIRECTOR_WEBHOOK_URL` env.
  Behavioral check (runnable surface → required): stand up the dashboard against a
  seeded queue with a pending `turnReview` (the LIN-22-style fixture, mock worker
  ok), drive `GET /` with `/playwright-cli`, submit the disposition from the page,
  and confirm `answers/<rid>.json` appears + a blocked `wait_for_answer` returns;
  separately run `director.notify --once` against a local capture URL and confirm
  one POST. Capture the output into the plan.
  At the end: the feature is demonstrated end-to-end and documented.
  Run: `python3 plugin/scripts/check.py` (GREEN) + the playwright drive.
  Expect: GREEN gate; the browser submit unblocks the worker; the webhook fires.

## Progress log
- [ ] (2026-06-18) plan created; base_commit 82449c2; review_level standard.

## Surprises & discoveries

## Decision log
- 2026-06-18: review_level = **standard** (review-arch + review-reliability) **plus
  review-security on the write-fencing** — by the skill's letter review-security is
  reserved for `hooks/`/`.harness.json`/lints (none touched here), but a new
  localhost **write** surface that mutates the queue workers consume makes the
  CSRF/Origin fence the headline risk, so it gets a security persona regardless.
- 2026-06-18: single `POST /api/v1/answer` kind-dispatched (spec D-1); answers via
  `director_min` writers only (spec D-2); separate `notify.py` (spec D-4); webhook
  URL from env, not config (spec D-5). All inherited from the spec, recorded here
  for the build.
- 2026-06-18: build order M1(route+fence) → M2(UI) → M3(notify) → M4(docs+E2E) —
  logic core first (headless-testable), UI second (consumes the route), notifier is
  independent (any order, placed third), E2E + docs last.

## Feedback (from completion gate)

## Outcomes & retrospective
