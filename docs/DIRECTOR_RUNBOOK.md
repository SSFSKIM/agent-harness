---
status: stable
last_verified: 2026-06-25
owner: harness
type: methodology
tags: [director, runbook, operations]
description: The command-first runbook for standing up and running the Director (Symphony) against a project — zero to a bounded live prod run, the full watched loop, the merger land, and cleanup. The how-to-type companion to DIRECTOR.md's how-to-judge.
---
# DIRECTOR_RUNBOOK.md — running the Director, command by command

This is the **runbook**: what to *type* to stand up and run the Director against a
project. Its companion, [`.claude/DIRECTOR.md`](../.claude/DIRECTOR.md), is the
**behavioral guide** — how the Director *judges* (taste-vs-handle, answering turn
reviews, lights-out). Two genres, two files: come here to run a test; go there to
decide a call. When a step needs a judgment, this runbook points you at the
DIRECTOR.md section that owns it.

> **The mental model in one breath.** You run the orchestrator **from this repo** (the
> agent-harness checkout *is* the Director) and aim it at *your* project — its Linear
> board + its git repo. Workers clone your repo into a scratch workspace, do the work,
> and open PRs; a separate serialized **merger** lands them on `main`. See
> [DIRECTOR.md §0](../.claude/DIRECTOR.md) for the *why* of this consumption model.

---

## 0. When to use which path

| You want to… | Go to | Cost / blast radius |
|---|---|---|
| Smoke that a worker can do *one* ticket end-to-end (no board poll, no live Director) | **§5** `director.run --linear` | One ticket, autonomous, one PR |
| Run the **full loop** — dispatch → you answer turn-reviews → PR → merger lands | **§6 + §8** | One pass, watched; lands real PRs |
| Run it **always-on** (picks up tickets as a human adds them) | **§9** `--daemon` | Open-ended; bounded by `concurrency` |
| Watch/answer a run from a **browser** instead of the session | **§7** dashboard | Read + fenced writes |

**First time against a project? Do §1 → §4 once, then pick a path.** Already set up?
Jump to §5/§6.

> **⚠ Safe fence (read before any real run).** Real workers open **real** GitHub PRs and
> the merger **squash-merges** them. Never first-run against a repo whose `main` you care
> about. Validate against a **disposable copy repo** + a throwaway board (§2), or bound it
> hard with §5 (one ticket, never polls the board).

---

## 1. Prerequisites + the env contract (one-time)

**Binaries / connections:**
- **`codex` CLI** on PATH — the default worker runtime (`codex app-server` is each
  worker spawn). Check: `codex --version` (validated against 0.142.0; the spawn shape is
  stable across the 0.13x–0.14x line).
- *(optional)* the **claude worker runtime** — vendored in-repo, built once:
  `bash worker-runtime/setup.sh` (needs Node + npm; produces
  `worker-runtime/app-server/dist/bin.js`). Enables `--worker claude`. Default stays codex.
- **`gh` authenticated** for the target repo with a token that can **open and merge** PRs:
  `gh auth status`. The merger squash-merges, so merge rights are required.
- **Linear MCP** connected in *this* session (the Director reads/writes the board), plus
  **`LINEAR_API_KEY`** in the environment (the single-ticket path in §5 reads the issue
  through the API directly).

**The three env vars the Director cannot run without** — keep them in `.env`
(**never committed**) and source them before launching:

```bash
# .env (gitignored) holds the live secrets — reference by name, never echo the values:
#   LINEAR_API_KEY=...     board read/write
#   GH_TOKEN=...           the worker's gh ops (clone/push/PR) + the merger's merge
#   DIRECTOR_TEAM=...      the Linear team/board UUID to poll   (optional: can live in .harness.json)
set -a; . ./.env; set +a          # export every key in .env into this shell
```

> The worker runs **deny-by-default**: only the keys listed in
> `worker_policy.worker_env` (default `GH_TOKEN`; add `CLAUDE_CODE_OAUTH_TOKEN` for the
> claude runtime) are forwarded into the sandbox. Nothing else in your env leaks. See
> [DIRECTOR.md §14](../.claude/DIRECTOR.md) for the full worker/Director config map.

---

## 2. The safe fence — disposable repo + a separate runner clone

Two pieces of isolation, both required for a real run:

