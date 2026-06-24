---
status: active
last_verified: 2026-06-25
owner: harness
type: exec-plan
description: Realign the worker prompt policy (director/taxonomy.py) with ADR 0004 — a ticket carries the whole pipeline within it, decomposition is the exception (two triggers), every issued ticket is self-contained — and land the two Symphony WORKFLOW.md parity divergences (sync-before-work, rework-reset).
base_commit: f5b5280
review_level: targeted
---
# Ticket = purpose unit — worker-policy realignment + two parity divergences

## Goal
The worker prompt policy in `director/taxonomy.py` encodes
[ADR 0004](../../adr/0004-ticket-purpose-unit.md): a ticket is a **purpose unit**
whose worker walks the whole research→spec→plan→exec→QA pipeline *within it* and
spawns a child ticket only on (1) a genuine size split or (2) surfaced deferred
work; every ticket a worker issues is **self-contained** (provenance + title +
description + acceptance). Plus the two Symphony `WORKFLOW.md` gap-#5 divergences
the parity review surfaced: **sync-before-work** and **rework-reset**.

Observable definition of done: (a) `taxonomy.WORKER_PROTOCOL` states the
two-trigger issuance rule and the self-contained-ticket contract (covering in-scope
deferred work, not only out-of-scope); (b) `_SPEC_TEMPLATE` and `_DESIGN_TEMPLATE`
no longer *unconditionally* hand off to child tickets — they continue the pipeline
in the same ticket and create children only on a genuine size split, mirroring
`_IMPL_TEMPLATE`'s existing "only if the work is too large for one plan" conditional;
(c) `_IMPL_TEMPLATE` instructs sync-to-`origin/main`-before-substantial-work (with
recorded evidence) and approach-wrong rework reset; (d) `tests/test_director_taxonomy.py`
asserts each of the above and the existing regression net (untyped raw prompt,
`with_terminal_contract`, framed first-turn = WORKER_PROTOCOL + TERMINAL_CONTRACT)
stays green; (e) `python3 plugin/scripts/check.py` is GREEN.

## Context
- **Decision:** [ADR 0004 — ticket = purpose unit](../../adr/0004-ticket-purpose-unit.md)
  owns the *what* and *why* (revises dev-stage-taxonomy D-18/D-20; realigns with
  [ADR 0001 recursive-decomposition](../../adr/0001-recursive-decomposition.md)).
  This plan owns the *build* — do not re-derive the decision here.
- **Source review:** the Symphony-parity worker-policy review
  (`docs/design-docs/symphony-parity-gap.md` gap #5;
  `docs/symphony-original/WORKFLOW.md` is the original manual). It found: the worker
  protocol is consumer-complete but producer-thin; `_SPEC_TEMPLATE` forces a spec→impl
  hand-off the methodology never asked for; and two `WORKFLOW.md` disciplines were never
  harvested — sync-before-work (Step 1.9/2.1) and rework-as-reset (Step 4).
- **Where the policy lives:** `director/taxonomy.py`. The five stage templates
  (`_PLANNING/_RESEARCH/_DESIGN/_SPEC/_IMPL_TEMPLATE`), the stage-agnostic
  `WORKER_PROTOCOL` (the no-scope-creep bullet is the one this plan rewrites), the
  `TERMINAL_CONTRACT`, and `frame_first_turn` (the single injection seam in
  `director/run.py` `drive`). The worker's ticket body is just
  `f"{identifier}: {title}\n\n{desc}"` (`director/board/linear.py:175`), so the only
  lever on "self-contained tickets" is what the *issuing* worker writes — exactly what
  the contract addresses.
- **The pattern to copy:** `_IMPL_TEMPLATE` already obeys ADR 0004 — *"Split off
  additional impl child tickets ... only if the work is too large for one plan."*
  M2 makes `_SPEC_TEMPLATE`/`_DESIGN_TEMPLATE` symmetrical.
- **Methodology grounding the templates point at:** `plugin/skills/product-design/SKILL.md`
  (scope check: split only on independently shippable subsystems) and
  `plugin/skills/execplan/SKILL.md`; `docs/PLANS.md` "Scope check".
- **Memory:** [[parallel-sessions-share-master-index]] — stage only this plan's own
  paths at commit.

