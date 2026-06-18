---
status: active
last_verified: 2026-06-18
owner: harness
base_commit: f2748b5e0137f417c05dcc29a7c41673cd7ecc87
review_level: standard
---
# Symphony adapter & workspace parity (slices 1–3)

## Goal
Close the three leftover adapter/workspace Symphony-parity gaps so the daemon is
correct at scale and survives restarts. Observable definition of done:
1. `list_ready_issues` returns **all** ready issues across pages (not just the first
   50), and a new paginated `fetch_issues_by_states` op exists — proven by unit tests
   driving a multi-page fake `http_post`.
2. A ticket whose board id contains `/` or `..` produces a **sanitized, root-contained**
   workspace dir (no escape), and dispatch / merge-enqueue / cleanup all derive the
   **same** path from one helper — proven by tests.
3. `run_forever` on startup **cleans** terminal-issue workspaces (except those a pending
   merge still needs) and **re-attaches** orphaned `started` tickets so they re-dispatch;
   reconcile **cleans** the workspace of a worker a human killed mid-flight to a terminal
   state, and **never** for a normal `done`/`blocked` — proven by `run_forever`/reconcile
   tests with `max_ticks` + a fake board.

The full gate (`python3 plugin/scripts/check.py`) is GREEN; no behavior of the daemon
tick loop, backoff, decider, queue append, or merger internals changes.

## Context
Built from the spec — the spec owns the design, this plan owns the build (does not
re-derive it):
- **Spec:** `docs/product-specs/2026-06-18-symphony-adapter-workspace-parity.md`
  (R1 pagination + `fetch_issues_by_states`; R2 workspace safety; R3 daemon startup
  recovery; R4 hooks DEFERRED).
- **Gap origin:** `docs/design-docs/symphony-parity-gap.md` (lines 130–135 + the
  2026-06-18 update).
- **Symphony reference:** `docs/symphony-original/SPEC.md` §8.5 (Part B reconcile
  cleanup), §8.6 (startup cleanup), §9.5 (workspace safety invariants), §11.1–11.2
  (adapter ops + Linear pagination), §14.3 (restart recovery), §17.2–17.4.
- **Code touched:** `director/board/linear.py` (M1), `director/run.py` (M2),
  `director/orchestrator.py` (M2 one-line + M3). Tests in `tests/`.
- **Integration facts already confirmed (don't re-discover):**
  - `merger.pending_merges(base)` (`director/merger.py:115`) returns the pending
    `mergeRequest` entries; each carries `workspace_path` at top level
    (`director/queue/__init__.py:133`). M3 excludes those paths from cleanup.
  - `_maybe_enqueue_merge` re-derives `Path(workspace_root)/str(tid)`
    (`orchestrator.py:105-107`) — the duplication M2 removes via `run.workspace_path`.
  - `_reconcile_in_flight` records the observed state in `cancelled_states[tid]`
    (`orchestrator.py:285`), today the `state_name` only; `fetch_issue_states_by_ids`
    also returns `state_type` (`linear.py:231`). M3 stores the dict so reconcile can
    test terminality by **type**.
  - `reconcile`'s `cancelled` branch is `orchestrator.py:190-200`; `reap` calls
    `reconcile(... external_state=self.cancelled_states.pop(tid, None))` (`:389`).
  - `resolve_states` (`orchestrator.py:40`) yields ids for ready/started/done/
    blocked/failed; `run_forever` (`:592`) is the daemon entry.

## Approach (self-generated alternatives)

**Pagination shape (M1):**
- A: per-query ad-hoc cursor loops in `list_ready_issues` and `fetch_issues_by_states`.
- B: one shared `_paginate(query, base_variables, node_path, ...)` helper both call.
- **Chosen: B** — single cursor-loop + integrity-check implementation, one test
  surface (spec "keep query construction isolated"); the two ops differ only in the
  GraphQL doc + variables.

**Orphan recovery (M3):**
- A: a new "submit-without-claim" dispatch path that attaches a worker to a `started`
  orphan directly.
- B: transition each orphan `started → ready` at startup, then let the normal first
  poll re-claim and re-dispatch it.
- **Chosen: B** — zero new dispatch logic, goes through the existing
  claim-before-act path; on a fresh process every `started` ticket is an orphan (the
  running-map is empty before the loop), so the transition is unambiguous and safe.

**Terminal detection for reconcile cleanup (M3, R3c):**
- A: compare `external_state` (a state *name*) against the configured terminal state
  names {done, blocked, failed}.
- B: carry Linear's `state_type` through `cancelled_states` and clean when
  `type ∈ {completed, canceled}`.
- **Chosen: B** — type is the canonical, naming-independent terminal signal and it
  catches a human-chosen terminal state *outside* our config (e.g. "Canceled"), which
  A would miss. Cost: `cancelled_states[tid]` becomes the observed-state dict instead
  of a bare name (a contained change to one closed-slice line + the cancelled-branch
  label + the few cancelled-branch tests).

**Containment for the explicit `workspace` override (M2, R2b):**
- A: enforce containment on every workspace path including explicit overrides.
- B: enforce on the *derived* path; exempt the explicit `ticket["workspace"]` override.
- **Chosen: B** — the override is the trusted single-ticket-CLI / test affordance
  (tests target `/tmp`), is never produced by the Linear daemon path (board ids are
  always derived), and the board-controlled id is the real escape vector that R2a
  sanitizes. Documented inline + in the spec.

## Assumptions & open questions (self-interrogation)
- **Assumption:** the prior process's worker subprocess died with the daemon (same
  process tree), so an orphan `started` ticket has no live worker — Symphony §14.3's
  stance. *Breaks if* a worker were reparented and survived a daemon crash → orphan
  re-dispatch could double-run on the reused workspace. Accepted (single-instance,
  board-as-truth converges); recorded in the spec.
