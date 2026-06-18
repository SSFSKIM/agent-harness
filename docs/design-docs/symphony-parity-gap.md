---
status: stable
last_verified: 2026-06-16
owner: harness
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

> **Strategic update (2026-06-17).** This doc's "neither bet is ahead" stance and
> its gap-#5-as-output-quality framing are **narrowed by
> [ADR 0002 — graduated autonomy](../memory/adr/0002-graduated-autonomy.md)**: we
> now deliberately take Symphony's autonomy bet on the *middle* (Director →
> exception-handler) and *worker-autonomy* axes, while **keeping** our board-ownership
> + serialized merger (those are correctness wins, not human-in-loop artifacts). Gap
> #5 is reclassified there as the *worker-autonomy enabler*, not just output quality.
> Read this doc as the observational comparison; read ADR 0002 for the chosen stance.

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
  answers free-form. Policy lives in code + CLI flags. The *orchestrator* (not the
  agent) owns board writes; a *separate serialized merger* lands PRs.

Neither is strictly ahead. The bets diverge on autonomy (Symphony: full, human
only seeds the board; us: supervised, a human-proxy Director holds taste) and on
where policy lives (Symphony: declarative `WORKFLOW.md`; us: code).

## Where we match or exceed Symphony

| Symphony capability | Our implementation | State |
|---|---|---|
| Dispatch loop, DAG eligibility, bounded concurrency, claim-before-act (§7–8, §16) | `orchestrator.py`: `run_once`/`run_until_drained`, `eligible_tickets`, `_dispatch_wave` | ✓ |
| Codex app-server client: handshake, turn stream, server-request seam, dynamic tools (§10) | `worker/app_server.py` | ✓ strong |
| Token/rate-limit accounting — absolute totals, ignore deltas (§13.5) | `app_server.extract_usage`/`extract_rate_limits`; `status` `codex_totals` | ✓ |
| Runtime snapshot + HTTP `GET /api/v1/state`, loopback, read-only, error envelope (§13.3, §13.7) | `status.py`, `dashboard.py` | ✓ |
| Linear adapter: candidate fetch, blockers, labels, state writes (§11) | `board/linear.py` | ◐ partial |
| Documented approval/sandbox posture (§10.5, §15.1) | `worker/autonomy.py` + the deny-by-default secret boundary | ✓ exceeds |

**Where we go beyond Symphony:**

- **Dev-stage taxonomy pipeline** (`taxonomy.py`) — planning → research/design/spec
  → impl as institution-as-data, with worker-driven DAG decomposition. Symphony
  has no typed-work model; a ticket is just a ticket.
- **Serialized single-consumer PR-merger** (`merger.py`) — rebase → integration
  gate → squash-merge, one PR at a time (no concurrent-main thrash). Symphony lets
  the agent merge its own PR via the `land` skill.
- **The watched-Director judge** — free-form turn-end dispositions + the
  taste-vs-handle line (`DIRECTOR.md`). Symphony has no equivalent (it's
  `approval_policy: never`, user-input = hard fail).
- **Deny-by-default worker secret boundary** (`worker/policy.py`) — Symphony only
  *recommends* harness hardening in §15.5 and ships nothing.

## The gaps, ranked

**1. No active-run reconciliation or stall detection (§8.5) — the biggest
correctness/operability gap.** Symphony, *every tick*, refreshes the tracker state
of all running issues and **stops a worker whose ticket a human moved to
terminal/cancelled** — the operator's primary control lever (§14.4). It also reaps
workers idle for `stall_timeout_ms`. We do **neither**: once dispatched, a worker
runs to terminal with no mid-flight tracker re-check, and a wedged worker is never
reaped. We also lack the `fetch_issue_states_by_ids` adapter op (§11.1) this needs.

