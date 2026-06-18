---
status: stable
last_verified: 2026-06-18
owner: harness
---
# Director operator console — actionable dashboard + park notifications

The human-reachability complement to the lights-out Director
([ADR 0003](../memory/adr/0003-lights-out-director.md)). Turns the existing
**read-only** dashboard ([director-observability-dashboard](2026-06-16-director-observability-dashboard.md))
into an **actionable** surface and adds the missing "reach an absent human"
channel. This is the deferred slice that doc's D-2 + Open Question named
("actionable 대시보드 후속 슬라이스 … write surface fencing 설계 필요").

## Problem

Two gaps block the lights-out operating model from being usable when the human
is genuinely away:

1. **No way to act except inside the session.** The dashboard lets a human
   *watch* a run but not *answer* it. The only way to resolve a worker's
   escalation (a pending `turnReview`, `commandApproval`, `fileChange`,
   `userInput`, `elicitation`, or `mergeReview` in the Director queue) is to
   type in the live Director session — or call `director_min` by hand, which is
   literally what we did to drive the lights-out live test (LIN-22). A blocked
   worker (`wait_for_answer`) sits parked until someone attaches to the session.
2. **Nothing reaches the human on park.** The orchestration-visibility spec made
   "push/notification to the human" an explicit non-goal ("Director surfaces only
   within session", line 212). In the **lights-out** model the human is *absent
   but async-reachable* — so when a run parks awaiting-human, something must
   reach them off-session; today nothing does.

Observable today: start a real watched run, let a worker post a `turnReview`,
walk away — the run blocks indefinitely and no signal leaves the machine. The
console closes both gaps: answer-from-browser + notify-on-park.

## Requirements

- **R1 — Answer a pending request from the browser.** A `POST` to the dashboard
  resolves a named pending queue request by writing its answer through the
  canonical `director_min` writer for its kind, so the blocked worker's
  `wait_for_answer` unblocks and the orchestrator proceeds. *Verifiable:* with a
  pending `turnReview` on a queue dir, a `POST` answer writes
  `answers/<request_id>.json` in the `answer_turn` shape and `read_pending` no
  longer lists it.
- **R2 — Per-kind action contracts.** Each human-answerable kind maps to its
  writer with the right shape: `turnReview` → a disposition
  (`{kind: terminal|reply|escalate, …}`, via `answer_turn`); `commandApproval` /
  `fileChange` → a decision (`accept|decline|acceptForSession|cancel`, via
  `answer`); `userInput` / `elicitation` → an `answers` payload (via `answer`);
  `mergeReview` → a resolution (`requeue`+note via `requeue_merge`, or
  `abandon`/`human` via `answer_merge_review`). `mergeRequest` is **not**
  human-answerable (it is the serialized merger's worklist) and is read-only on
  the console. *Verifiable:* a unit test per kind asserts the correct
  `director_min` function is invoked with a schema-valid payload.
- **R3 — Console UI with per-item controls.** The dashboard's "pending" list
  gains action controls appropriate to each item's kind (e.g. accept/decline
  buttons for an approval; a disposition selector + reply/escalate text for a
  `turnReview`); submitting issues the R1 `POST` and the item clears on the next
  poll. *Verifiable:* with a seeded pending queue, the page renders a control per
  pending item and a submit resolves it.
- **R4 — Park notification via webhook.** An independent tail of the queue
  fires **one** HTTP `POST` to a configured webhook URL when a *new*
  human-bound pending request appears, carrying
  `{request_id, kind, ticket_id, summary, created_at}`. *Verifiable:* point the
  notifier at a capture URL, create a pending `turnReview`, observe exactly one
  POST with those fields; a second poll of the same still-pending request does
  not re-fire (dedup by `request_id`).
- **R5 — Write-surface fencing.** The server binds `127.0.0.1` only (unchanged),
  and every state-changing `POST` requires BOTH (a) an `Origin`/`Host` header
  naming localhost (cross-origin rejected) AND (b) a per-server CSRF token minted
  at startup and embedded in the served page; a `POST` lacking the matching token
  is `403`. *Verifiable:* a `POST` without the token, or with a foreign `Origin`,
  is refused `403` and writes no answer.
- **R6 — Act durably, never double-answer.** The answer file is written
  atomically (`write_answer` = temp+`os.replace`, already) and the console
  reports success only after it is durable; answering a request that already has
  an answer is refused (`409`) rather than clobbering a possibly-consumed answer
  ([[queue-act-before-consume-ordering]]). *Verifiable:* a second `POST` for an
  already-answered `request_id` returns `409` and leaves the first answer intact.
- **R7 — Read-only safety preserved; everything fail-soft.** `GET /api/v1/state` is
  byte-unchanged and `GET /`'s read rendering is preserved (the page gains the R3
  controls + the R5 token `<meta>`, but watching is unaffected); a malformed `POST` → `400`,
  an unknown/answered request → `404`/`409`, and any handler or webhook error is
  fail-soft (structured response, the server/notifier survives) — never a gate on
  a run, never a crash, mirroring the read dashboard's "never a gate" posture
  (RELIABILITY R14). *Verifiable:* a `POST` with a garbage body returns `400` and
  the server keeps serving; a dead webhook URL does not crash the notifier.
