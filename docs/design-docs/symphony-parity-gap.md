---
status: stable
last_verified: 2026-06-26
owner: harness
type: design-doc
tags: [symphony, orchestrator, parity, gap-analysis]
description: A holistic gap analysis comparing this harness's orchestrator against the original OpenAI Symphony spec — as of 2026-06-26 the substrate gaps are all shipped; the only remaining deltas are deliberate philosophy forks (no WORKFLOW.md file, no Liquid templating, no hot-reload) plus the un-built lights-out runtime.
---
# Symphony parity — gap analysis

A holistic comparison of our `director/` orchestrator against the original
OpenAI Symphony (vendored at `docs/symphony-original/` — `SPEC.md` §1–18 + the
SSH appendix, `WORKFLOW.md`, `README.md`). Written 2026-06-16 from a full read of
both sides: the Symphony spec end-to-end and our orchestration core
(`orchestrator.py`, `run.py`, `board/linear.py`, `decider.py`, `merger.py`,
`taxonomy.py`, `worker/app_server.py`, `worker/autonomy.py`, `director_min.py`)
plus `DIRECTOR.md`/`ARCHITECTURE.md`. This is the reference the Symphony-parity
track cites; it is observational (what differs and why), not a roadmap — the
chosen next move lives in its own spec (see "Derived work" below).

> **Status refresh (2026-06-26).** The "gaps, ranked" below were the 2026-06-16
> snapshot; **all five plus every lesser adapter/workspace gap have since shipped**
> (each marked CLOSED inline with its landing execplan). What is left versus
> Symphony is no longer a *capability* deficit — it is three **deliberate
> philosophy forks** (no `WORKFLOW.md` file, no Liquid prompt templating, no
> config hot-reload) and exactly **one un-built capability: the lights-out
> *runtime*** (the Daemonized Claude Code; its contracts shipped, the runtime did
> not). Read the "Remaining deltas" section for the current truth; the ranked
> gaps are retained as the historical record of how we got here.
>
> **Strategic stance (2026-06-17, unchanged).** This doc's original "neither bet is
> ahead" framing is **narrowed by
> [ADR 0002 — graduated autonomy](../adr/0002-graduated-autonomy.md)**: we
> deliberately take Symphony's autonomy bet on the *middle* (Director →
> exception-handler) and *worker-autonomy* axes, while **keeping** our
> board-ownership + serialized merger (correctness wins, not human-in-loop
> artifacts). Read this doc as the observational comparison; read ADR 0002 for the
> chosen stance and [ADR 0003](../adr/0003-lights-out-director.md) for the
> lights-out completion.

## The headline: a different bet, not a worse one

Symphony and our Director solve the same problem with opposite philosophies.

- **Symphony is an unattended daemon.** It runs forever, polls Linear on a fixed
  cadence, and delegates *all* judgment to the agent (`approval_policy: never`;
  user-input-required = hard failure). The human only curates the board. Its
  center of gravity is `WORKFLOW.md` — a repo-owned file (YAML front matter +
  Liquid prompt) holding *all* policy, hot-reloaded without restart. The agent
  walks the ticket lifecycle (Todo → In Progress → Human Review → Merging → Done)
  and performs every tracker write + the PR land itself.
- **Our Director is supervised, episodic, and code-configured.** A live Claude
  session is the taste-judge; worker turn-ends route to it through a queue and it
  answers free-form. Policy lives in `.harness.json` + CLI flags, resolved once at
  startup. The *orchestrator* (not the agent) owns board writes; a *separate
  serialized merger* lands PRs.

Neither is strictly ahead. The bets diverge on autonomy (Symphony: full, human
only seeds the board; us: supervised by default, with a designed lights-out path
where a Director agent holds taste via `PRINCIPLES.md`) and on where policy lives
(Symphony: declarative `WORKFLOW.md`, hot-reloaded; us: declarative
`.harness.json`, startup-resolved).

## Where we match or exceed Symphony