## Approach (self-generated alternatives)
- **A — Prompt-text only.** Rewrite the `WORKER_PROTOCOL` no-scope-creep bullet into
  the issuance contract, make `_SPEC_/_DESIGN_TEMPLATE` size-gated like `_IMPL_`, add
  the two impl disciplines, update the taxonomy tests. Tradeoff: smallest possible
  surface, no registry/orchestrator change, consistent with the proven "policy =
  prompt text" mechanism; keeps the five types as start-points (ADR 0004 "no type
  removed"). Cost: must update the existing tests that assert *mandatory* child
  creation to assert the *conditional* form (an intended behavior change, not a
  regression).
- **B — New `feature`/`dev` type carrying the whole pipeline + deprecate the spec/impl
  split.** Tradeoff: most "honest" to the purpose-unit model, but it changes the type
  registry, the `_PRIORITY` resolution, and risks backward-compat with existing typed
  tickets and `ticket_type`; far larger blast radius for no behavior the prose change in
  A doesn't already deliver. ADR 0004 explicitly says "no taxonomy type removed."
- **Chosen: A.** Surgical, matches the ADR's stated consequences, and the `_IMPL_TEMPLATE`
  conditional already proves the shape works. (Mirrored in Decision log.)

## Assumptions & open questions (self-interrogation)
- Assumption: the existing `tests/test_director_taxonomy.py` asserts `_SPEC_TEMPLATE`
  contains an "create impl child" instruction (dev-stage-taxonomy R3). What breaks if
  wrong: M2's test edit is a no-op rather than an update. Mitigation: M2 reads the test
  first and adapts the exact assertion; either way the *new* conditional-form assertion
  is added.
- Assumption: prose-only changes to first-turn framing need no orchestrator/run.py
  change — `frame_first_turn` already injects `WORKER_PROTOCOL` at the single seam, and
  the templates are formatted in `compose_worker_prompt`. What breaks if wrong: an
  injection path misses the new text. Mitigation: the existing R1 test (framed prompt
  contains WORKER_PROTOCOL) covers the seam; no seam change is made.
- Assumption: "self-contained ticket" is enforced by *prompt instruction*, not by a
  schema/validation on the linear tool. ADR 0004 scopes this as policy text; a
  programmatic check on issued-ticket shape is out of scope (would belong with the
  linear skill / a future lint). Recorded, not built.
- Open: keep the board-comment-mirror and propose-don't-set bullets in WORKER_PROTOCOL
  untouched? → resolved YES — they are slice-2 (ADR 0002/0003) disciplines orthogonal to
  issuance; only the no-scope-creep bullet changes.
- Open: does "sync-before-work" name the `pull` skill or describe the action? → resolved:
  name the `pull` skill (workspace skills are vendored into the worker; `WORKFLOW.md`
  Step 1.9 references the same `pull` skill) AND describe the recorded-evidence outcome,
  so it works whether or not the skill name resolves.

## Milestones
- **M1 — WORKER_PROTOCOL: two-trigger self-contained issuance contract.** Replace the
  `WORKER_PROTOCOL` "No scope-creep" bullet with the issuance contract: a worker creates
  a *new* ticket on exactly two triggers — (1) genuine size split (work divides into
  independently shippable sub-projects/slices, each its own spec→ExecPlan, `blocked_by`
  this one) and (2) surfaced deferred work (out-of-scope, **or** in-scope tech debt /
  additional production tests / hardening whose inline fix would break momentum) — and
  otherwise stays on the current ticket; and every ticket it issues is self-contained
  (provenance: link to this parent + the source doc it derives from; a clear title; a
  description; acceptance criteria). At the end the bullet reads as the contract. Run
  `python3 -m unittest tests.test_director_taxonomy -v`; expect new assertions green —
  WORKER_PROTOCOL contains the two-trigger language, "acceptance criteria", "tech debt",
  and a provenance/link phrase.
- **M2 — `_SPEC_TEMPLATE` + `_DESIGN_TEMPLATE`: continue the pipeline in-ticket.** Rewrite
  `_SPEC_TEMPLATE` so the spec worker, after writing the product-spec, **continues into
  the ExecPlan + implementation + QA in the same ticket** when the build is one coherent
  unit, and creates `spec`/`impl` child tickets **only** when the work genuinely splits
  into independently shippable sub-projects (citing the product-design scope check) —
  the same conditional `_IMPL_TEMPLATE` already uses. Align `_DESIGN_TEMPLATE` the same
  way (design → continue to spec/build in-ticket unless it splits). Update the existing
  taxonomy test(s) that assert *mandatory* child creation to assert the *conditional*
  form, and add an assertion that the unconditional "Then create impl child tickets"
  wording is gone. At the end the spec/design templates are size-gated. Run
  `python3 -m unittest tests.test_director_taxonomy -v`; expect green.
