---
status: active
last_verified: 2026-06-29
owner: harness
type: exec-plan
description: Make reconcile's spawned-id validation identifier-aware so a worker that reports a child by its human identifier (LIN-31) instead of the UUID node id is no longer false-classified as a missing/unlabeled child (false escalate on blocked, misleading "not found" on done); and document operator-facing that a blocked/escalate/park terminal needs a manual re-ready (it does not auto-resume, and any child blocked_by it stays undispatchable until then).
base_commit: e1c23c13ee62db21a15290b1ce5fb2cede1aa6ce
review_level: standard
---
# Spawned-id identifier matching + operator re-ready note

## Goal

Two tracked fix-forwards from the worker-issuance lineage, closed together:

1. **Gap #1a — identifier-aware spawned-id lookup.** `reconcile`'s spawned-id
   validation (`_validate_spawned` → `board.fetch_issue_labels_by_ids`) resolves a
   worker's reported child ids against the board. Today the lookup uses Linear's
   `issues(filter: {id: {in: $ids}})` filter, which matches **UUID node ids only**.
   A worker that reports a child by its **human identifier** (`LIN-31` — the more
   natural thing to echo) gets that real, dispatchable child classified *invalid* →
   a false **escalate** on a `blocked` outcome, a misleading "claimed but not found"
   line on a `done`. After this plan, the lookup resolves **both** forms: UUID node
   ids in one batched read; human identifiers each via `issue(id:)` (which accepts
   both forms). A real agent-ready child reported by `LIN-31` validates as *valid*.
2. **Operator-doc note.** Document the operator-facing fact that a `blocked` /
   escalate / park terminal **leaves the ticket parked** (in `started`, or a
   configured `blocked` state) and **does not auto-resume** — a human must re-ready
   it (move it back to the ready state, or give a directive that drives a fresh
   terminal) — and that **any child `blocked_by` it stays undispatchable** until the
   parent reaches a `completed` state. Currently undocumented in DIRECTOR.md / the
   runbook.

Definition of done: the identifier-aware lookup + its mock mirror ship with unit
tests; the operator note lands in DIRECTOR.md (§4 + §12) and the runbook (§11); the
gate is GREEN; the always-on + standard review personas return SATISFIED.

## Context