- **R8 — Additive; no orchestrator/queue/status changes.** Reuse `director_min`
  + `queue` + `status` unchanged. The change set is: extend `director/dashboard.py`,
  add `director/notify.py`, tests, and a `docs/DIRECTOR.md` section. The
  orchestrator, `run.py`, `decider.py`, `queue/`, and `status.py` are untouched.

## Design

### Component map

| File | Change | Responsibility |
|---|---|---|
| `director/dashboard.py` | extend | add the `POST` answer route, the CSRF token, and the per-item action UI; enrich `build_view` pending entries with the payload the controls need |
| `director/notify.py` | **new** | the park notifier: tail the queue for new human-bound pending requests and `POST` each once to a webhook (reuses `watch.new_pending` for dedup/filter) |
| `tests/test_director_dashboard.py` | extend | `POST` answer per kind, token/Origin fencing, idempotency, malformed-body |
| `tests/test_director_notify.py` | **new** | payload shape, dedup-once, fail-soft on a dead URL |
| `docs/DIRECTOR.md` | section | how to run the console + notifier; what it answers; the webhook env/flag |

### Answer path (`director/dashboard.py`)

- **Route:** one new `POST /api/v1/answer`. Body:
  `{"request_id": str, "kind": str, …kind-specific}`. A single route that
  dispatches on `kind` keeps the surface minimal and mirrors `_summary_for`'s
  kind switch.
- **Dispatch → `director_min`** (the canonical writers — never re-implement
  `write_answer`):
  - `turnReview` → `answer_turn(request_id, disposition, base=queue_dir)` where
    `disposition` is the validated `{kind, …}` from the body. Reuses
    `decider.disposition_from_answer`'s contract (empty `reply` → invalid).
  - `commandApproval` / `fileChange` → `answer(request_id, decision, base=…)`
    with `decision ∈ APPROVAL_DECISIONS`.
  - `userInput` / `elicitation` → `answer(request_id, answers=<dict>, base=…)`.
  - `mergeReview` → `requeue_merge(review, note=…, base=…)` for a guided retry,
    else `answer_merge_review(request_id, {action: abandon|human, note}, base=…)`.
    (The console must read the full pending request to pass `requeue_merge` the
    `review` dict; it looks it up from `read_pending` by `request_id`.)
  - `mergeRequest` (and any non-human kind) → `409`/`400`: not answerable here.
- **Pre-checks (R6):** look up the request in `read_pending(queue_dir)`; if
  absent → it is either unknown or already answered → `404`/`409`
  (distinguish via `read_answer`). If `kind` in the body disagrees with the
  queued request's kind → `400`.
- **Validation:** reject a disposition/decision/answers payload that the
  downstream writer would reject (e.g. a `terminal` with no `outcome.status`, a
  decision outside the enum, an empty `reply`) → `400` with the reason, *before*
  writing — never queue a malformed answer.

