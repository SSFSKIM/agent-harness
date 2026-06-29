---
status: completed
last_verified: 2026-06-29
owner: harness
type: exec-plan
description: Make orchestrator.reconcile verify a worker's reported spawned_ticket_ids against the board (exists + carries agent-ready + not self) so a failed/refused/hallucinated issueCreate can no longer park a ticket with a false "children filed" audit trail — a blocked outcome whose claimed children are not real/dispatchable is surfaced as an escalate instead of silently stranded.
base_commit: 0bb384869835172ef2e810941f06f44b1f3c7598
review_level: standard
---
# Reconcile validates worker-reported spawned_ticket_ids

## Goal

After this plan, `orchestrator.reconcile` no longer trusts a worker's
`report_outcome(spawned_ticket_ids=[…])` as opaque strings. On a terminal outcome
that carries spawned ids, it **reads the board** and partitions the ids into
*valid* (the ticket exists, carries the `agent-ready` dispatch label, and is not the
parent itself) vs *invalid* (missing / unlabeled / self-referential). Two observable
consequences:

1. **No false audit trail.** A board comment or run summary never claims a child
   exists that the board does not have. Invalid ids are surfaced explicitly
   ("claimed but not found/not agent-ready: …") on both the `done` and `blocked`
   paths.
2. **A childless `blocked` is surfaced, not silently parked.** When a worker reports
   `blocked` and *none* of its claimed children are valid/dispatchable (the
   silent-strand-with-false-audit-trail case — a failed/refused/hallucinated
   `issueCreate`), reconcile downgrades the outcome to **escalate** (visible to the
   human) instead of parking the ticket `blocked` with a fake continuation.

Definition of done: the new board lookup + the reconcile validation ship with unit
tests, the gate is GREEN, and the always-on + standard review personas return
SATISFIED.

## Context

- Originating review: the worker-behavior policy review (2026-06-29) + its
  independent Opus corroboration. Findings recorded in
  [tech-debt-tracker](../tech-debt-tracker.md) (top row, "Worker ticket-issuance").
  The **steering** half (a worker mistakenly choosing `blocked` for a decomposition)
  was already fixed in the contract (`director/taxonomy.py`, commit `0bb3848`); this
  plan fixes **mechanism gap #1** — reconcile trusting spawned ids blindly.
- The mechanism: a worker creates child tickets via the `linear_graphql` tool bounded
  by `director/worker/authority.py` (`issueCreate`/`issueRelationCreate` allowlisted),
  and reports them via `report_outcome` (`director/worker/tools.py`,
  `spawned_ticket_ids`). `orchestrator.reconcile` (`director/orchestrator.py:182-246`)
  executes the terminal outcome onto the board. Today it only string-joins the ids into
  a comment (`:192-193`, `:230-237`) — no board read, no existence/label check.
- The dispatch gate that makes an unlabeled child undispatchable:
  `orchestrator.eligible_tickets(require_label=True)` drops tickets lacking
  `DISPATCH_LABEL = "agent-ready"` (`orchestrator.py:310-325`); `dispatch_requires_label`
  defaults `True` (`director/config.py`). So a spawned child that is missing,
  unlabeled, or is the parent itself never actually runs — yet today it is reported as
  a real follow-up.
- Board client: `director/board/linear.py`. The by-ids read `fetch_issue_states_by_ids`
  (`:285`, query `_ISSUE_STATES` `:86`) is the shape to mirror — it already does
  `issues(filter: {id: {in: $ids}})`. It returns state only; this plan adds a sibling
  that returns labels. `_parse_labels` (`:218`) already extracts `labels{nodes{name}}`.
- Boundary preserved: reconcile board writes are **best-effort** (a failed read/write is
  recorded in the summary `errs`, never raised — `:157-172`). The new board read follows
  the same total-function discipline (RELIABILITY R12): on any read failure it degrades
  to "could not verify" (treat as before — surface, do not crash the reconcile).
- Out of scope (linked follow-up, tracked): mechanism gap #2 (default `blocked: None`
  → orphan-reattach re-runs the parent on restart → duplicate children) and gap #3
  (daemon strand-age escalation). Those live in the **poll loop**, a different
  subsystem (PLANS.md scope-check → separate plan). This plan closes only the
  reconcile-boundary gap.