- **Assumption:** `Path.is_relative_to` (py3.9+) is available on the gate's Python.
  *Breaks if* an older interpreter → fall back to a `os.path.commonpath`/prefix check.
  Will confirm at M2 (the gate runs the tests).
- **Assumption:** pagination `endCursor`/`hasNextPage` live under the connection's
  `pageInfo` for the Linear `issues` connection. *Breaks if* the schema differs →
  the M1 tests use a fake `http_post`, and the live shape is verified by the existing
  Linear-backed behavioral path (not re-run here without a board).
- **Open:** should `fetch_issue_states_by_ids` (reconcile read) also paginate?
  → Resolved **no** (spec): bounded by running count ≤ concurrency; recorded as
  accepted in the spec. Only the two unbounded reads paginate.
- **Open:** does cleaning a `blocked` workspace risk a pending merge? → No: only a
  `done` worker enqueues a merge (`_maybe_enqueue_merge` requires PR fields); the
  pending-merge exclusion set covers it regardless of state, so M3's exclusion is the
  single safety net.

## Milestones

- **M1 — Linear adapter: pagination + `fetch_issues_by_states` (R1).**
  Scope: `director/board/linear.py`. Add `$after: String` + `first: 50` +
  `pageInfo { hasNextPage endCursor }` to `_READY_ISSUES`; add a new
  `_ISSUES_BY_STATES` doc filtering `state: { id: { in: $states } }` over the team
  with the same fields + pageInfo. Add a shared `_paginate(query, variables, *,
  api_key, endpoint, http_post)` that POSTs pages (threading `after=endCursor`),
  concatenates `issues.nodes` in fetch order, and **raises** `RuntimeError` when
  `hasNextPage` is true but `endCursor` is falsy. Rewrite `list_ready_issues` to
  normalize the paginated nodes (state_id/blockers/labels exactly as today). Add
  `fetch_issues_by_states(state_ids, ...)`: empty `state_ids` → `[]` with **no**
  POST; else paginate + normalize to the same re-dispatchable ticket dicts; expose
  a `LinearBoard.fetch_issues_by_states` method. At the end: the adapter fetches
  unboundedly and the new op exists. Run: `python3 -m pytest tests/test_director_linear.py -q`
  (add cases). Acceptance: a 2-page fake (`hasNextPage` then false) returns all nodes
  in order; `hasNextPage`+empty `endCursor` raises; `fetch_issues_by_states([])` makes
  0 POSTs and returns `[]`; a populated multi-page case returns normalized tickets
  (spec acceptance 1–2).

- **M2 — Workspace safety helper + containment + cwd assert (R2).**
  Scope: `director/run.py` (+ a one-line call-site change in `orchestrator.py`). Add
  `workspace_key(identifier)` (`re.sub(r"[^A-Za-z0-9._-]", "_", str(identifier))`) and
  `workspace_path(identifier, workspace_root) -> Path` (the single derivation). Point
  `_workspace_for` at `workspace_path` for the derived case and add the containment
  guard — resolve the derived path and the root, require the root to be a parent
  (`is_relative_to`), else `raise`; the explicit `ticket["workspace"]` override stays
  exempt (documented). Replace `_maybe_enqueue_merge`'s re-derivation
  (`orchestrator.py:105-107`) with `run.workspace_path(tid, workspace_root)` (import
  already present). In `_prepare`, assert the resolved `cwd` equals the resolved
  workspace path before constructing `AppServerClient`. At the end: one helper governs
  every workspace path; ids are sanitized + contained. Run:
  `python3 -m pytest tests/test_director_run.py -q` (add cases). Acceptance:
  `workspace_key("feat/ABC XY")=="feat_ABC_XY"`; a *derived* id resolving outside root
  (e.g. `".."`) raises before mkdir; `_maybe_enqueue_merge` and `_workspace_for` agree on
  the path for the same id+root (spec acceptance 3–4). (`.` is allowed, so `..` survives
  sanitization — containment R2b blocks the escape, not the sanitizer.)