### Write-surface fencing (`director/dashboard.py`, R5)

- `_DashboardServer` mints `token = secrets.token_urlsafe(32)` at construction
  and stores it (alongside `status_dir`/`queue_dir`).
- `PAGE` embeds the token (a `<meta>` or JS const); the page's `POST` fetch
  sends it as header `X-Director-Token`. Same-origin policy means a *foreign*
  page in the user's browser cannot read the served HTML (so cannot learn the
  token) — the classic localhost-CSRF defense.
- `_route` for a `POST`: require `X-Director-Token == server.token` AND an
  `Origin`/`Host` that resolves to `127.0.0.1`/`localhost`; otherwise `403`.
  GET routes are unaffected (no token needed — read-only).

### Park notifier (`director/notify.py`, R4)

- A thin tail loop: `python3 -m director.notify --webhook <url> [--queue-dir …]
  [--poll …]`. The URL also resolves from `$DIRECTOR_WEBHOOK_URL` when `--webhook`
  is omitted (so a Slack/Discord webhook — itself a secret-bearing URL — stays in
  `.env`, never committed; mirrors `load_api_key`). No config-block change (the
  URL is deployment-secret, not policy).
- Reuses `watch.new_pending(pending, seen, kinds=_HUMAN_KINDS)` for the
  exactly-once-per-`request_id` dedup and the human-bound filter
  (`_HUMAN_KINDS = turnReview, commandApproval, fileChange, userInput,
  elicitation, mergeReview` — `mergeRequest`/`runReport` excluded). Keeping the
  notifier separate from `watch.py` isolates the *network egress* concern from
  watch's Monitor-stdout emitter (a cleaner trust boundary), while sharing the
  pure dedup function (no duplicated logic).
- **Notifier boundary:** `make_webhook_notifier(url, http_post=urllib_post) ->
  notify(event) -> bool`; `webhook_payload(req) -> dict` is pure (unit-tested).
  A future email/OS channel is a second `make_*_notifier` behind the same
  `notify(event)` boundary — not built now (YAGNI).
- **Fail-soft + bounded retry (R7):** a non-2xx / raised POST is logged once and
  the `request_id` is *left unseen* so the next tick retries — bounded by a
  per-request attempt cap (after N attempts, mark seen + log "abandoned") so a
  permanently-dead URL never hammers. The poller never raises out of the loop.

### Integration points & edge cases

- **Act-before-consume** ([[queue-act-before-consume-ordering]]): the answer is
  the durable side-effect; the console writes it (atomic) and only then returns
  `200`. There is nothing to "consume" on the console side — the worker consumes
  via `wait_for_answer` — so ordering reduces to "write atomically, report after".
- **Concurrent answer (console + live session).** Both write
  `answers/<rid>.json`; `os.replace` is atomic so the file is never torn, and the
  R6 pre-check (`read_answer is None`) makes the console refuse if the session
  already answered. A race where both pass the pre-check then both write is
  benign (idempotent: same request, last writer wins an equivalent answer) and
  vanishingly unlikely for a single human operator; not further locked (YAGNI).
- **Torn queue read** at the dashboard boundary already degrades to "no pending"
  (`_read_pending`); the notifier inherits the same tolerance.
- **No run / empty queue:** pending list empty → no controls, no notifications.

## Non-goals (scope fence — YAGNI)

- **Orchestrator "poll-now / refresh" trigger.** Symphony's `POST /api/v1/refresh`
  queues an immediate board poll+reconcile; replicating it needs an *inbound
  control channel into the orchestrator* (a control file the daemon checks each
  tick), which the read dashboard deliberately avoided and which couples the
  console to orchestrator internals. The dashboard view already auto-refreshes
  (~1s), and the daemon polls on its own cadence. Deferred — a future slice tied
  to the daemon's control surface.
- **Pause / cancel a worker from the console.** The operator-stop lever already
  exists: move the ticket out of `In Progress` and active-run reconciliation
  cancels the worker (`2026-06-16-active-run-reconciliation.md`). Not duplicated.