**2. We're a batch drainer, not a daemon (§6.2, §8.1) — the identity gap.**
`run_until_drained` re-polls *within* a run but exits on "drained". Symphony ticks
forever at `polling.interval_ms`, picking up tickets created later, indefinitely.
The "long-running automation service" Symphony *is*, we are not. → **daemon stage 2:
`docs/product-specs/2026-06-17-continuous-daemon-loop.md`** (collapses both barriers
into one continuous tick loop over a persistent running-map; adds the `run_forever`
mode; lifts stage 1's reconcile/cancel pieces unchanged).

> **The structural root of #1 and #2.** `_dispatch_wave` **blocks** on
> `wait(FIRST_COMPLETED)` until the whole wave reaches terminal (the "wave
> barrier"). Symphony keeps a `running` map of *background* workers and **keeps
> ticking while they run** — which is exactly what lets it reconcile/kill a worker
> mid-flight. So #1 and #2 are not independent bolt-ons: closing them means moving
> from our wave-barrier to Symphony's "running-map + independent tick" loop. That
> refactor is the real cost.

**3. No exponential backoff (§8.4).** We retry-once, immediately, in-wave
(`reconcile` `retry_budget`). Symphony does `min(10000·2^(attempt-1),
max_retry_backoff_ms)` plus a ~1s continuation retry after a *normal* worker exit
that re-checks whether the issue is still active. Small; completes the retry model.
→ **daemon stage 3: `docs/product-specs/2026-06-17-daemon-exponential-backoff.md`**
(exponential backoff for the daemon's retry/idle/claim via one `_backoff_s` helper;
batch keeps immediate retry; the per-completion re-check is a non-goal — active-run
reconciliation already covers it). **With stages 1–3 shipped, the daemon track
(gaps #1/#2/#3) is CLOSED;** gap #4 (config) is done; only gap #5 (agent protocol
depth) remains, on the separate worker-protocol track.

**4. No `WORKFLOW.md` declarative contract (§5–6) — the portability/philosophy
gap.** Symphony's premise — "teams version the agent prompt + runtime settings
*with their code*" — has no analog. Our state-name map, concurrency, codex command,
posture, and stage templates are baked into code/flags; no config layer, `$VAR`
indirection, or reload. Partly deliberate (we self-host), but it is the single most
Symphony-defining feature we lack, and it maps naturally onto our existing
`.harness.json` host-config grain (ARCHITECTURE invariant 7).

**5. Thinner agent operating protocol.** Symphony's `WORKFLOW.md` *file* encodes a
rich, battle-tested agent protocol: the single `## Codex Workpad` comment as
source-of-truth, reproduction-first, acceptance-criteria mirroring, the **PR
feedback sweep**, and the explicit Human Review / Rework lifecycle. Our per-stage
templates in `taxonomy.py` are a few sentences each. This is the lever for worker
*output quality* — and, per
[ADR 0002](../memory/adr/0002-graduated-autonomy.md), the **precondition for
graduated autonomy**: the worker protocol must be rich enough to run unsupervised
before the Director can step back from judging every turn-end. Harvest the
stage-agnostic disciplines into a shared worker-protocol preamble; do **not** port
`WORKFLOW.md` as a file (its lifecycle steps assume the worker owns the board +
self-merge — the two axes ADR 0002 rejects).

**Lesser/adapter-level gaps:** `board/linear.py` lacks `fetch_issue_states_by_ids`
(§11.1, ties to #1), pagination (§11.2), and startup terminal-workspace cleanup
(§8.6); no crash/restart recovery path (§7.4, §14.3 — though our board-as-truth
model recovers in spirit); workspace handling lacks Symphony's sanitization +
root-containment invariants and the `after_create`/`before_run`/`after_run`/
`before_remove` hooks (§9).

> **Update (2026-06-18).** `fetch_issue_states_by_ids` **landed** with the
> active-run-reconciliation slice (so it is no longer a gap). The rest of this
> paragraph is now the **Symphony adapter & workspace parity** track:
> [`docs/product-specs/2026-06-18-symphony-adapter-workspace-parity.md`](../product-specs/2026-06-18-symphony-adapter-workspace-parity.md)
> takes pagination + the `fetch_issues_by_states` op (R1), workspace sanitization +
> root-containment (R2), and startup cleanup + crash/orphan recovery (R3); the §9
> lifecycle hooks (the repo-population bridge) are deferred there as R4.

## Derived work

The chosen next move (human pick, 2026-06-16, from the three axes — daemon /
declarative-config / agent-protocol) is **gap #4**: see
`docs/product-specs/2026-06-16-director-declarative-config.md`. Gaps #1–#3 (the
reconciling-daemon refactor) and #5 (worker protocol depth) remain open and would
each take the full product-design → execplan flow; #1's wave-barrier→running-map
refactor is the heaviest single item.
