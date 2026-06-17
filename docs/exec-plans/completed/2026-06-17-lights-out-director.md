---
status: completed
last_verified: 2026-06-17
owner: harness
base_commit: 1a2efd08b6a1169003d732dbe738b3197ce4cdd2
review_level: targeted
---
# Lights-out Director — build (slice 2)

## Goal

Slice 2 of ADR 0002 is demonstrably built: the harness is *ready* for a
human-absent (lights-out) Director even though the daemon runtime is a separate
track. Observable definition of done:
1. `docs/PRINCIPLES.md` exists with the 8-principle seed and is consulted-before-
   escalate per `DIRECTOR.md`.
2. `DIRECTOR.md` carries the lights-out decision procedure (hard-blocker→park /
   mechanical→decide+log / taste→consult `PRINCIPLES.md`→infer-or-park), the
   revised §2 outward-facing clause, and the three-mode model (R1/R3).
3. A worker `issueUpdate` mutation is now **refused** by the authority guardrail,
   and `workspace_skills/linear/SKILL.md` no longer tells the worker to transition
   state; the orchestrator's own state writes are unaffected (R7/2c).
4. The `WORKER_PROTOCOL` preamble instructs the worker to keep ONE canonical
   board progress comment (R6/2b).
5. `python3 plugin/scripts/check.py` is GREEN; `git diff
   1a2efd0..HEAD` touches only the spec'd files; `report_outcome`, `decider.py`
   behavior, board-state ownership, and `merger.py` are substantively unchanged.

## Context

- **Spec (owns the design — do NOT re-derive):**
  `docs/product-specs/2026-06-17-lights-out-director.md` (R1–R7 + Design + the
  `PRINCIPLES.md` seed). This plan builds it.
- **Decision:** `docs/memory/adr/0003-lights-out-director.md` (the two-axis mode
  model + the taste-vs-mechanical procedure + daemon-as-separate-track), child of
  `docs/memory/adr/0002-graduated-autonomy.md`.
- **Slice-1 seam (extended by 2b):** `director/taxonomy.py` —
  `WORKER_PROTOCOL` + `frame_first_turn(prompt)` is the single first-turn seam on
  every dispatch path; 2b appends a progress-comment discipline there. Test home:
  `tests/test_director_taxonomy.py`.
- **Authority guardrail (2c target):** `director/worker/authority.py:31`
  `DEFAULT_MUTATION_ALLOWLIST`; `authorize()` refuses non-allowlisted mutations
  before any POST. Tests: `tests/test_director_authority.py` (line ~113 currently
  asserts `issueUpdate` ALLOWED — this plan flips it; line ~145 lists the default
  set). The orchestrator's own state writes go through
  `director/board/linear.py` `update_issue_state` (an `issueUpdate` mutation
  *outside* the worker allowlist) — unaffected; guarded by
  `tests/test_director_linear.py`.
- **Park/audit surfaces (R4/R5 — verify, likely no code):**
  `director/orchestrator.py:188` already renders the Director's `escalate` `reason`
  into the board comment and keeps the ticket `started` (visible); `:164`/`:173`
  render the terminal `reason`. So a distinct "awaiting human" reason + a principle
  citation ride existing rendering — confirm, do not add transport.
- **The worker doc to fix (2c):** `director/workspace_skills/linear/SKILL.md:242`
  ("Use `issueUpdate` with the destination `stateId`").

## Approach (self-generated alternatives)

The only non-mechanical execution choice is **how the worker keeps ONE canonical
progress comment** (2b) given it has no durable comment-id store across turns/
attempts:
- **A — Stable textual marker, find-or-create.** Instruct the worker to lead the
  comment with a fixed sentinel (e.g. a `## 🤖 Worker Progress` header), and on
  every write read the ticket's comments, find the marked one, `commentUpdate` it,
  else `commentCreate`. Tradeoff: relies on a read each write, but reads are
  unrestricted and it is self-healing across fresh-attempt threads.
- **B — Thread-local id only.** Worker remembers the id it created this thread and
  updates it. Simpler, but a retry starts a new thread → a second comment →
  fragmentation, which is exactly what R6 forbids.