- **M3 — `_IMPL_TEMPLATE`: sync-before-work + rework-reset.** Add two disciplines:
  (a) **sync-before-work** — before substantial implementation, sync the working base to
  `origin/main` (the `pull` skill) and record the sync result (source, clean/conflicts,
  resulting HEAD) in the ExecPlan Notes, so a stale base does not surface conflicts late
  in the PR-feedback sweep; (b) **rework-reset** — when the ticket returns because the
  *approach* was wrong (a reviewer/human rejected the direction, not incremental line
  feedback), reset rather than patch: close the existing PR, branch fresh from
  `origin/main`, and write a fresh plan; reserve the on-arrival PR-feedback sweep for
  incremental feedback. At the end `_IMPL_TEMPLATE` carries both. Run
  `python3 -m unittest tests.test_director_taxonomy -v`; expect green (assertions for an
  `origin/main`/sync phrase and a "rework"/"approach"/"fresh branch" phrase).
- **M4 — Docstring + completion gate.** Update the `director/taxonomy.py` module docstring
  to state the purpose-unit framing (ticket carries the pipeline; decomposition is the
  exception; issuance is self-contained) and cite ADR 0004. Run `python3 plugin/scripts/check.py`;
  expect GREEN. Behavioral check: **N/A** — the deliverable is worker prompt *text* with no
  runnable surface; its "behavior" is prompt content, fully asserted by the M1–M3 unit
  tests (recorded N/A + why, per PLANS.md). Self-review the diff vs `base_commit`. Dispatch
  always-on **review-spec-compliance** → **review-code-quality**; targeted risk persona
  **review-arch** (this revises decomposition architecture / D-20). Process P1 (fix + rerun
  gate) / P2 (Feedback + tech-debt-tracker). All SATISFIED → Outcomes, `status: completed`,
  `git mv` to `completed/`, commit.

## Progress log
- [x] (2026-06-25) Plan created; base_commit f5b5280; review_level targeted. ADR 0004 committed (f5b5280).
- [x] (2026-06-25) M1 — WORKER_PROTOCOL no-scope-creep bullet → two-trigger self-contained
  issuance contract (genuine size split / surfaced deferred work incl. in-scope tech debt;
  provenance + title + description + acceptance). New test `test_preamble_states_two_trigger_self_contained_issuance`.
- [x] (2026-06-25) M2 — `_SPEC_TEMPLATE` + `_DESIGN_TEMPLATE` continue the pipeline in-ticket;
  children only on a genuine size split (mirrors `_IMPL_TEMPLATE`). Updated the stale
  "decomposes into impl children" comment; new tests `test_spec_prompt_continues_in_ticket_not_mandatory_handoff`
  + `test_design_prompt_continues_in_ticket`.
- [x] (2026-06-25) M3 — `_IMPL_TEMPLATE` rework path split (incremental sweep vs approach-reset:
  close PR / fresh branch / fresh plan) + sync-before-work (`pull` to origin/main, recorded
  evidence). New test `test_impl_prompt_syncs_base_and_resets_on_wrong_approach`.
- [x] (2026-06-25) M4 — module docstring states the purpose-unit framing + ADR 0004. Full gate
  GREEN (790 tests, +4). Taxonomy suite 26 green.

## Surprises & discoveries
- (2026-06-25) `_SPEC_TEMPLATE` is a plain triple-quoted string (literal newlines), unlike
  `WORKER_PROTOCOL` which uses `\`-continuations — so "independently shippable" wrapped across a
  line and a naive substring assertion failed. Reflowed the line so the phrase stays intact
  (the rendered prompt is unaffected; the assertion is now line-robust).

## Decision log
- 2026-06-25: Approach A (prompt-text only) over a new pipeline-carrying type (B) — ADR 0004
  keeps the five types as start-points; `_IMPL_TEMPLATE`'s existing conditional proves the shape.
- 2026-06-25: sync-before-work names the `pull` skill AND the recorded-evidence outcome, so it
  works whether or not the skill name resolves in the workspace (matches WORKFLOW.md Step 1.9).

## Feedback (from completion gate)

## Outcomes & retrospective