## Approach (self-generated alternatives)

- **A: Reconcile reads the board to verify spawned ids (chosen).** Add a by-ids label
  lookup to the board client; in reconcile, partition spawned ids into valid/invalid;
  surface invalid honestly; downgrade a no-valid-children `blocked` to escalate.
  Tradeoff: one extra board read per terminal-with-spawned-ids (cheap — only fires when
  spawned ids are present, which is the minority of terminals), and the validation runs
  in reconcile (already the board-transition authority — the right home).
- **B: Validate at worker `report_outcome` time** (in `tools.py`'s executor, when the
  worker calls the tool). Tradeoff: the executor runs inside the worker drive loop with
  the worker's own (guarded) Linear tool — it would couple the terminal-signal capture
  to a network read and muddy the clean "worker proposes, orchestrator executes"
  seam (D-40). Rejected: validation is an *orchestrator* responsibility, not the
  worker's self-report.
- **C: Have the daemon poll reconcile spawned ids asynchronously** (a board-sweep that
  checks each parked ticket's claimed children). Tradeoff: more moving parts, delayed
  detection, and it belongs to the gap-#3 strand-escalation subsystem. Rejected for
  this plan: heavier and out of the reconcile boundary.
- **Chosen: A** — the validation belongs where the board transition is decided
  (reconcile), it is the minimal surface that closes the false-audit-trail, and it is
  synchronous (the human sees the right outcome immediately).

## Assumptions & open questions (self-interrogation)

- Assumption: a worker reports spawned ids as Linear node **ids** (what `issueCreate`
  returns), and the board's `issues(filter:{id:{in:…}})` matches on those ids. If a
  worker instead reports a human **identifier** (e.g. `LIN-31`), the filter may not
  match and the id reads as "missing" → treated invalid. Mitigation: the lookup will
  match on node id; an identifier-only report degrades to "could not verify" surfacing,
  never a crash. (Noted as a known edge; the contract tells the worker to report the
  created id.) — what breaks if wrong: a real child reported by identifier is flagged
  invalid → a false escalate. Acceptable failure direction (surfacing > silent strand);
  revisit if observed live.
- Assumption: an empty `spawned_ticket_ids` on a `blocked` outcome is a *legitimate*
  "I'm genuinely stuck, no children" — NOT a strand to escalate. Only a `blocked` that
  *claims* children (non-empty list) but has none valid is the false-audit case. So the
  escalate-downgrade fires only when `spawned` is non-empty AND zero are valid. — what
  breaks if wrong: scope creep into "should every childless blocked escalate?" which is
  gap #3's territory; kept out deliberately.
- Open: should a `blocked` with *some* valid + *some* invalid children escalate, or stay
  blocked? → resolved autonomously: stay `blocked` (it has ≥1 real dispatchable child,
  so the continuation is real) but surface the invalid ids in the comment. Escalate only
  on **zero** valid.
- Open: validate spawned ids on the `done` path too? → resolved: yes for the **audit**
  (surface invalid ids honestly) but NEVER change the `done`/`merging` transition — a
  `done` ticket's primary work is complete regardless of a follow-up's validity. The
  escalate-downgrade is `blocked`-only.
- Assumption: `read_timeout`/board errors must not turn a real terminal into a crash.
  The lookup is a total function (None/empty on failure); on "could not verify" reconcile
  behaves as today (surface the ids as reported, unverified) — no new failure mode.

## Milestones

- **M1 — board by-ids label lookup.** Add `fetch_issue_labels_by_ids(ids) ->
  {id: [label_names]}` to `director/board/linear.py` (a module function + a `LinearBoard`
  method), backed by a new query mirroring `_ISSUE_STATES` but selecting
  `labels { nodes { name } }` (+ `identifier`). Only ids the board actually returns
  appear in the map, so a **missing id ⇒ absent key ⇒ does not exist**. Empty input →
  `{}` (no POST), matching the existing empty-guard convention. Add the method to the
  test `MockBoard` (look up its own seeded issues by id, return their `labels`). At the
  end: the board client and the mock can answer "for these ids, which exist and what
  labels does each carry." Run `python3 -m unittest discover -s tests`; expect new
  label-lookup tests in `tests/test_director_linear.py` green (the 4 scenarios:
  exists+multiple+no-labels, missing, empty).
- **M2 — reconcile validates spawned ids.** In `reconcile`'s terminal branch, add a
  helper that, given the reported `spawned_ticket_ids`, calls the M1 lookup and returns
  `(valid, invalid)` where valid = exists AND `agent-ready` in its labels AND id != this
  ticket's id. Then: (done path) keep the `done`/`merging` transition unchanged but make
  the comment/summary surface valid vs invalid ids honestly; (blocked path) if `spawned`
  is non-empty and **zero** are valid → emit an **escalate** outcome (comment "escalated:
  worker reported blocked but no valid agent-ready child exists (claimed: …)", summary
  status `escalated`, stay visible) instead of setting `blocked`; otherwise set
  `blocked`/stay-started as today but surface any invalid ids. The lookup is best-effort:
  a board-read failure degrades to "unverified" (today's behavior) and is recorded in
  `errs`. At the end: a fabricated/missing spawned id on a `blocked` outcome produces an
  `escalated` summary, not a silent `blocked`; a `done` with an invalid follow-up id
  still completes but names the invalid id. Run the suite; expect new reconcile-validation
  tests green: (a) valid agent-ready child → blocked kept, child listed; (b) non-empty
  spawned, none valid → escalated; (c) done with an invalid id → final_state done/merging
  + invalid surfaced; (d) board-read failure → unverified, no crash, errs recorded.

## Progress log
- [x] (2026-06-29) Plan created (`bd35d9b`); base_commit `0bb3848`; gate GREEN.
- [x] (2026-06-29) M1 — `fetch_issue_labels_by_ids` (module fn + `LinearBoard` method,
  query `_ISSUE_LABELS`) + `MockBoard.fetch_issue_labels_by_ids`; 3 new board test methods
  covering the 4 scenarios (exists+multiple+no-labels / missing / empty) in
  `tests/test_director_linear.py` (25 green).
- [x] (2026-06-29) M2 — `reconcile` helpers `_validate_spawned`/`_follow_note`/
  `_spawned_summary`; done path surfaces valid vs invalid honestly (transition
  unchanged); blocked path with a non-empty-but-zero-valid claim downgrades to escalate;
  best-effort board read (fail-open + `reconcile_error`). 7 new reconcile tests + 2 done
  tests reseeded with valid children. Full suite green (149 orchestrator+board); gate GREEN.
- [x] (2026-06-29) Completion gate: gate GREEN; self-review done; behavioral acceptance =
  fixture-level reconcile tests (the mock board exercises the path end-to-end); live worker
  dogfood deferred (codex CLI unavailable in-env). All 4 personas SATISFIED, 0 P1
  (spec-compliance, code-quality, review-arch, review-reliability).
- [x] (2026-06-29) Post-review inline fixes: hardened `_validate_spawned` (partition loop
  inside the try → total even on a non-dict board response); dropped the unused `identifier`
  query field; added the done-path fail-open test; fixed two plan-text nits. 150 tests green;
  gate GREEN. Remaining P2s tracked fix-forward (see Feedback + tech-debt-tracker).

## Surprises & discoveries
- `summary["spawned_ticket_ids"]` has **no downstream logic consumer** (grepped
  status/dashboard/watch) — it is observability-only — so re-meaning it as "the REAL
  (valid) follow-ups" is safe; invalid ids go in a new `spawned_invalid` field (present
  only when non-empty). Two existing done tests asserted unverified ids in
  `spawned_ticket_ids`; reseeded them with real agent-ready children (the validated path).
- Escalate-downgrade is deliberately narrow: fires only on `blocked` with a **non-empty**
  claim where **zero** ids are valid AND the board read **succeeded**. Empty claim → plain
  blocked; partially-valid → blocked (has a real child); board-read failure → trust the
  report (no false escalate on unverifiable data).

## Decision log
- 2026-06-29: Chose approach A (validate in reconcile) over worker-side (B) or
  daemon-sweep (C) — validation is the orchestrator's board-transition responsibility,
  synchronous, and minimal.
- 2026-06-29: Escalate-downgrade fires only on a `blocked` with non-empty spawned ids
  and zero valid — an empty list stays a legitimate plain `blocked`; a partially-valid
  list stays `blocked` with the invalid ids surfaced. `done` transitions never change.
- 2026-06-29: Scoped gap #2 (duplicate-on-restart) and gap #3 (daemon strand escalation)
  OUT — different subsystem (poll loop); linked follow-up in the tracker.

## Feedback (from completion gate)

All four personas **SATISFIED**, zero P1.

**Fixed inline (P2):**
- review-reliability — `_validate_spawned`'s partition loop ran outside the try/except, so a
  board adapter returning a non-dict (vs raising) could throw out of reconcile; moved the loop
  inside the guard so the whole verify path is total (fail-open on any failure).
- review-code-quality — `_ISSUE_LABELS` selected an unused `identifier`; dropped it (nothing
  speculative). Added `test_done_spawned_verify_board_error_trusts_report` to close the
  fail-open matrix (was blocked-only).
- review-spec-compliance — two plan-text nits (test count + module name) corrected above.

**Tracked fix-forward (tech-debt-tracker):**
- **Identifier-vs-node-id matching** (review-arch P2 + code-quality note + this plan's
  Assumptions): the lookup filters by Linear node id, so a worker reporting a human identifier
  (`LIN-31`) gets every real child classed invalid → a false escalate on blocked, a misleading
  "not found" line on done. Only bites a contract-noncompliant worker (the contract mandates
  the `issueCreate`-returned id); safe direction (surfacing > silent strand). Fix = an
  identifier-aware lookup.
- **Escalate-downgrade ↔ orphan-reattach (gap #2 sharpening)** (review-reliability +
  review-arch): in a `blocked`-CONFIGURED deployment the downgrade leaves the ticket in
  `started` (was: parked in `blocked`, which orphan-reattach ignores), so a daemon restart
  re-dispatches it — a new entry into gap #2's duplicate-on-restart path.
- **Two proposed RELIABILITY.md rules** (doc-gardener): (a) a control-path board READ newly
  inserted into reconcile's terminal-transition path must be total AND fail-open to prior
  behavior (never a stricter verdict on a read failure); (b) a code-synthesized escalate
  inherits the `started`/restart-redispatchable lifecycle — a human-bound terminal needs a
  parked state or restart-idempotency (anchors the deferred gap #2 work).

**Accepted as-is (taste):**
- review-code-quality — `_validate_spawned` returns a dict the two formatters unpack
  positionally; a defensible decoupling. Left as-is.

## Outcomes & retrospective

Shipped: `fetch_issue_labels_by_ids` (board by-ids label lookup) + reconcile spawned-id
validation. A worker's reported `spawned_ticket_ids` are now verified against the board
(exists + `agent-ready` + not self); a `blocked` whose claimed children are all invalid is
surfaced as an **escalate** instead of a silent strand with a false audit trail, and both the
`done` and `blocked` comments/summaries name real vs claimed-but-not-real ids honestly. The
`done` transition is unchanged; the board read is fail-open (a read failure trusts the report,
records `reconcile_error`, never a false escalate). Closes mechanism gap #1 from the
worker-behavior review.

Scope held: gaps #2 (duplicate-on-restart) and #3 (daemon strand-escalation) stay deferred to
a poll-loop follow-up; the gate sharpened gap #2 (the escalate-downgrade is a new entry into
its restart path). 12 new tests; full suite + gate GREEN; all four review personas SATISFIED.

Retrospective: the four-persona panel earned its keep — review-reliability caught the
loop-outside-try totality gap, and arch + code-quality converged on the `identifier` field from
opposite directions, resolving to "drop now, track identifier-aware matching." The cleanest
insight: re-meaning an observability-only summary field (`spawned_ticket_ids` → valid-only,
+ `spawned_invalid`) was safe precisely because it had no structured consumer — verified by
grep before relying on it.