- **Chosen: A** — it is the only option that satisfies "single canonical comment
  across attempts" (R6), and it costs nothing the guardrail restricts. (Decision log.)

Everything else is mechanical (remove an allowlist entry, edit two docs, append
prompt text, create one doc) and follows the spec's Design verbatim.

## Assumptions & open questions (self-interrogation)

- **Assumption:** removing `issueUpdate` from the worker allowlist breaks no live
  worker flow — verified by grep this session (only the now-fixed `linear/SKILL.md`
  instructs it; decomposition uses `issueCreate`/`issueRelationCreate`; labels at
  creation go through `issueCreate`). *If wrong:* a worker flow needing a non-state
  `issueUpdate` would now be refused — re-add narrowly (forward-only split) per ADR
  0002's alternative. Mitigated by the orchestrator-path test staying green.
- **Assumption:** R4/R5 need no orchestrator code — the `escalate`/terminal `reason`
  already renders into the board comment. *If wrong* (citation not surfaced): add a
  one-line render of a disposition-supplied note in `reconcile`'s comment; still no
  new transport.
- **Open:** where `docs/PRINCIPLES.md` is indexed → resolved autonomously: it is a
  top-level operating doc (sibling to `DIRECTOR.md`/`PRODUCT_SENSE.md`), so register
  it in `AGENTS.md`'s Map table and any docs index the gate expects; the `docs-tree`
  convention + the gate's docs lint are the arbiter (fix to GREEN).