- Originating gate: [reconcile-spawned-ticket-validation](../completed/2026-06-29-reconcile-spawned-ticket-validation.md)
  (gap #1) left both items as tracked fix-forward P2s — see its **Feedback** and the
  [tech-debt-tracker](../tech-debt-tracker.md) top row ("Worker ticket-issuance", §
  "Still OPEN: gap (1a) identifier-vs-node-id matching, and the operator-doc note").
- The lookup: `director/board/linear.py` `fetch_issue_labels_by_ids(ids) ->
  {id: [labels]}` (`:320`), query `_ISSUE_LABELS` (`:94`) = `issues(filter: {id: {in:
  $ids}})`. Linear's `IDComparator` (`id: {in:}`) matches the **UUID** node id; the
  human **identifier** (`LIN-31`) is not a filterable comparator on `IssueFilter`.
- The both-forms resolver already in the file: `read_issue` (`:187`) uses
  `issue(id: $id)` and its docstring says "by id/**identifier**" — Linear's single
  `issue(id:)` node query accepts BOTH a UUID and a human identifier. The
  `director.run --linear LIN-30` single-ticket path already passes identifiers to it
  in production. So resolving an identifier via `issue(id:)` is an existing,
  load-bearing, proven pattern in this very module — not a new external assumption.
- The caller: `orchestrator._validate_spawned` (`:139`) does
  `DISPATCH_LABEL in (labels.get(sid) or [])` and excludes `sid == parent_tid`
  (the node id). It is **total / fail-open** already — any read raise degrades to
  "trust the report, verified=False" (`:159-165`). The fix preserves that contract.
- The test `MockBoard.fetch_issue_labels_by_ids` (`orchestrator.py:1297`) looks up
  `self._issues` keyed by node id only, so it currently *also* conflates id and
  identifier (seeded children use `id == identifier`). To exercise the identifier
  path at the orchestrator level the mock must mirror the real both-forms resolution
  (match a reported id against an issue's node id OR its identifier).
- Operator docs: `.claude/DIRECTOR.md` §4 (answering a terminal `blocked`), §12 (the
  daemon's `idle`+`stuck` heartbeat — "the daemon will not make progress until **you**
  unblock it"), §13 (park). `docs/DIRECTOR_RUNBOOK.md` §11 (troubleshooting table).
  The strand-escalation signal (`🚷 stranded` + a `stranded`/`polls` status flag,
  from [poll-loop-strand-safety](../completed/2026-06-29-poll-loop-strand-safety.md))
  is the daemon's once-per-lifetime nudge that a parked subtree needs the human — it
  belongs in the same note.

## Approach (self-generated alternatives)

- **A: partition reported ids — UUID node ids → one batched filter read; everything
  else → a per-id `issue(id:)` resolve (chosen).** A UUID-shaped id keeps the existing
  one-POST batch (the common `issueCreate`-returns-node-id case stays a single read);
  a non-UUID id (a human identifier, the gap-#1a case) is resolved singly via the
  both-forms `issue(id:)` query. The map is keyed by the **exact reported string** so
  `_validate_spawned`'s `labels.get(sid)` works regardless of form. Tradeoff: N extra
  single POSTs when identifiers are reported — negligible for a control-path reconcile
  that runs on a handful of ids only when spawned ids are present.
- **B: GraphQL-alias a single query** (`i0: issue(id:"LIN-31"){…} i1: issue(id:…)`)
  to batch identifier resolves into one POST. Tradeoff: dynamic query-string
  construction with the ids interpolated into the document (not variables) — a
  string-built-query smell for a 1–3-id control path. Rejected: complexity/safety cost
  for no real latency win at this scale.
- **C: parse `LIN-31` → team-key + number and batch via `number: {in:}`.** Tradeoff:
  brittle (identifier parsing, team scoping, multi-team ambiguity) and needs the team
  id threaded into the lookup. Rejected.
- **Chosen: A** — minimal, reuses the proven both-forms `issue(id:)` resolver, keeps
  the common batch path single-POST, and degrades along the existing fail-open axis.

## Assumptions & open questions (self-interrogation)

- Assumption: a Linear issue node id is a **UUID** (`8-4-4-4-12` hex) and a human
  identifier is `TEAMKEY-NUMBER` (`^[A-Z][A-Z0-9]*-[0-9]+$`, uppercase team key). The
  two shapes are disjoint (a UUID never matches the identifier regex — it starts with
  a hex group, often a digit, and its post-dash groups carry letters). The router
  keys on the identifier shape: identifier-shaped → single resolve; everything else
  (UUIDs + fake/short test node ids like `u1`) → batch. — what breaks if wrong: a real
  node id mis-shaped as an identifier would route to single-resolve (still correct via
  `issue(id:)`, just not batched); a real identifier mis-shaped would route to the
  batch and read as "missing" (today's bug, unchanged for that id). Neither is a new
  failure mode; both resolve to the existing fail-open direction.
- Assumption: `issue(id:)` returns `{issue: null}` (no `errors`) for a clean
  not-found, so a hallucinated identifier resolves to "absent key ⇒ invalid" ⇒ the
  gap-#1 escalate still fires. If Linear instead **errors** on a not-found id, `_post`
  raises → `_validate_spawned` fail-opens (trusts the report, verified=False) for that
  reconcile — the **safe** direction (never a false escalate), consistent with the
  existing all-or-nothing fail-open posture. Documented as a residual; the *real-child*
  case (the gap's actual symptom) is fixed regardless, because an existing issue
  always returns `{issue: <obj>}`.
- Assumption: per-id error isolation is NOT wanted — a single identifier resolve that
  raises should propagate to `_validate_spawned`'s guard and fail-open the WHOLE
  validation (trust all reported ids), exactly as the existing batch-read failure
  does. Catching-and-marking-invalid per id would let a transport blip produce a false
  escalate, violating the codebase's "never falsely escalate a real worker" rule.
- Open: also exclude the parent's **identifier** (not just its node id) from the
  valid set? → resolved yes: a worker reporting its OWN identifier as a child is no
  more a real continuation than reporting its own node id; `_validate_spawned` already
  has the parent identifier available at the call site (`label`). Closes the
  self-reference hole symmetrically for both forms.
- Open: does the operator note belong in §4, §12, or §13? → resolved: a tight,
  self-contained statement in §4 (the terminal-blocked answer, where the operator
  *creates* the parked state) cross-linked from §12's stuck bullet (where they *read*
  it), plus a runbook §11 troubleshooting row (where they *act* on it). §13 (park)
  already covers the lights-out human-absent framing; link, don't duplicate.

## Milestones

- **M1 — identifier-aware spawned-id lookup.** In `director/board/linear.py`: add a
  single-issue label query `_ISSUE_LABELS_ONE` (`issue(id:){ id identifier labels{…} }`)
  + a tolerant helper `_fetch_one_issue_labels(rid) -> [labels] | None` (None on a
  clean `{issue: null}`; a transport/GraphQL error propagates). Rewrite
  `fetch_issue_labels_by_ids` to route reported ids: identifier-shaped
  (`_looks_like_identifier`, regex `^[A-Z][A-Z0-9]*-[0-9]+$`) → single resolve;
  everything else → the existing batched `_ISSUE_LABELS` filter; the result map is
  keyed by the **exact reported string**, absent when the board has no such issue, and
  an empty input still makes **no** POST. Mirror the both-forms resolution in the test
  `MockBoard.fetch_issue_labels_by_ids` (match a reported id against an issue's node id
  OR its identifier). In `orchestrator._validate_spawned`: take the parent
  **identifier** too and exclude a `sid` matching either the parent node id or its
  identifier; thread `label` through from both reconcile call sites. At the end: a
  worker reporting a real agent-ready child by `LIN-31` validates it as valid (no false
  escalate); reporting the parent's own identifier is excluded. Run
  `python3 -m unittest discover -s tests`; expect new tests green —
  `tests/test_director_linear.py`: identifier resolves via the single query, an
  identifier not-found is absent, an all-identifier input makes no batch call, the
  node-id batch path is unchanged; `tests/test_director_orchestrator.py`: a blocked
  claiming a real child **by identifier** stays blocked (was: false escalate), a
  parent-identifier self-spawn escalates.
- **M2 — operator re-ready note.** In `.claude/DIRECTOR.md`: extend §4's terminal
  bullet with a one-paragraph "a `blocked`/escalate parks the ticket; it does not
  auto-resume; re-ready it (or give a directive) to continue; children `blocked_by` it
  stay ineligible until it reaches a completed state" note, and extend §12's `idle`+
  `stuck` bullet to name those parked outcomes as the thing the human must re-ready
  and to read the `stranded` heartbeat flag (the daemon's once-per-lifetime
  `🚷 stranded` escalation). In `docs/DIRECTOR_RUNBOOK.md` §11: add a troubleshooting
  row ("ticket sits `blocked`/`escalated`/In-Progress and its children never dispatch
  → it's parked awaiting a human → re-ready it / answer its turn"). At the end: an
  operator reading either doc learns that a parked terminal needs a manual re-ready and
  why its subtree is stalled. No runnable surface → behavioral QA is N/A (docs only).

## Progress log
- [ ] (2026-06-29) Plan created; base_commit `e1c23c1`; gate GREEN.

## Surprises & discoveries
- (to fill as I work)

## Decision log
- 2026-06-29: Chose approach A (UUID→batch / identifier→single `issue(id:)`) over an
  aliased single-query batch (B) or identifier-number parsing (C) — reuses the proven
  both-forms `issue(id:)` resolver and keeps the common case a single POST.
- 2026-06-29: Per-id resolve errors propagate to the existing fail-open guard (no
  per-id catch) — preserves "never falsely escalate a real worker."
- 2026-06-29: Exclude the parent **identifier** as well as its node id from the valid
  set (symmetric self-reference guard).

## Feedback (from completion gate)
- (to fill at the gate)

## Outcomes & retrospective
- (to fill at completion)