- **Non-webhook notification channels** (email/SMTP, desktop/OS, browser
  Notification API). Webhook is the v1 "reach-anywhere" channel; the notifier
  boundary admits others later.
- **SSE / server-push, multi-run aggregation, cross-run history.** Unchanged from
  the read-dashboard non-goals (still poll, current-run only).
- **Auth / users / non-localhost bind.** Single local operator; `127.0.0.1` +
  per-server token, no login.
- **The daemon's park→queue handoff.** *How* a lights-out daemon turns a "park"
  decision into a pending human-bound request (vs. an `escalate` disposition that
  only comments the board) is the Daemonized-Claude-Code track's responsibility.
  This console answers whatever human-bound requests are pending; it does not
  define the daemon's parking mechanism.

## Acceptance criteria

- `POST /api/v1/answer` with a pending `turnReview` disposition writes
  `answers/<rid>.json` in the `answer_turn` shape; `read_pending` drops it;
  (live, optional) a blocked orchestrator turn proceeds — i.e. the LIN-22
  live-test loop, but the `turnReview` answered **from the browser** instead of
  `answer_turn` by hand.
- A unit test per answerable kind asserts the correct `director_min` writer +
  schema-valid payload; `mergeRequest`/unknown kind → refused.
- `POST` without the token or with a foreign `Origin` → `403`, no answer written;
  answering an already-answered request → `409`; malformed body → `400`; server
  keeps serving after each.
- `python3 -m director.notify --webhook <capture>` POSTs exactly once per new
  human-bound `request_id` with `{request_id, kind, ticket_id, summary,
  created_at}`; a dead URL is fail-soft (bounded retry, poller survives).
- `GET /api/v1/state` byte-unchanged, `GET /` read rendering preserved (+ controls/token);
  `python3 plugin/scripts/check.py`
  GREEN.

## Decision log

- **D-1 — single `POST /api/v1/answer`, kind-dispatched (not per-kind routes).**
  Mirrors `_summary_for`'s existing kind switch; one route, one validator seam.
  (autonomous.)
- **D-2 — answers go through `director_min` writers, never a re-implemented
  `write_answer`.** The shapes (`disposition` / `decision` / `answers` /
  `merge_review_disposition`) are owned there and consumed by the worker; a
  second writer would drift. (autonomous.)
- **D-3 — fencing = `127.0.0.1` + per-server CSRF token + Origin/Host check.**
  Standard localhost-CSRF defense; no auth system for a single local operator.
  This is the "write surface fencing" the read-dashboard's Open Question deferred.
  (autonomous; resolves the deferred concern.)
- **D-4 — notifier is a separate `director/notify.py` reusing `watch.new_pending`,
  not a `--webhook` flag on `director.watch`.** Isolates network *egress* from
  watch's Monitor-stdout emitter (trust boundary) while sharing the pure dedup.
  (autonomous.)
- **D-5 — webhook URL from `--webhook` / `$DIRECTOR_WEBHOOK_URL`, not a committed
  config knob.** The URL is a secret (Slack/Discord webhooks embed a token);
  keep it in env/`.env` like `LINEAR_API_KEY`, never in `.harness.json`.
  (autonomous.)
- **D-6 — notification channel = webhook (v1).** Chosen over local desktop/browser
  (doesn't reach an away human) and email/SMTP (heavier, more secrets). Most
  general "reach-anywhere", stdlib `urllib` only. (**human, 2026-06-18.**)
- **D-7 — orchestrator poll-now/refresh is a non-goal.** Needs an inbound control
  channel the read-dashboard avoided; the view already auto-refreshes. (autonomous.)

## Open questions

- **Daemon park → pending-request handoff.** When the lights-out daemon decides
  to park (vs. answer), the cleanest console integration is for the park to leave
  or post a *pending human-bound request* so it surfaces + notifies. The exact
  mechanism belongs to the daemon track; flagged here so the two slices converge.
- **Webhook payload richness.** v1 sends `{request_id, kind, ticket_id, summary,
  created_at}`; whether to include a deep link / fuller context is deferred until
  real use shows what a phone notification needs.