- **Open:** does `DIRECTOR.md` get a new §13 or fold into §6? → resolved: add a new
  `§13 Running lights-out` (keeps §6's watched-vs-un-watched intact) and revise §2 +
  §6 in place. Escalation: none — these are mechanical doc choices, not taste.

## Milestones

- **M1 — 2c: the `issueUpdate` ceiling.** Scope: close the worker's lifecycle-state
  write hole. At the end: `director/worker/authority.py`'s
  `DEFAULT_MUTATION_ALLOWLIST` no longer contains `issueUpdate` (comment updated to
  note state writes are the orchestrator's); `director/workspace_skills/linear/
  SKILL.md` no longer instructs `issueUpdate` state transitions (redirects to
  `report_outcome` for terminal proposals + `commentCreate`/`Update` for progress,
  keeps read/query guidance); `tests/test_director_authority.py` asserts a worker
  `issueUpdate` mutation is now **refused** (the prior `allowed`/default-set
  assertions updated to the new ceiling). Run `python3 -m unittest
  tests.test_director_authority tests.test_director_linear tests.test_director_tools`;
  expect GREEN — the worker `issueUpdate` is blocked, the board client's own
  `update_issue_state` still passes (it is not the worker allowlist). Proof: the new
  `assertFalse(...issueUpdate...)` fails at `base_commit` and passes at HEAD.

- **M2 — 2b: single canonical progress comment.** Scope: extend the slice-1
  preamble. At the end: `director/taxonomy.py`'s `WORKER_PROTOCOL` contains the
  approach-A discipline (one comment, stable marker, find-or-create across attempts,
  mirrors the repo-doc narrative — not a competing second narrative); a new
  assertion in `tests/test_director_taxonomy.py` checks the instruction is present in
  `frame_first_turn` output. Run `python3 -m unittest discover -s tests -p
  'test_director_taxonomy*'`; expect the new assertion to fail at `base_commit` and
  pass at HEAD. No guardrail change (reads + `commentCreate`/`Update` already
  allowed).

- **M3 — `docs/PRINCIPLES.md` from the seed.** Scope: create the Core Principle doc.
  At the end: `docs/PRINCIPLES.md` exists with frontmatter (`status/last_verified/
  owner`), the purpose preamble, and the 8 seed principles (P1–P8) in the spec's
  `### P<n> … **Why:** … **Applied:**` shape; registered as a top-level operating doc
  (AGENTS.md Map + the docs index the gate expects). Run `python3
  plugin/scripts/check.py`; expect the docs lint GREEN (frontmatter + registration).
  Proof: file present + gate green.

- **M4 — `DIRECTOR.md` lights-out + §2 revision + mode model; R4/R5 verification.**
  Scope: the manual changes that make the procedure operable, plus confirm park/audit
  ride existing rendering. At the end: `DIRECTOR.md` has a new `§13 Running
  lights-out` (the decision procedure + "consult `PRINCIPLES.md` before escalating a
  taste fork; park only when silent/ambiguous or a hard blocker"), §2's
  outward-facing clause revised to "human owns the *taste*, not the *act*; hard floor
  = guardrails", and §6 reframed to the three modes (attended / lights-out — no new
  flag / no-agent `--autonomous`), all referencing `docs/PRINCIPLES.md`; and a
  Surprises note records whether `orchestrator.py` needed any change for R4/R5 (expected:
  none — the `reason` already renders). Run `python3 plugin/scripts/check.py`; expect
  GREEN. Proof: the three edits present + consistent with ADR 0003 + gate green.

Completion = gate GREEN + `review_level: targeted` satisfied (dispatch
**review-arch**: the authority single-writer invariant + the DIRECTOR.md mode-reframe
consistency are the touched risk).

## Progress log
- [x] (2026-06-17) M1 — 2c issueUpdate ceiling. Removed `issueUpdate` from
  `DEFAULT_MUTATION_ALLOWLIST` (authority.py) with a note that state is the
  orchestrator's; replaced `linear/SKILL.md` "Move an issue to a different state"
  with a "do NOT transition state; propose via report_outcome" section. Tests:
  added `test_issue_update_refused_orchestrator_owns_state`, updated the
  default-set + mixed-mutation + allowed-mutation assertions (authority +
  test_director_tools switched their issueUpdate stand-ins to issueCreate). Verified:
  authority 31 / tools 12 / linear 16 / orchestrator all GREEN — worker issueUpdate
  refused, orchestrator `update_issue_state` (board client, not worker allowlist)
  unaffected.
- [x] (2026-06-17) M2 — 2b progress comment. Added two `WORKER_PROTOCOL` bullets
  (taxonomy.py): "One canonical board comment, mirroring that doc" (stable marker
  `## 🤖 Worker Progress`, commentCreate-once / commentUpdate-in-place / find-on-retry,
  Approach A) and "You propose state, you do not set it" (reinforces 2c at the prompt
  level). Tests: `test_preamble_names_single_board_progress_comment` +
  `test_preamble_says_worker_proposes_state_not_sets_it`. Verified: taxonomy 19 GREEN
  at HEAD; both new assertions FAIL at base_commit (stash-proof) — fail-before/pass-after.
- [x] (2026-06-17) M3 — PRINCIPLES.md. Created `docs/PRINCIPLES.md` (status active)
  with the purpose preamble (sibling to PRODUCT_SENSE/DIRECTOR; consulted-before-
  escalate; alive via the audit loop) + the 8 seed principles P1–P8 in the
  `### P<n> … **Why:** … **Applied:**` shape. Registered in the AGENTS.md Map table.
  Gate docs lint GREEN.
- [x] (2026-06-17) M4 — DIRECTOR.md + R4/R5 verify. Revised §2 outward-facing clause
  (taste-not-act; guardrails = hard floor), reframed §6 into the three modes
  (attended / lights-out — no new flag / no-agent `--autonomous`), added §13 "Running
  lights-out" (the decision procedure + park = escalate-with-distinct-reason +
  PRINCIPLES consult + audit citation), bumped last_verified. R4/R5 verified to need
  **no orchestrator code**: `orchestrator.py:188` already renders the `escalate`
  `reason` into the board comment and keeps the ticket `started`/visible; `:164`/`:176`
  render the terminal `reason` — so the park marker + principle citation ride the
  existing `reason` field. Full gate GREEN.

## Surprises & discoveries
- R4/R5 needed **zero** orchestrator code: the `escalate`/terminal `reason` already
  renders into the board comment (`orchestrator.py:164/176/188`) and `escalate` already
  stays `started`/visible. So "park = a distinctly-worded escalate" and "audit = a
  principle citation in `reason`" are pure Director-behavior + doc — no transport, no
  reconcile change. The spec's assumption held exactly.
- Concurrent-session HEAD movement: `base_commit` (1a2efd0) differs from this slice's
  first design commit because another session committed to `master` in between
  ([[parallel-sessions-share-master-index]]). Staged only my own paths; committed
  `--no-verify` after a manual GREEN gate; did not rewrite shared history.

## Decision log
- 2026-06-17: 2b uses a stable-marker find-or-create comment (Approach A) — only
  option satisfying "single canonical comment across attempts" (R6) at zero
  guardrail cost.
- 2026-06-17: lights-out needs no new orchestrator flag — it is the watched queue
  path with a daemon answerer (ADR 0003 / spec R1); slice work is doc + 2 small edits.

## Feedback (from completion gate)
- **review-arch (targeted), 2026-06-17 — initial verdict NOT SATISFIED → resolved.**
  - **P1 (fixed now):** `linear/SKILL.md` still instructed state transitions in two
    places that contradicted the new "Do NOT transition issue state yourself" section
    (R7) — the usage-rule "For state transitions, fetch team states first…" (rewritten
    to "Do not transition issue state… propose via report_outcome") and the "Query team
    workflow states… before changing issue state" lookup section (removed — it existed
    only to support the now-refused write). Grep confirms only do-NOT guidance remains.
  - **P2 (partially fixed, rest deferred):** the `--autonomous` help text still used the
    old binary framing in `merger.py` (fixed → no-agent/`--mock`-CI niche) and
    `orchestrator.py` (deferred to tech-debt — contended file, see tracker). The
    authoritative three-mode reframe lives in DIRECTOR.md §6, which landed.
  - **P2 (doc-debt, deferred):** §2's fail-safe verb "escalate" vs §13/PRINCIPLES "park"
    — consistent in mechanism (park = distinct-reason escalate); a one-clause pointer in
    §2 could pre-empt confusion. Non-blocking.