| Symphony capability | Our implementation | State |
|---|---|---|
| Continuous poll→dispatch→reconcile daemon, DAG eligibility, bounded concurrency, claim-before-act (§7–8, §16) | `orchestrator.py`: `run_forever` (continuous tick) + `run_once`/`run_until_drained` (batch), `eligible_tickets`, `_dispatch_wave`/`_RunState` | ✓ |
| Active-run reconciliation + stall handling + terminal-state cancel (§8.5, §14.4) | `_reconcile_in_flight` (wall-clock-anchored, ARCH inv. 7) | ✓ |
| Exponential backoff + retry/idle/claim cadence (§8.4) | `_backoff_s` helper (daemon path; batch keeps immediate retry) | ✓ |
| Codex app-server client: handshake, turn stream, server-request seam, dynamic tools (§10) | `worker/app_server.py` | ✓ strong |
| Token/rate-limit accounting — absolute totals, ignore deltas (§13.5) | `app_server.extract_usage`/`extract_rate_limits`; `status` `codex_totals` | ✓ |
| Runtime snapshot + HTTP `GET /api/v1/state` + per-ticket drill-down (SSE), loopback, read-only, error envelope (§13.3, §13.7) | `status.py`, `dashboard.py`, `ticket_events.py` | ✓ exceeds |
| Linear adapter: candidate fetch (paginated), `fetch_issues_by_states`, `fetch_issue_states_by_ids`, blockers, labels, state writes (§11) | `board/linear.py` | ✓ |
| Workspace: sanitized per-issue key, root-containment, `after_create`/`before_run`/`after_run`/`before_remove` hooks, startup terminal cleanup + orphan recovery (§8.6, §9) | `run.py` (`workspace_key`/`is_contained`/`run_hook`), `orchestrator.py` startup recovery | ✓ |
| Documented approval/sandbox posture (§10.5, §15.1) | `worker/autonomy.py` + the deny-by-default secret boundary | ✓ exceeds |

**Where we go beyond Symphony:**

- **Dev-stage taxonomy pipeline** (`taxonomy.py`) — planning → research/design/spec
  → impl as institution-as-data, with worker-driven DAG decomposition. Symphony
  has no typed-work model; a ticket is just a ticket. (Per
  [ADR 0005](../adr/0005-no-stage-prompt-templates.md) the label is now
  dispatch/DAG metadata only — the worker's methodology surface is
  `WORKER_PROTOCOL` + the host's `AGENTS.md`, Symphony's own model.)
- **Serialized single-consumer PR-merger** (`merger.py`) — rebase → integration
  gate (preservation tripwire + hygiene) → code-issued squash-merge, one PR at a
  time (no concurrent-main thrash). Symphony lets the agent merge its own PR via
  the `land` skill.