- **M3 — Daemon startup recovery + reconcile cleanup (R3).**
  Scope: `director/orchestrator.py`. Add `_startup_recovery(board, states, *,
  workspace_root, queue_base, terminal_state_ids)` invoked once at the top of
  `run_forever` before the `while True`:
  (a) **startup terminal cleanup** — `board.fetch_issues_by_states(terminal_state_ids)`;
  build the exclusion set from `{r.get("workspace_path") for r in
  merger.pending_merges(base=queue_base)}`; for each terminal issue compute
  `run.workspace_path(id, workspace_root)`, skip if excluded, else containment-check +
  `shutil.rmtree(..., ignore_errors=True)`; the whole pass in try/except → log+continue;
  (b) **orphan re-attach** — `board.fetch_issues_by_states([started_id])`; for each,
  `board.update_issue_state(id, states["ready"])` in a per-orphan try/except.
  Then update `_reconcile_in_flight` to store the observed-state **dict** in
  `cancelled_states[tid]` (was `state_name`), and `reconcile`'s `cancelled` branch
  (`:190-200`) to read `final = (external_state or {}).get("state_name") or "released"`
  and `rmtree` the `run.workspace_path` (containment-guarded, best-effort → `errs`)
  **iff** `(external_state or {}).get("state_type") in {"completed","canceled"}`; the
  `done`/`blocked`/non-terminal branches are untouched. `run_forever` derives
  `terminal_state_ids` from `states` (done + blocked/failed when set) and passes them in.
  At the end: a restarted daemon self-heals. Run:
  `python3 -m pytest tests/test_director_orchestrator.py -q` (add cases; daemon tests
  live here). Acceptance: terminal workspaces removed at startup
  except a seeded pending-merge path; fetch-raises → startup still proceeds; a seeded
  `started` ticket gets a `ready` transition; reconcile cleans on cancelled-to-terminal
  (by type), not on non-terminal-cancelled nor normal `done` (spec acceptance 5–7).

## Progress log
- [x] (2026-06-18) Plan created from spec; base_commit recorded.
- [x] (2026-06-18) M1 done. `board/linear.py`: `_CANDIDATE_FIELDS` shared fragment;
  `_READY_ISSUES`/`_ISSUES_BY_STATES` paginated (`first:50`+`after`+`pageInfo`);
  `_paginate` helper (order-preserving, missing-end-cursor raise, no-pageInfo→single
  page); `_normalize_candidate` extracted; `list_ready_issues` paginates;
  `fetch_issues_by_states(team, state_ids)` + LinearBoard method (empty-guard).
  `tests/test_director_linear.py` +6 (2-page order, missing-cursor raise, no-pageInfo,
  empty-guard, by-states paginate+normalize, board method). 22 pass; full gate GREEN.
- [x] (2026-06-18) M2 done. `run.py`: `workspace_key` (re.sub charset) + shared
  `workspace_path` helper; `_workspace_for` derived-path containment guard (resolve +
  `is_relative_to`, raise) with explicit-override exemption; `_prepare` pre-launch
  cwd/is-dir check (§9.5 inv 1). `orchestrator._maybe_enqueue_merge` now calls
  `run.workspace_path` (was re-derived). `tests/test_director_run.py` +6 (key sanitize
  incl. `..` survives, path = root+key, derived contained, derived-`..` raises, override
  exempt, dispatch↔merge agree). 13 pass; full gate GREEN.
- [ ] M3 next.

## Surprises & discoveries
- 2026-06-18 (M2): the spec's first sanitization example (`feat/ABC..XY → feat_ABC__XY`)
  was wrong — Symphony's charset `[A-Za-z0-9._-]` ALLOWS `.`, so `..` survives the
  sanitizer. Containment (R2b) is what blocks a `..`-component escape (`root/..`
  resolves outside root → raise). The two invariants are complementary, not redundant.
  Corrected spec R2a + acceptance 3 and the M2 milestone/acceptance to a real example
  (`feat/ABC XY → feat_ABC_XY`) + a derived-`..` containment case. In practice the
  derived key is the issue UUID (always safe); sanitization+containment are
  defense-in-depth for a malformed id.

## Decision log
- 2026-06-18: shared `_paginate` helper (Approach B) — one cursor loop, one test surface.
- 2026-06-18: orphan recovery via `started → ready` transition (Approach B) — reuses the
  normal claim path; every `started` ticket is an orphan at fresh-process startup.
- 2026-06-18: reconcile terminal detection by Linear `state_type` (Approach B) — carry
  the observed-state dict through `cancelled_states`; catches out-of-config terminals.
- 2026-06-18: containment enforced on the derived path only; explicit `workspace`
  override exempt (trusted CLI/test affordance, never on the Linear daemon path).
- 2026-06-18: completion review = standard (arch + reliability) **plus review-security**
  — the diff adds a filesystem write surface (path containment + `rmtree`) that warrants
  a security pass even though it is not the hooks/.harness.json live-exec surface.

## Feedback (from completion gate)

## Outcomes & retrospective