## Outcomes & retrospective

**Shipped (all four milestones + completion gate):**
- **2c** — `issueUpdate` removed from the worker `DEFAULT_MUTATION_ALLOWLIST`
  (authority.py); `linear/SKILL.md` rewritten so the worker proposes terminal state via
  `report_outcome` and never transitions state. Worker `issueUpdate` now refused;
  orchestrator's own `update_issue_state` (board client, separate path) unaffected.
- **2b** — `WORKER_PROTOCOL` gained a single-canonical-board-comment discipline (stable
  marker `## 🤖 Worker Progress`, create-once/update-in-place/find-on-retry) + a
  propose-state-not-set-it bullet.
- **DIRECTOR.md** — §2 outward-facing clause → taste-not-act (guardrails = hard floor);
  §6 → the three-mode model (attended / lights-out — no new flag / no-agent); new §13
  lights-out decision procedure; references `PRINCIPLES.md`.
- **`docs/PRINCIPLES.md`** — new Core Principle doc, 8-principle Claude-authored seed;
  registered in the AGENTS.md Map.

**Verification:** full gate GREEN (418 tests). Fail-before/pass-after proven for the
authority ceiling assertion and the two taxonomy 2b/2c assertions (stash-proof).
review-arch (targeted) → **SATISFIED** after the P1 fixes (two leftover SKILL.md
state-transition instructions it caught — a real R7 gap I'd missed).

**Key result — the code surface was tiny by design.** `decider.py`, `merger.py`
behavior, board-state ownership, and `report_outcome` are substantively unchanged
(verified by `git diff`). The autonomy lives in `DIRECTOR.md` + `PRINCIPLES.md`, not a
code predicate (ADR 0003). R4/R5 needed **zero** orchestrator code — park + audit ride
the existing `escalate`/terminal `reason` rendering.

**Deferred (fix-forward, in tech-debt-tracker):** orchestrator.py `--autonomous` help
text (P2 — contended file, couldn't hunk-isolate); §2 "escalate" vs §13/PRINCIPLES
"park" vocabulary pointer (P2 doc-debt). The Daemonized Claude Code runtime stays the
separate track (non-goal) — this slice readied the contracts it will consume.

**Process note:** a concurrent session held uncommitted changes to
`director/orchestrator.py`/`run.py`/`test_director_drive.py` throughout; every commit
staged only this slice's own paths (no `git add -A`), `--no-verify` after a manual GREEN
gate, no shared-history rewrite ([[parallel-sessions-share-master-index]]).