- **The watched-Director judge** — free-form turn-end dispositions + the
  taste-vs-handle line (`DIRECTOR.md`) + the lights-out completion (`PRINCIPLES.md`
  as the human's externalized taste, [ADR 0003](../adr/0003-lights-out-director.md)).
  Symphony has no equivalent (it's `approval_policy: never`, user-input = hard fail).
- **Deny-by-default worker secret boundary** (`worker/policy.py`) — Symphony only
  *recommends* harness hardening in §15.5 and ships nothing.

## The gaps, ranked (2026-06-16 snapshot — all CLOSED, retained as history)

**1. No active-run reconciliation or stall detection (§8.5).** *Was* the biggest
correctness/operability gap: once dispatched, a worker ran to terminal with no
mid-flight tracker re-check, a wedged worker was never reaped, and there was no
`fetch_issue_states_by_ids` adapter op. **CLOSED** — `2026-06-16-active-run-reconciliation`
added `_reconcile_in_flight` (terminal-state cancel + stall reap) and the
`fetch_issue_states_by_ids` adapter op.

**2. We're a batch drainer, not a daemon (§6.2, §8.1).** `run_until_drained`
re-polled *within* a run but exited on "drained"; Symphony ticks forever.
**CLOSED** — `2026-06-17-continuous-daemon-loop` added `run_forever` over a
persistent running-map (`_RunState`), with the batch wave and the daemon sharing
one claim→submit→reap→reconcile implementation (ARCH inv. 7).

> **The structural root of #1 and #2 (resolved).** `_dispatch_wave` once **blocked**
> on `wait(FIRST_COMPLETED)` until the whole wave reached terminal (the "wave
> barrier"), which is why mid-flight reconcile/kill was impossible. The daemon-loop
> slice moved to Symphony's "running-map + independent tick" model; the wave barrier
> survives only as the batch mode, which now also reconciles in-flight on a
> wall-clock cadence (`reconcile_interval_s`, D-60).

**3. No exponential backoff (§8.4).** We retried once, immediately, in-wave.
**CLOSED** — `2026-06-17-daemon-exponential-backoff` added the `_backoff_s` helper
(`min(base·2^(attempt-1), cap)`) for the daemon's retry/idle/claim; batch keeps
immediate retry by design; the per-completion ~1s continuation re-check is covered
by active-run reconciliation + multi-turn execution.

**4. No declarative config contract (§5–6).** Our state-name map, concurrency,
codex command, and posture were baked into code/flags. **CLOSED (as config, with a
deliberate exception)** — `2026-06-16-director-declarative-config` moved them into
the `director` block of `.harness.json` (typed, `$VAR`-resolved, single `DEFAULTS`
source, ARCH inv. 5). The one Symphony feature we deliberately did **not** adopt is
**hot-reload** — see Remaining deltas.

**5. Thinner agent operating protocol.** Symphony's `WORKFLOW.md` *file* encoded a
rich agent protocol (the single `## Codex Workpad` source-of-truth,
reproduction-first, acceptance-criteria mirroring, the PR feedback sweep, the
Human Review / Rework lifecycle); our per-stage templates were a few sentences each.
**CLOSED** — harvested into `WORKER_PROTOCOL` across `2026-06-17-worker-operating-protocol`,
`2026-06-23-worker-methodology-delivery`, and `2026-06-25-worker-methodology-surface`;
[ADR 0005](../adr/0005-no-stage-prompt-templates.md) then made `WORKER_PROTOCOL` +
the host's `AGENTS.md` the *whole* methodology surface and deleted the stage
templates. As predicted, we did **not** port `WORKFLOW.md` as a file (its lifecycle
steps assume the worker owns the board + self-merge — the two axes ADR 0002 rejects).

**Lesser/adapter-level gaps — all CLOSED.** `board/linear.py` gained
`fetch_issue_states_by_ids` (with `2026-06-16-active-run-reconciliation`),
pagination + `fetch_issues_by_states`, workspace sanitization + root-containment,
and startup terminal cleanup + crash/orphan recovery (`2026-06-18-symphony-adapter-workspace-parity`,
R1–R3). The §9 lifecycle hooks (the repo-population bridge), deferred there as R4,
**shipped** in `2026-06-19-workspace-lifecycle-hooks` (`run.py:run_hook` —
`after_create`/`before_run` fatal, `after_run`/`before_remove` swallowed, per §9.4).

## Remaining deltas (2026-06-26) — three deliberate forks + one un-built runtime

After the closures above, the orchestration **substrate** is at parity or ahead.
What remains is no longer a backlog of capabilities; it is a small set of
intentional divergences plus a single pending runtime:

1. **No config hot-reload (§6.2) — deliberate.** Symphony *MUST* watch `WORKFLOW.md`
   and re-apply config/prompt without restart. We resolve `.harness.json` **once at
   startup** (ARCH inv. 5: "deployment policy is declarative, not code… resolved
   ONCE at startup"). For a self-hosted, episodically-launched Director this is a
   non-cost; it is the one live Symphony *MUST* we do not meet, and would be a
   bounded add (a watch + re-resolve over the existing `DEFAULTS` loader) if a
   long-lived multi-tenant deployment ever needs it.

2. **No `WORKFLOW.md` file / no Liquid prompt templating + `attempt` variable
   (§5.4, §12) — deliberate fork.** Per [ADR 0005](../adr/0005-no-stage-prompt-templates.md),
   the worker prompt is `WORKER_PROTOCOL` + a self-contained ticket, not a
   strict-rendered template; the dev-stage label carries no prompt. This is a
   contract-shape difference, not a capability hole — "templates restrict more than
   they guide," and it *is* Symphony's own one-operating-manual model, just split
   across `WORKER_PROTOCOL` (injected) + the host `AGENTS.md` (auto-loaded).

3. **The lights-out *runtime* (the one genuinely un-built capability).** The
   lights-out *contracts* shipped (`2026-06-17-lights-out-director`): `PRINCIPLES.md`,
   the `DIRECTOR.md` §13 procedure, the park / "awaiting human" board+queue marker,
   and the two-axis mode model ([ADR 0003](../adr/0003-lights-out-director.md)). What
   does **not** exist is the **Daemonized Claude Code** — an event-woken, always-ready
   session that *is* the Director while the human is away. Until it lands, the only
   live Director is the **watched** session (the human's own), so the
   "decoupled human-deputy" the architecture reaches for is real as *seams and
   contracts* but **not yet exercised as a human-absent deputy**. This is the single
   highest-leverage open item and is tracked as a separate in-development runtime
   track (ADR 0003: "OUT of scope here").

## Derived work

The 2026-06-16 "chosen next move" (gap #4, declarative config) and the daemon
track (#1–#3), adapter/workspace parity, the §9 hooks, and the worker-protocol
depth (#5) are **all shipped** — see the execplans cited inline above. The
remaining forward work is **not** in this substrate: it is the **lights-out
runtime** (the Daemonized Claude Code, ADR 0003's separate track) and the optional
hot-reload add (delta #1). Everything else versus Symphony is a settled, documented
divergence rather than a gap.
