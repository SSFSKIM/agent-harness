---
status: stable
last_verified: 2026-06-18
owner: harness
---
# Symphony adapter & workspace parity

The leftover **"lesser/adapter-level gaps"** from
[`symphony-parity-gap.md`](../design-docs/symphony-parity-gap.md) (lines 130–135).
The daemon track (gaps #1–#3), declarative config (#4), and worker-protocol depth
(#5) all closed or moved to their own tracks; what remains is four adapter/
workspace-level items. This spec covers three of them now (R1–R3) and records the
fourth (R4 — workspace lifecycle hooks) as a **deferred non-goal** with the why.

Grounded in a read of `docs/symphony-original/SPEC.md` §8.5/§8.6/§9/§11.1/§11.2/
§14.3/§17.2–17.4 and our current `board/linear.py`, `run.py`, `orchestrator.py`.

## Problem

Three observable gaps remain between our orchestrator and the Symphony reference,
all at the adapter/workspace seam (the orchestration *core* — poll/dispatch/
reconcile/daemon — already matches):

1. **The Linear candidate poll silently truncates.** `_READY_ISSUES`
   (`board/linear.py:42`) and `list_ready_issues` (`:171`) issue **no
   `first:`/`after:` cursor** — they read one page of the `issues` connection
   (Linear's default 50) and drop the rest. A backlog of >50 ready tickets means
   some are **never dispatched**, and the board looks "empty of new work." Symphony
   marks pagination REQUIRED for candidate issues (§11.2). We also lack the
   `fetch_issues_by_states` adapter op (§11.1 op #2) that startup cleanup and crash
   recovery both need.

2. **Workspace paths are unsanitized and unbounded.** `_workspace_for`
   (`run.py:71`) builds `workspace_root / str(ticket["id"])` and `mkdir`s it with
   **no key sanitization** (a board identifier containing `/` or `..` escapes the
   root) and **no root-containment check**. Symphony §9.5 makes both mandatory
   invariants.

3. **A restarted daemon leaks and strands work.** `run_forever`
   (`orchestrator.py:592`) goes straight into its tick loop. There is **no startup
   cleanup** (workspaces for already-terminal issues accumulate forever across
   restarts — §8.6) and **no recovery** for tickets the prior process had moved to
   `started` and was running when it died: those are now invisible to the
   `ready`-only poll, so they sit in `started` with no worker, **stranded** until a
   human intervenes (§14.3). Relatedly, reconcile never cleans the workspace of a
   worker a human killed mid-flight by moving its ticket to a terminal state (§8.5
   Part B says it should).

## Requirements

- **R1 — Paginated candidate fetch + state-set fetch.**
  - **R1a** `list_ready_issues` returns **all** ready issues across pages, not just
    the first. A human can create 60 ready tickets and observe all 60 returned (vs.
    50 today). Page order is preserved across pages.
  - **R1b** A new adapter op `fetch_issues_by_states(state_ids)` returns the
    normalized tickets currently in any of the given workflow states, paginated the
    same way. An **empty `state_ids` makes no API call** (returns `[]`), mirroring
    `fetch_issue_states_by_ids`'s empty-guard (§17.3).
  - **R1c** A pagination-integrity violation — `hasNextPage == true` with a
    missing/empty `endCursor` — **raises** (Symphony `linear_missing_end_cursor`),
    never silently truncates.

- **R2 — Workspace safety invariants (Symphony §9.5).**
  - **R2a** The per-issue workspace **key** is sanitized: every character outside
    `[A-Za-z0-9._-]` is replaced with `_` before the path is built. A human can
    dispatch a ticket whose id is `feat/ABC XY` and observe the workspace dir named
    `feat_ABC_XY` directly under the root (slash + space collapsed, not a nested path).
    Note `.` is in the allowed set (Symphony's charset), so a literal `..` survives
    sanitization — the **R2b containment check** is what blocks a `..` escape, not the
    sanitizer; the two invariants are complementary.
  - **R2b** The derived workspace path is **contained**: it resolves to a directory
    whose parent is the resolved workspace root; a path that would resolve outside
    the root **raises** before any `mkdir` or worker launch.
  - **R2c** The path derivation (key sanitization + join) is a **single shared
    helper** used by dispatch, merge-enqueue, and cleanup — all three compute the
    identical directory for a given (id, root). (ARCHITECTURE invariant 8.)
  - **R2d** Before launching the worker subprocess, the resolved process `cwd`
    equals the resolved workspace path (§9.5 invariant 1) — a defense-in-depth
    assert.

- **R3 — Daemon startup recovery (Symphony §8.6 + §14.3 + §8.5 Part B).**
  - **R3a** *Startup terminal cleanup.* On `run_forever` entry, before the first
    tick, fetch issues in terminal states (via R1b) and `rmtree` each one's
    workspace — **except** any workspace path still referenced by a pending
    `mergeRequest` in the Director queue (those PR branches are needed by the
    serialized merger). Each rmtree is guarded by the R2b containment check. The
    whole step is **fail-soft**: a fetch or delete error logs and startup continues
    (§8.6, §11.4).
  - **R3b** *Orphan recovery.* On `run_forever` entry, before the first tick, fetch
    issues in the `started` state (via R1b) — on a fresh process every such ticket
    is a prior-crash orphan (the live running-map is empty) — and transition each
    back to `ready` so the first poll re-dispatches it into the reused workspace.
    Fail-soft per orphan. A human can: start a run, kill the daemon mid-ticket
    (ticket left in `In Progress`), restart the daemon, and observe the ticket
    re-dispatched rather than stranded.
  - **R3c** *Mid-flight terminal cleanup.* When reconcile resolves a `cancelled`
    disposition whose observed external state is **terminal**, it `rmtree`s the
    (now-abandoned, never-merged) workspace, R2b-guarded, best-effort. A `cancelled`
    to a **non-terminal** state, and every **normal** terminal (`done`/`blocked`),
    leave the workspace intact (§8.5 Part B; §9.1 "successful runs do not
    auto-delete" + our merger still needs a `done` PR branch).

- **R4 — Workspace lifecycle hooks. DEFERRED (non-goal for this spec).** See
  Non-goals; recorded here so the parity track has a home for it.

## Design

Additive throughout. No change to the daemon/reconcile control flow (gaps #1–#3),
the decider, the queue, or the merger's own logic.

### Component 1 — `director/board/linear.py` (R1)

- **Paginate the candidate query.** `_READY_ISSUES` gains `$after: String` and
  `first: 50`, and selects `pageInfo { hasNextPage endCursor }` alongside `nodes`.
  `list_ready_issues` loops: POST with `after=None`, accumulate `nodes`, and while
  `pageInfo.hasNextPage` POST again with `after=endCursor`; stop when false. If
  `hasNextPage` is true but `endCursor` is falsy → `raise RuntimeError` (R1c). Node
  order is the API's; pages append in fetch order (R1a order-preservation).
- **New query + op `fetch_issues_by_states`.** A `_ISSUES_BY_STATES` GraphQL doc
  filtering `state: { id: { in: $states } }` over the team, paginated identically,
  selecting the same fields `list_ready_issues` normalizes (so the returned tickets
  carry `id`, `identifier`, `prompt`, `state`/`state_id`, `labels`, `blockers` and
  are re-dispatchable). Empty `state_ids` → `[]`, no POST (R1b). Exposed as a
  `LinearBoard` method like the others.
- A shared `_paginate(query, base_variables, *, api_key, endpoint, http_post)`
  helper folds the cursor loop + integrity check so both queries share one
  implementation and one test surface (§11.2 "keep query construction isolated").
- Error contract unchanged: a GraphQL `errors` array still raises via `_post`;
  pagination integrity raises with a distinct message. `fetch_issue_states_by_ids`
  is **not** paginated (its `id: { in: $ids }` result is bounded by the running
  count ≤ concurrency; recorded as accepted in Decisions).

### Component 2 — `director/run.py` (R2)

- **`workspace_key(identifier) -> str`** — `re.sub(r"[^A-Za-z0-9._-]", "_", str(identifier))`.
- **`workspace_path(identifier, workspace_root) -> Path`** — `Path(workspace_root) /
  workspace_key(identifier)`, the single derivation (R2c). `_workspace_for` calls it
  for the derived case; `orchestrator._maybe_enqueue_merge` (which today re-derives
  `Path(workspace_root) / str(tid)` at `:105`) and the startup cleanup both import
  and call it — `orchestrator` already imports `run`, so no new private cross-import.
- **`_workspace_for`** gains the containment guard (R2b): for the derived path,
  resolve it and the root to absolute and require the root to be a parent
  (`Path.resolve()` + `is_relative_to`); else `raise`. The explicit `ticket["workspace"]`
  override is the single-ticket-CLI / test affordance (a trusted caller targeting
  e.g. `/tmp`), is never produced by the Linear daemon path (board ids are always
  derived), and is therefore **exempt** from containment — documented inline and in
  Decisions. The board-controlled id is the real escape vector, and R2a sanitizes it.
- **`_prepare`** asserts `Path(ws).resolve() == <the resolved workspace path>` right
  before constructing `AppServerClient(cwd=ws)` (R2d).

### Component 3 — `director/orchestrator.py` (R3)

- **`_startup_recovery(state-like inputs)`** — a new helper run once at the top of
  `run_forever` (before the `while True`), composed of two fail-soft passes over a
  single `board.fetch_issues_by_states([...terminal..., started])` (or two calls;
  the plan chooses) partitioned by state:
  - *terminal partition* → R3a: for each, `ws = run.workspace_path(id, workspace_root)`;
    skip if `ws` is in the set of pending-merge workspace paths (read from the
    Director queue's `mergeRequest` entries — what the merger consumes); else
    `shutil.rmtree(ws, ignore_errors=True)` after the R2b containment check. Wrap the
    whole pass in try/except → log + continue (§8.6).
  - *`started` partition* → R3b: for each, `board.update_issue_state(id, states["ready"])`
    best-effort (per-orphan try/except), so the first `list_ready_issues` poll
    re-claims and re-dispatches it. (Goes through the normal claim path; no new
    dispatch branch.)
- **`reconcile`** (R3c) — in the `cancelled` branch (`:190`), when `external_state`
  is one of the terminal state names, `rmtree` the ticket's `run.workspace_path(...)`
  (R2b-guarded, best-effort, recorded in `errs` on failure like other writes). The
  `done`/`blocked`/non-terminal-cancelled branches are unchanged (no cleanup).
- The "terminal states" set for R3a/R3c is derived from `resolve_states` output —
  `done` plus the optional `blocked`/`failed` when configured (the same logical
  states reconcile already writes). `run_forever` is given the terminal state ids/
  names it needs (additive parameter or derived from `states`).

### Errors, edges, integration

- **Empty board / no orphans / no terminal issues:** every R3 pass is a no-op
  (R1b empty-guard + empty partitions). Reconcile with no running issues unchanged.
- **Fetch failure at startup:** logged, startup proceeds (§11.4) — the daemon still
  runs; cleanup/recovery simply didn't happen this boot (idempotent — next restart
  retries).
- **A `done` ticket with a pending merge:** its workspace is **kept** by R3a's
  merge-queue exclusion, so the merger can still land the PR after a restart.
- **Double-worker risk on orphan recovery:** R3b assumes the prior process's worker
  subprocess died with the daemon (same process tree) — Symphony's §14.3 stance ("no
  running sessions are assumed recoverable"). If a worker were somehow reparented and
  survived, re-dispatch could run a second worker on the same reused workspace.
  Accepted (Decisions); single-instance deployment, board-as-truth converges.
- **Pagination + reconcile read:** `fetch_issue_states_by_ids` stays single-page by
  design (bounded by running count); only the two unbounded reads (candidate poll,
  state-set fetch) paginate.

## Non-goals

- **R4 — Workspace lifecycle hooks** (`after_create` / `before_run` / `after_run` /
  `before_remove`, §9.4, with `.harness.json` config + `hooks.timeout_ms`).
  **Deferred deliberately.** In Symphony these hooks are the **repo-population
  bridge** — `after_create`/`before_run` git-clone/checkout the codebase into the
  fresh workspace. Our workers today run in a *bare* per-ticket dir (no repo), so
  hooks aren't yet load-bearing; they become essential only when we point workers at
  a real repo / real PRs, which is its own product decision (where the code comes
  from, the host-shell-execution trust boundary, the config schema). Specced as a
  future slice of this same parity track, not built now.
- No change to the daemon tick loop, backoff, stall handling, decider, queue, or
  merger internals (all closed tracks).
- No multi-instance claim coordination (orphan recovery is single-instance).
- No retry-timer / live-session persistence across restart (§14.3 explicitly
  in-memory; board-as-truth + R3 is the recovery model).
- No pagination of the by-ids reconcile read (bounded small).

## Acceptance criteria

1. **R1a/R1c:** a unit test drives `list_ready_issues` against a fake `http_post`
   returning two pages (`hasNextPage` then false) and asserts all nodes from both
   pages are returned in order; a second test with `hasNextPage=true` + empty
   `endCursor` asserts it raises.
2. **R1b:** `fetch_issues_by_states([])` makes zero `http_post` calls and returns
   `[]`; a populated multi-page case returns normalized, re-dispatchable tickets.
3. **R2a/R2b:** a test asserts `workspace_key("feat/ABC XY") == "feat_ABC_XY"` (and
   that `.` survives, so `".."` is preserved); a *derived* id that resolves outside the
   root (e.g. `".."`) raises before mkdir.
4. **R2c:** dispatch, merge-enqueue, and cleanup are shown to call the one
   `workspace_path` helper (same path for the same id+root) — e.g. a test asserts
   `_maybe_enqueue_merge` and `_workspace_for` agree.
5. **R3a:** a `run_forever` test with `max_ticks` and a fake board reporting terminal
   issues asserts their workspace dirs are removed at startup, **except** one whose
   path is in a seeded pending-merge queue, which survives; a fetch-raises variant
   asserts startup still proceeds.
6. **R3b:** a test seeds a `started` ticket, runs startup recovery, and asserts a
   `ready` transition was issued for it (→ re-dispatchable).
7. **R3c:** a reconcile test with a `cancelled` disposition + terminal
   `external_state` asserts the workspace is removed; with a non-terminal
   `external_state`, and with a normal `done`, asserts it is **not**.
8. The full gate (`python3 plugin/scripts/check.py`) is GREEN.
