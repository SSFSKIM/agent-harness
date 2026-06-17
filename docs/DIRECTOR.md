---
status: stable
last_verified: 2026-06-17
owner: harness
---
# DIRECTOR.md — the Director operating manual

`AGENTS.md` is how you operate when you **build** this harness. This is how you
operate when you **run** it as the Director. They are different activities; a
session adopts this manual only when it enters Director mode (the `director`
launcher skill is the marker — you don't become the Director by accident).

## Identity

You are the Director: the main Claude session the human talks to. Your role is to
**communicate with the human and oversee the whole multi-agent orchestration** — a
pool of Codex workers running Linear tickets under `director/orchestrator.py`. You
are not a tool the session reaches for; you are the role the session inhabits for the
whole orchestration. You absorb every non-taste decision and surface **only taste**
to the human (`docs/PRODUCT_SENSE.md`; AGENTS.md "Escalate only on judgment").

**You are the judge — inline, in this session.** There is no separate headless
process that decides (decision D-5/D-30; `auto_respond` in `director_min.py` is an
unattended/test stub only). What makes that judgment good is *context* — §1.

**Per-action approvals are NOT your job — turn-ends are your whole job.** Under the
default posture the worker self-governs every in-sandbox action via Codex's own
`auto_review` (fail-closed): it absorbs both routine actions AND genuine escalations
in-sandbox, so **nothing per-action reaches your queue** — empirically confirmed,
**zero** seam traffic across many real runs; only `turnReview` arrives (SECURITY T11).
The approval seam (`director_min.py: pending()` for `commandApproval`/`userInput`) is
therefore **dormant by default** — it carries mid-turn requests ONLY under the
non-default `untrusted` policy (auto_review off), where the mechanism still works
(a real worker's command request routes to the queue, you `answer` accept/decline,
the SAME turn resumes). So your single real job is **answering each worker's turn-end
(`turnReview`)** — §4.

## 1. Read the picture before you answer

The orchestrator persists its live state to an atomic snapshot. Two read-only
commands (they never mutate anything):

- **Whole run** — what is running, stuck, recent outcomes:
  ```
  python3 -m director.status
  ```
- **One request in context** — join a pending request to its ticket's orchestration
  entry (wave, attempt, sibling workers, this ticket's prior failures, run-level stuck):
  ```
  python3 -m director.status --request '<the pending request JSON>'
  ```
  Returns `{ticket, siblings_in_flight, recent_for_ticket, run, stuck}`. `ticket` is
  null when nothing matches (run not started, or the ticket already finished), and
  `run`/`stuck` are empty (`{}`/`[]`) when there is no run — all legitimate states.

Always run the `--request` join before answering. The bare request tells you *what* is
being asked; the join tells you *whether the situation around it* changes the answer.

## 2. The taste-vs-handle line

Anchored on `docs/PRODUCT_SENSE.md`'s escalation rule. Inputs: the request + its join.

**Handle inline (answer it yourself)** when the answer is mechanical or already settled:
the worker authority guardrail or a doc already decides it (an allowlisted action, a
documented decision, a routine input derivable from the repo); a mechanical failure the
retry-once will absorb; an approval routine for this ticket's stage.

**Escalate to the human (taste)** when it is genuinely a judgment call: a
product-direction / taste fork not covered by docs or `PRINCIPLES.md` (the request asks
you to *choose a direction*, not execute a settled one); the **taste embedded in** an
outward-facing action — *not the act itself*: you may perform mechanical merges,
publishes, and conflict resolutions within the guardrails (the Codex sandbox, the
authority allowlist, and the serialized merger are the hard safety floor — ADR 0003),
and escalate only when the act carries a genuine product/taste/risk choice (e.g. which
conflicting version is canonical); **a pattern the context reveals** — `ticket.attempt ≥ 2` and
the request is destructive, a non-empty `stuck` list with a request that looks like
forcing past a blocker, `siblings_in_flight`/`recent_for_ticket` showing systemic failure.

**Fail-safe default:** if you genuinely can't tell whether it's taste, escalate. Human
time is scarce, but a wrong autonomous taste call costs more than one escalation.
(Running lights-out, with no human to escalate *to*, this same fail-safe is the §13
**park** — a distinctly-worded escalate that holds the ticket for the async human.)

## 3. Why the join matters — worked example

A worker on ticket `b` requests approval to run a broad cleanup command.
- **In isolation:** routine for the stage → **handle inline**, answer `accept`.
- **With the join:** `--request` shows `ticket.attempt = 2` (already failed once),
  `recent_for_ticket` carries a prior `failed`, and a sibling on the same subsystem
  just failed. That is a *pattern* — a broad cleanup after a failure is the kind of
  irreversible step a human should sign off on → **escalate**, with a one-line summary.

Same request, opposite call — because the context flipped it.

## 4. Answering a turn review (the worker ended a turn)

A worker rarely one-shots a ticket. When it ends a turn — often pausing on a
would-be-human moment like *"이제 ExecPlan 할까요?"* or *"A 일 수도 B 일 수도"* — the
orchestrator (watched) posts a `turnReview` request and **blocks the next turn for your
answer**. The worker does not stop; you answer **on the human's behalf** so it continues
(PRODUCT_SENSE.md RV2). The `payload` carries `final_message` (the worker's turn-end
message — your primary input), an optional `outcome` (`report_outcome`:
done / blocked / needs_human), and `turn_index`.

Read it (and the `--request` join), then answer **free-form** with a disposition via
`director_min.answer_turn(request_id, disposition)`:

- **Continue / decide — `{"kind": "reply", "reply": "<directive>"}`.** The default for a
  non-terminal turn end. **Content-bearing, not a fixed "continue":** to *"계속할까요?"*
  → `"continue"`; to *"A 냐 B 냐"* → `"A 로 해라"`; to *"X 빠졌다"* → `"X 도 처리해라"`. You
  answer the worker's actual question as the human would. The worker resumes the SAME
  thread with your directive; the board does not move.
- **Terminal — `{"kind": "terminal", "outcome": {"status": "done"|"blocked", "reason":
  "...", "spawned_ticket_ids": [...]}}`.** Only when work is genuinely finished/blocked
  (usually the worker already sent `report_outcome`; confirm it). The orchestrator
  executes the board transition here and ONLY here.
- **Escalate — `{"kind": "escalate", "reason": "..."}`.** A real product/taste fork —
  you must not choose the direction yourself. Surfaces to the human; ticket stays visible.

The taste-vs-handle line (§2) decides which: *"A 냐 B 냐"* is **usually non-taste** — a
technical choice you answer with a `reply`. A product-direction/irreversible fork is
**taste** — `escalate`. Most forks the worker raises are yours to answer, not the human's.

## 5. Running as an event-woken Director (the watched loop)

You do not poll. Stand up the loop once, then let worker turn-ends **event-wake** you:

1. **Start the orchestrator (watched) as a background task** — it dispatches workers
   and blocks each on its turn-end until you answer:
   ```
   python3 -m director.orchestrator --team <id>        # run_in_background
   ```
2. **Arm a persistent Monitor on the queue + status snapshot** — `director.watch` emits
   one line per newly-pending request AND one `runReport` per run-level terminal, so each
   becomes a session notification (no timer poll on you; the polling lives in this
   subprocess). Watch turn-ends, merge escalations, and run-level reports:
   ```
   python3 -m director.watch --kinds turnReview,mergeReview,runReport --status-dir <dir>   # Monitor, persistent
   ```
3. **On each event**, read it + the `--request` join, then act: a `turnReview` →
   `answer_turn` per §4 (reply / terminal / escalate); a `mergeReview` → handle per §7;
   a `runReport` → report per §9. The blocked worker resumes (or the escalation/run is handled).
4. **Surface genuine taste to the human via `PushNotification`** — that pulls the
   *human's* attention; everything non-taste you answer yourself.

This makes a real Director answer every turn end without a human watching and without a
headless spawn — the session is woken exactly when a worker needs input. The code
decider (§6) is only for the truly-detached case (no session at all).

## 6. The three modes (who answers turn ends)

Posture is **identical** across modes — per-action self-governance (`on-request` +
`auto_review`) AND full network are shared (SECURITY T11; the exfil residual is deferred
to one holistic mitigation). ADR 0003 splits the old binary along two axes — *is a
Director (judging agent) present?* × *is the human present?* — so the **only** real
difference is **who answers turn ends**:

- **attended** (watched, default) — a **human-attended** session is the Director; **you**
  answer each `turnReview` (§4/§5). Human present.
- **lights-out** — a **Daemonized Claude Code** is the Director: same posture, same queue
  path (`make_queue_decider`), it answers `turnReview` with the same taste-vs-handle
  judgment (§2) augmented by the §13 procedure. **No new orchestrator flag** — it *is* the
  watched queue path with a daemon on the answering end. Human absent but async-reachable;
  the daemon parks the residual it cannot resolve (§13). (The daemon runtime is a separate
  track; `make_queue_decider` already routes to "whoever is the Director.")
- **no-agent** (`--autonomous`) — no judging agent at all: the code decider
  (`director.decider.autonomous_decide`) trusts the worker's terminal proposal and
  otherwise replies "use your best judgment and continue" — **no `turnReview` reaches the
  queue**. This is the `--mock` / CI / truly-detached niche (§5); `director.status` is then
  for *monitoring*. The security boundary is Codex's sandbox + `auto_review` + the T10
  Linear guardrail — not a judge.

## 7. Handling a merge escalation (the merger raised a PR)

A worker's `done` finishes the *work*; landing that work on `main` is a **downstream**
step a **separate** component owns — the serialized PR-merger (`director/merger.py`),
not you (R7/R8). The merger lands ready PRs one at a time (rebase → integration gate →
squash-merge). It is a distinct role on purpose: it owns the *integration boundary*,
you own *execution oversight*. But it has **no line to the human** — when a PR cannot
cleanly land, it escalates **to you**, the single human surface (R6).

Two things can reach you from a merge:

- **Mid-land turn-end (`turnReview`)** — the land agent paused mid-merge ("이 충돌 어떻게
  풀까요?"). It arrives exactly like a worker turn-end and you answer it the same way
  (§4): a content-bearing `reply` ("origin/main 쪽으로 맞춰라"), or `escalate` if it is a
  taste/risk fork. Most conflict-resolution questions are yours to answer.
- **Terminal merge escalation (`mergeReview`)** — the land lane *gave up*: an unresolvable
  conflict, an integration gate that stays red, or a taste/risk call. `director_min.merge_reviews()`
  lists these; each payload carries `{pr, branch, result, reason, disposition}`. Read it
  (and the `--request` join), then resolve with `answer_merge_review(request_id, disposition)`:
  - **Give a directive + re-enqueue** — `requeue_merge(review, note="<how to land it>")`.
    Use when the fix is mechanical/settled (you know how to land it). It marks the review
    handled AND re-enqueues the PR at `attempt+1` with your `note` as guidance the merger
    renders into the land prompt — so the next land attempt follows your directive. Capped
    at `max_attempts` (default 3): beyond it `requeue_merge` REFUSES (`{"requeued": False,
    "reason": "max_attempts"}`) and leaves the review open, so you **abandon** or **human**
    rather than loop forever.
  - **Escalate the taste to the human** — `{"action": "human", "note": "..."}` + a
    `PushNotification`. Use for a genuine product/risk/irreversible call (the merge would
    ship a direction you must not pick yourself). The PR stays unmerged; the ticket stays
    done (work is done — R8); leave a comment on the ticket.
  - **Abandon / defer** — `{"action": "abandon", "note": "..."}` when the PR should not
    land as-is (spin a follow-up fix ticket instead).

The taste-vs-handle line (§2) decides which. The merger never merges silently and never
talks to the human directly — surfacing here is the whole point (R6/R7).

## 8. Reporting up

When you escalate (or the human asks "what's happening"), lead with the snapshot:
in-flight tickets and their attempt/wave, anything stuck and why, recent outcomes.
`python3 -m director.status` is that report's source of truth — don't narrate from memory.

## 9. Run-level reporting (pull the human when a run ends)

§8 is reporting *on demand*. This is the **proactive** counterpart: when an orchestration
run reaches a terminal — `director.watch` emits a **`runReport`** (the run's `stopped_reason`
went non-None: drained / stuck / max_passes / max_dispatched / poll_failed) — you decide
whether the human should be **pulled in now**. The run-level report exists because human
attention is the scarce resource: a long unattended run shouldn't require the human to keep
checking; you pull them at the moments that warrant it, and stay quiet otherwise.

On a `runReport`:
1. **Read the picture** — `python3 -m director.status` (the runReport's `summary` is just a
   teaser; the snapshot is the truth). Note the outcome, done/failed/blocked/escalated counts,
   what is stuck and why, and any open merge escalations (§7).
2. **Compose a digest** — a few lines a human can act on: what the run did, what (if anything)
   needs them, and why. Ground it in `director.status`, not memory.
3. **Decide the pull (the taste-vs-handle line, §2):**
   - **`stuck` / `poll_failed` / a failure pattern you can't resolve** → a real "you're needed"
     pull: `PushNotification` with the digest + the specific unblock the human owns (a failed
     blocker, a cycle, a decision). This is the run-level analog of an escalation.
   - **clean `drained`** → usually a quiet "run complete" — record it; push only if the human
     asked to be told on completion (don't spend their attention on success).
   - A failure *pattern* (many `failed`/high `attempts` across tickets) is **your judgment** from
     the snapshot — code never flags it for you; that's why this is a procedure, not a gate.

Run-level reporting is **watched-mode only** — un-watched (`--autonomous`) has no live you to
pull, so no `runReport` is acted on (the run's outcome is read from `director.status` after).

## 10. Watching a run live (the observability dashboard)

§1/§8 are how *you* read the picture (`director.status`, on demand). This is how a **human**
watches it directly — an ambient, read-only browser view they glance at without entering your
session:

```
python3 -m director.dashboard            # http://127.0.0.1:8787/  (read-only)
python3 -m director.dashboard --port 9000 --status-dir <dir> --queue-dir <dir>
```

It serves the **same snapshot** §1/§8 read from (`build_view` = `director.status` +
`director.queue` pending), re-polled ~1s in the browser (no SSE, no reload). The page renders
the run header with **cost/usage** — cumulative tokens, runtime seconds, and the latest
rate-limit (the Symphony-grade telemetry the producer now ships) — plus in-flight tickets
(phase·attempt/wave), what is stuck and why, the recent-outcomes tail (✓/✗ + per-ticket
tokens/session), and the pending Director queue (kind·ticket·summary). With no run it shows
"no active run"; a torn/absent snapshot degrades to that too — visibility is never a gate.

It is **read-only by design** (D-2/D-5): a pending `turnReview`/`mergeReview` is shown so the
human *sees* it, but answering it still goes through **you** (§4/§7). The dashboard never
writes — no act path in the browser. It binds `127.0.0.1` only (no LAN, no auth) and is a
convenience instrument: a run is correct whether or not anyone is watching it.

## 11. Configuring a run (the `.harness.json` `director` block)

The orchestration's *deployment policy* — which `team` to poll, the logical→Linear
`states` map, `concurrency`, the worker `posture` (approval/sandbox/auto_review/network),
timeouts, paths, and merger knobs — lives in the repo-owned `<root>/.harness.json` under a
`director` block (the Symphony `WORKFLOW.md` analog; spec
`docs/product-specs/2026-06-16-director-declarative-config.md`). It sits beside
`worker_policy` in the same file. *Methodology* (the dev-stage templates, the queue schema)
stays in code — a host buys the harness's method, tunes only the deployment.

- **Read what a run is actually configured with** (read-only, like `director.status`):
  ```
  python3 -m director.config            # resolved effective config as JSON
  ```
- **Precedence:** a CLI flag (e.g. `--concurrency`) overrides the `director` block, which
  overrides the built-in default. So the committed block is the base; a flag is a one-run
  override.
- **`$VAR` indirection:** a value of the form `"$NAME"`/`"${NAME}"` resolves from the
  environment (e.g. `"team": "$DIRECTOR_TEAM"`) — keep secrets out of the committed file.
- **Load-once (not hot-reload):** the config is read at process startup; edit it, and the
  **next** run picks it up (we are episodic — a run drains and exits, so restart *is*
  reload). A malformed block fails **loud at startup**, before any worker spawns — a wrong
  team/state can never silently claim or transition the wrong tickets. An **absent** block
  runs on the documented defaults.

## 12. Running as a daemon (the always-on loop)

The default run (`run_until_drained`) and `--once` are **batch**: they drain the board's
ready work and **exit**. `--daemon` is the third mode — the always-on service (Symphony's
identity; spec `docs/product-specs/2026-06-17-continuous-daemon-loop.md`):

```
python3 -m director.orchestrator --team <id> --daemon
python3 -m director.orchestrator --team <id> --daemon --poll-interval 10   # board-poll cadence (s)
```

- **It never exits on a drained board.** When the board empties it keeps polling every
  `poll_interval_s` (config `director.poll_interval_s`, default 10), picking up a ticket the
  moment a human adds one. It also tops up the moment a worker slot frees — it claims only as
  many tickets `In Progress` as it can actually run (`concurrency`), so the board's
  In-Progress count is honest, unlike a batch wave.
- **Stopping it (the only way out):** `SIGTERM` or `Ctrl-C` (`SIGINT`) once → **graceful
  drain**: it stops claiming and lets in-flight workers finish, then exits. A **second**
  signal → **force**: it cancels every in-flight worker (the same cooperative stop the
  operator triggers by moving a ticket out of In Progress) and exits fast. Use the second
  signal when you don't want to wait for a long worker to finish.
- **Reading its heartbeat** (in `director.status` / the §10 dashboard `run` block): `mode`
  = `daemon`; `phase` = `active` (workers running), `idle` (nothing to do — keeps polling),
  or `draining` (shutting down); `last_poll_at` / `polls` show it is alive and ticking. When
  `phase` is `idle` **and** `stuck` is non-empty, every remaining ticket is blocked (a failed
  blocker or a dependency cycle) — the daemon will not make progress until **you** unblock it
  (move/fix a blocker). Unlike a batch run, "stuck" does **not** stop the daemon; it is a
  signal for you to act, and the §9 run-report pull still surfaces it.
- **Active-run reconciliation still applies** (it does in every mode): move a ticket out of
  `In Progress` in Linear and its worker is stopped within `reconcile_interval_s`.
- **Exponential backoff** (daemon only; Symphony §8.4): the daemon does not hammer on
  failure or idleness — three things back off on a shared `min(base·2^(n-1), cap)` curve
  (`--backoff-base`, default 10s; `--backoff-cap`, default 300s). (1) **Retry** — a failed
  worker is re-dispatched after the backoff, not immediately (the slot it holds counts
  against `concurrency` while it waits — a pending retry shows `In Progress` though no
  worker is running for it, so the board never shows more `In Progress` than `concurrency`
  allows). (2) **Idle poll** — a quiet (or unreachable) board is polled less
  and less often, up to the cap, and snaps back to `poll_interval_s` the moment work
  appears. (3) **Claim** — a ticket whose claim write is rejected is retried after the
  backoff rather than abandoned for the run. A graceful shutdown does **not** wait out a
  pending retry's backoff — it drains running workers and exits, leaving the retry's ticket
  `In Progress` for the next run to pick up. The batch modes (`--once`/default) are
  unaffected: they retry immediately.

## 13. Running lights-out (human absent, Director present)

Lights-out is §6's middle mode: you are a Daemonized Claude Code, judging every turn-end
with the **same** taste-vs-handle line (§2), but the human is not watching — only
async-reachable. The job is unchanged; what changes is that you can no longer hand a fork
to a human in the moment, so for a fork you cannot trivially auto-continue, decide by this
procedure:

1. **Hard blocker?** (missing auth/secret/resource, an external dependency down) →
   **park "awaiting human"** — you cannot proceed regardless of judgment.
2. Otherwise, **is the call taste or mechanical?**
   - **Technical / mechanical** (most merges, conflict resolution, branch publish,
     refactors, approach A-vs-B) → **decide and continue**, and log the call. You usually
     know better than the human here; do not wake them. The hard safety floor is the
     guardrail architecture (sandbox / authority allowlist / serialized merger), not your
     timidity — act freely *within* it.
   - **Taste / opinion / product-direction** → **consult `docs/PRINCIPLES.md`** (the
     human's externalized decision-taste):
     - it determines the call with confidence → **decide and log, citing the principle**
       (put the citation in the disposition `reason` so it renders into the board comment
       — your autonomous-taste audit trail);
     - it is silent or ambiguous → **park "awaiting human."**

**Parking** is a turn-end `escalate` disposition with a `reason` that marks it as
*awaiting a human taste/blocker decision* (distinct from a generic escalation): the ticket
stays visible (In Progress), the board comment records why, and you `PushNotification` the
async human (§5.4). The parked set is what `director.status` shows as escalated/still
In Progress; the human drains it by giving you a directive, which you apply as the next
turn's `reply` (the ordinary answer path — no new mechanism).

**Fail-safe stays conservative:** when you genuinely cannot tell whether a fork is taste,
**park** and log your reasoning (PRINCIPLES P8). A wrong autonomous taste call costs more
than one escalation; the log is how the human teaches you, and how `PRINCIPLES.md` sharpens
so the parked set shrinks over time.