**(a) A disposable copy repo** (the workers' target — not your canonical repo):

```bash
gh repo create <owner>/<project>-shakedown --private
git push https://x-access-token:${GH_TOKEN}@github.com/<owner>/<project>-shakedown.git master:main
gh repo edit <owner>/<project>-shakedown --default-branch main   # land skill + merger target `main`
```

> Reuse one if it already exists — the `gh` token often lacks `delete_repo` scope, so old
> shakedown repos persist (that's a feature here). To enable delete-on-cleanup:
> `gh auth refresh -h github.com -s delete_repo`.

**(b) A separate runner clone** — run the orchestrator from a clone *other* than your
working checkout, so shakedown config (team, hooks) never touches the canonical
`.harness.json`, and so concurrent sessions don't fight over one index:

```bash
git clone <this-repo-url> ../agent-harness-runner && cd ../agent-harness-runner
```

> **Why a clone, not a worktree:** a `git worktree` shares `.git` (refs + objects), so it
> does **not** isolate you from another session mutating the repo. A separate clone does.
> (See the `worktrees-dont-isolate` lesson.)

---

## 3. Configure the run — the runner's `.harness.json` `director` block

In the **runner clone** (not canonical), add/extend the `director` block. This is the
minimum to aim at a project; [DIRECTOR.md §11](../.claude/DIRECTOR.md) is the full knob
reference.

```jsonc
{
  "director": {
    "team": "$DIRECTOR_TEAM",            // Linear team/board UUID (or a literal, or pass --team)
    "states": {                           // logical state -> YOUR board's column names
      "ready":   "Todo",
      "started": "In Progress",
      "done":    "Done",
      "merging": "In Review"              // present -> enables merge-gated landing (§8)
    },
    "concurrency": 2,
    "dispatch_requires_label": true,      // only claim tickets carrying a dev-stage label
    "worker": { "tools": "linear", "install_skills": true },
    "paths": { "workspace_root": ".harness/workspaces" },
    "workspace": {
      "hooks": {
        "after_create": "git clone https://x-access-token:${GH_TOKEN}@github.com/<owner>/<repo>-shakedown.git .",
        "before_run":   "git fetch origin && git checkout main && git reset --hard origin/main && git clean -fd"
      }
    }
  }
}
```

> **The workspace hooks put your code in front of the worker.** Without an `after_create`
> clone the workspace is an **empty directory** (that is why `--mock` runs need no hooks).
> `before_run` re-syncs to `origin/main` before each ticket, so a child builds on its
> parent's *landed* base. The literal `${GH_TOKEN}` survives config's `$VAR` resolver
> (only a value that is *entirely* `$NAME` is substituted), so the token is injected at
> hook-exec time, never baked into the resolved config.

Verify what a run will actually use (read-only):

```bash
python3 -m director.config            # resolved effective config as JSON
```

A malformed block fails **loud at startup**, before any worker spawns.

---

## 4. Prepare the board (one-time)

On the target Linear team, create the dev-stage labels — `planning` / `spec` / `design`
/ `research` / `impl` — and tag each ticket with the one stage it should run (`impl`
routes the full ExecPlan methodology). With `dispatch_requires_label: true`, an
unlabelled ticket is never claimed (onboarding/stray issues are ignored).

---

## 5. Cheap path — drive ONE ticket (bounded, un-watched)

The cheapest validation: drive a single ticket to terminal with the **autonomous** code
decider (no live Director answers turn-ends, never polls the board). Best first smoke.

```bash
set -a; . ./.env; set +a
python3 -m director.run --linear LIN-23 --tools linear --install-skills
# --worker claude        # opt into the claude runtime (default: codex)
# --max-turns 8          # bound the multi-turn drive
```

Prints a JSON disposition (`{"ticket": "...", "kind": "terminal", ...}`). It opens a real
PR on the shakedown repo. Exit 0 = terminal; non-zero = stuck. This path **skips** the
turn-review judgment seam and the merger — use §6 for the full loop.

---

## 6. Full watched loop — you are the Director

Here a worker turn-end **event-wakes you**; you answer it on the human's behalf so the
worker continues. You do not poll. (The *judgment* — what to answer — is
[DIRECTOR.md §1–§4](../.claude/DIRECTOR.md); this is the *mechanics*.)

**1. Launch the orchestrator (watched), in the background:**

```bash
set -a; . ./.env; set +a
python3 -m director.orchestrator --team "$DIRECTOR_TEAM" --turn-review-timeout 3600
#   --once                      # drain ready work in ONE pass, then exit (bounded run)
#   --concurrency 1             # one worker at a time for a clean first run
#   --worker claude             # claude runtime (default: codex)
```
Run it as a **background task** so the session stays free to answer. `--turn-review-timeout
3600` keeps a worker from timing out while you deliberate. `--once` is the bounded
single-pass run (ideal for validating one canary ticket); omit it for the multi-wave
batch, or use `--daemon` (§9) for always-on.

**2. Arm the queue Monitor** — emits one line per newly-pending request + one `runReport`
per run-level terminal, so each becomes a session notification (the polling lives in this
subprocess, not on you):

```bash
python3 -m director.watch --kinds turnReview,mergeReview,runReport --status-dir .harness/director-status
```

**3. On each event, read the picture before answering** (read-only; never mutates):

```bash
python3 -m director.status                          # whole run: in-flight, stuck, recent outcomes
python3 -m director.status --request '<request JSON>'  # join one request to its ticket context
```
Always run the `--request` join — the bare request says *what* is asked; the join says
whether the *situation around it* changes the answer ([DIRECTOR.md §1/§3](../.claude/DIRECTOR.md)).

**4. Answer the turn-review** — from *this* session, call the same writer the console calls
(`director_min`). Disposition kinds (full semantics: [DIRECTOR.md §4](../.claude/DIRECTOR.md)):

```python
import director.director_min as dm

# read what is pending
dm.pending(base=".harness/director-queue")          # list of pending requests

# continue / decide (the default for a non-terminal turn-end) — content-bearing:
dm.answer_turn("<request_id>", {"kind": "reply", "reply": "continue"})         # or a directive
# terminal (work genuinely done/blocked) — carry the PR through for the merge gate:
dm.answer_turn("<request_id>", {"kind": "terminal",
    "outcome": {"status": "done", "reason": "...", "pr_url": "...", "pr_branch": "..."}})
# escalate (a real product/taste fork you must not decide) -> surfaces to the human:
dm.answer_turn("<request_id>", {"kind": "escalate", "reason": "..."})
```

The blocked worker resumes the SAME thread. For a `done` that opened a PR with a `merging`
state configured, the ticket parks in `merging` until the **merger lands it** (§8) — then
the orchestrator sweeps it to `Done`. "Nothing on the board while a PR is `merging`" is
expected.

---

## 7. Operator console — watch + answer from a browser

For a human to watch AND answer without attaching to the session:

```bash
python3 -m director.dashboard --port 8787 \
  --status-dir   .harness/director-status \
  --queue-dir    .harness/director-queue \
  --history-dir  .harness/director-history \
  --events-dir   .harness/director-events
# -> http://127.0.0.1:8787/
```

- **Watch:** the live run header (cumulative **tokens** climbing mid-turn, runtime,
  rate-limit headroom), in-flight tickets, what's stuck, recent outcomes, the pending
  queue, and a cross-run history panel — server-pushed over SSE.
- **Drill down (per-ticket session events):** click any in-flight or recent ticket row →
  a live panel streams that ticket's worker run **step by step** (turn boundaries, agent
  messages, tool calls + clipped arg summary, token accrual) + a telemetry strip. Backed
  by `director/ticket_events.py` → `<id>.jsonl` under `--events-dir`. (Capturing full tool
  output is a non-goal — a summary, not a transcript.)
- **Answer:** each pending item shows a kind-appropriate control (turnReview →
  reply/done/blocked/escalate; mergeReview → requeue/abandon) — it writes through the same
  `director_min` path as §6. Bound to `127.0.0.1` only; writes need a per-server CSRF token
  + localhost Origin/Host (reads unfenced).

**Get pinged when a run parks** (so you know to open the console):

```bash
export DIRECTOR_WEBHOOK_URL=https://hooks.slack.com/...   # keep in .env, never committed
python3 -m director.notify --queue-dir .harness/director-queue   # or --webhook <url>
```

Fires your webhook once per new human-bound pending request; fail-soft.

---

## 8. Merger — land the PR

A worker's `done` finishes the *work*; landing it on `main` is the serialized **merger**'s
job (it owns the integration boundary; you own execution oversight). Run it after a
PR-bearing ticket reaches `merging`:

```bash
python3 -m director.merger --once
#   --mock         # run the REAL preservation tripwire + hygiene gate + code-issued squash
#                  # merge with a no-op land lane (cheap back-half validation for a clean PR)
```

The merger runs a **code-owned gate** — a preservation tripwire (did the PR's change
survive the rebase, or did a conflict resolution silently drop a hunk?) + a hygiene gate
(CI green + review threads resolved) — and issues the squash-merge **itself**, one PR at a
time. On success it emits a `merger.merge_outcome`; the orchestrator's sweep then moves the
ticket `merging` → `Done`. When a PR cannot cleanly land, the merger posts a **`mergeReview`**
to your queue — handle it per [DIRECTOR.md §7](../.claude/DIRECTOR.md) (`dm.requeue_merge`
with a directive, or escalate). A clean no-CI PR reads `pr_hygiene = green` (empty rollup →
green, 0 threads), so `--mock` lands it without another multi-M-token worker.

---

## 9. Daemon — always-on

`--once`/default are **batch** (drain ready work, exit). `--daemon` never exits on a drained
board — it keeps polling and tops up the moment a slot frees or a human adds a ticket:

```bash
python3 -m director.orchestrator --team "$DIRECTOR_TEAM" --daemon --poll-interval 10
```

- **Stop it:** `SIGTERM`/`Ctrl-C` once → graceful drain (let in-flight workers finish, then
  exit). A **second** signal → force-cancel every in-flight worker and exit fast.
- **Heartbeat** (in `director.status` / the console `run` block): `phase` = `active` /
  `idle` / `draining`; `last_poll_at` / `polls` show it ticking. `phase: idle` **with** a
  non-empty `stuck` means every remaining ticket is blocked — the daemon won't progress
  until **you** unblock it. Full daemon semantics (backoff, reconciliation):
  [DIRECTOR.md §12](../.claude/DIRECTOR.md).

---

## 10. Cleanup after a run

```bash
# stop the background processes (orchestrator / watch / dashboard / notify)
gh repo delete <owner>/<project>-shakedown          # needs delete_repo scope (gh auth refresh -s delete_repo)
# cancel/close the shakedown tickets on the test board
rm -rf ../agent-harness-runner/.harness             # workspaces + status/queue/events dirs
```

If the token lacks `delete_repo`, leave the shakedown repo (it's disposable) and just reset
its `main` next time via the `before_run` sync.

---

## 11. Troubleshooting — the friction list

| Symptom | Cause | Fix |
|---|---|---|
| Worker can't `gh`/clone; `LINEAR_API_KEY` errors | `.env` not sourced into the launching shell | `set -a; . ./.env; set +a` **before** launch (§1) |
| Worker workspace is empty; nothing to build | no `after_create` clone hook (or `--mock`) | add the clone hook (§3); only `--mock` is hook-free |
| `codex: command not found` in the worker | codex CLI not on PATH for the launching env | install/PATH the `codex` CLI; `codex --version` |
| Worker silently dies after ~30s on a real task | old default read-timeout (fixed: now 180s) | ensure you're on current `master`; `--read-timeout 180` to override |
| Worker returns empty turns (0 messages/calls) | Codex/Claude **rate window** exhausted | check the rollout's `rate_limits`; wait for reset (DIRECTOR.md §13 park) |
| Merger won't land; `mergeReview` posted | hygiene gate (red CI / unresolved thread) or preservation tripwire | resolve + `dm.requeue_merge(review, note=...)` (DIRECTOR.md §7) |
| `git mv` / "cannot lock ref" mid-run | a concurrent session shares the same `.git` | use a separate **clone** as the runner, not a worktree (§2) |
| Headline token count looks enormous (~M/turn) | agentic loop re-sends growing transcript; ~97% prompt-cache hits | read the rollout (`~/.codex/sessions/.../rollout-*.jsonl`, `token_count` events) for *real* compute before trusting it |

---

## 12. See also

- [`.claude/DIRECTOR.md`](../.claude/DIRECTOR.md) — the behavioral guide (Identity, §1–§4
  judgment, §6 modes, §7 merge handling, §8/§9 reporting, §11 config reference, §12 daemon
  semantics, §13 lights-out, §14 the config map). **Come here to run; go there to decide.**
- [`docs/adr/0003-lights-out-director.md`](adr/0003-lights-out-director.md) —
  the attended / lights-out / no-agent modes and the guardrail safety floor.
- [`docs/PLANS.md`](PLANS.md) — the ExecPlan methodology the `impl`-labelled workers run.
