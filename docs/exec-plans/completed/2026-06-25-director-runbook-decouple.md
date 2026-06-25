---
status: completed
last_verified: 2026-06-25
owner: harness
type: exec-plan
description: Extract a command-first Director prod-run runbook (docs/DIRECTOR_RUNBOOK.md), decouple DIRECTOR.md to a pure behavioral guide, and prove the runbook with a real codex single-ticket run through the full loop.
base_commit: dcb3d08f026b5c2d35e944bf59968399a3372c74
review_level: targeted
---
# Director prod-run runbook + DIRECTOR.md decoupling

## Goal
A reader (human or a fresh Director session) can go from **zero to a bounded live
prod run** by following **one** command-first runbook — `docs/DIRECTOR_RUNBOOK.md` —
without exploring code, grepping CLI flags, or relying on a stale memory file. The
runbook covers the full operating loop end-to-end: stand-up (prereqs, secrets, the
disposable-repo safe fence), the cheap single-ticket validation (`director.run
--linear`), the watched orchestrator + operator console, and the merger land + cleanup.
`.claude/DIRECTOR.md` is decoupled to a **pure behavioral guide** (Identity + the
taste-vs-handle judgment + answering turn/merge reviews + lights-out) that *points to*
the runbook for "what to type", carrying no stand-up/launch command blocks of its own.
**Definition of done, observable:** (1) a person following only the runbook lands a
real PR on a disposable shakedown repo via a codex worker run (dispatch → turnReview →
PR → merger squash-land), with the new per-ticket drill-down observed live on the
dashboard; (2) `DIRECTOR.md` no longer contains setup/launch command recipes except
pointers; (3) every cross-reference into the moved sections still resolves; (4) gate
green + all completion-gate reviews SATISFIED.

## Context
- `.claude/DIRECTOR.md` — today's operating manual; mixes a behavioral guide (Identity,
  §1 read-the-picture, §2 taste-vs-handle, §3 worked example, §4 turn-review, §6 modes,
  §7 merge escalation, §8/§9 reporting, §13 lights-out) with **runbook** content (§0
  Standing up, §10 dashboard launch, §11 config commands, §12 daemon launch). The user's
  decoupling mandate: behavioral guide is a behavioral guide; runbook is a runbook.
- The concrete safe-fence recipe currently lives only in the `dogfood-shakedown-recipe-
  and-findings` **memory** (not in the repo, flagged stale): disposable copy-repo, the
  `${GH_TOKEN}` clone hook, `before_run` sync, `director.run --linear <ID>` cost-bound,
  `merger --once`, cleanup. This runbook brings that into the repo as durable, current.
- CLI surface (verified at base_commit): `director.run --ticket|--linear --worker --tools
  {none,linear} --install-skills --autonomous --max-turns` (single-ticket, **un-watched**
  / autonomous decider; reads the issue via `director.board.linear.read_issue`, needs
  `LINEAR_API_KEY`). `director.orchestrator --team --once|--daemon --worker --concurrency
  --turn-review-timeout --status-dir --queue-dir …` (watched/batch/daemon). `director.
  dashboard --port --status-dir --queue-dir --history-dir --events-dir`. Gate: `python3
  plugin/scripts/check.py`.
- This repo's committed `.harness.json` `director` block intentionally has **no `team`
  and no workspace hooks** (it is the orchestrator host, not aimed at a project) — so the
  live run uses a **separate runner clone** (`agent-harness-cc-runner`) whose own
  `.harness.json` carries the shakedown team + clone hooks. Keeping shakedown config out
  of canonical is itself a runbook lesson.
- Worker runtimes available locally: `codex` 0.142.0 on PATH (default worker; docs pin
  0.139.0 — drift to note), and the in-repo claude runtime built at `worker-runtime/app-
  server/dist/bin.js`. This run uses **codex** (the default path the runbook documents;
  also closes the codex-live-proof gap left by the per-ticket-event-stream work, which was
  live-proven only on claude).
- Disposable shakedown repos still exist (`agent-harness-shakedown`, `agent-harness-cc-
  shakedown`, `agent-harness-dogfood-claude`) — reuse one, no fresh `gh repo create`.
  `gh` token lacks `delete_repo` scope (cleanup-by-delete needs `gh auth refresh -s
  delete_repo`) — a runbook caveat.

## Approach (self-generated alternatives)
- A: **New stable-named runbook in `docs/` + slim DIRECTOR.md + cross-links.** The runbook
  is a docs-nav-indexed, map-linked page (genre = operating procedure / methodology);
  DIRECTOR.md stays the `.claude/` agent-config behavioral guide and links to it. Tradeoff:
  two files to keep in sync, but each has one clear job and the runbook is discoverable.
- B: **Expand DIRECTOR.md §0 in place.** One file. Tradeoff: perpetuates exactly the
  genre-mix the user flagged, and leaves the recipe in `.claude/` where docs-nav can't
  index it — undiscoverable, the original complaint.
- C: **Runbook in `.claude/` paired with DIRECTOR.md.** Keeps the pair together. Tradeoff:
  `.claude/` is outside the docs-nav corpus → not indexed/map-linked → poor discoverability.
- Chosen: **A** — it is the only option that both decouples the genres *and* makes the
  runbook discoverable (the root cause of the re-exploration pain). Cross-links solve the
  pairing concern.

## Assumptions & open questions (self-interrogation)
- Assumption: the runbook home is `docs/DIRECTOR_RUNBOOK.md` (stable name, no date — a
  living reference like `docs/PLANS.md`, not a dated spec/plan). If wrong, the doc still
  works anywhere under `docs/`; only the link targets change.
- Assumption: a single bounded canary ticket through the watched loop + merger is a
  sufficient behavioral proof of the runbook (it exercises dispatch, the turn-review
  judgment seam, the PR, and the serialized merger land — the full loop). A multi-ticket
  DAG / daemon soak is out of scope (cost; not needed to validate the *commands*).
- Assumption: reusing an existing shakedown repo + the existing runner clone (re-synced)
  is equivalent to a fresh stand-up for validation purposes, *and* I will separately
  smoke the "fresh stand-up" command sequence by reading it critically (a true from-empty
  `gh repo create` is gated by the missing `delete_repo`/clutter cost — recorded, not run).
- Open: which canary ticket / shakedown board to use → resolved autonomously at M3 from the
  Lingu test board (team `d4fac356-…`), reusing or creating one tiny docs ticket; not a
  taste fork.
- Open: exact split of DIRECTOR.md §10–§12 (some sentences are behavioral context, some are
  launch commands) → resolved at M2 by the rule **"a command to type → runbook; a decision
  to make → DIRECTOR.md"**, leaving a one-line pointer where commands left.

## Milestones
- **M1 — Draft the runbook (command-first).** Author `docs/DIRECTOR_RUNBOOK.md`: numbered
  zero→run sections — (0) what this is + when to use it, (1) prerequisites + the env
  contract, (2) the disposable-repo safe fence + runner clone, (3) `.harness.json` run
  config, (4) the **cheap path** (`director.run --linear <ID>`), (5) the **full watched
  loop** (orchestrator background + `director.watch` + answering turn-reviews) with the
  operator console + notifier, (6) the **merger land**, (7) daemon mode, (8) cleanup, (9)
  troubleshooting (the friction list: secrets not sourced, empty-workspace-without-hooks,
  codex version drift, missing `delete_repo`). Every command copy-pasteable; secrets by
  name only. At end: the file exists, registered in `docs/product-specs/index.md`-style
  index (whichever index the docs-tree convention dictates) and linked from the map; run
  `python3 plugin/scripts/check.py` → GREEN; `nav.py catalog --json` lists it.
- **M2 — Decouple DIRECTOR.md.** Move §0 and the launch-command portions of §10/§11/§12
  into the runbook (or delete where the runbook now owns them), leaving DIRECTOR.md as the
  behavioral guide with a top-of-file pointer to the runbook and inline pointers where
  commands used to be. Update every cross-reference (grep the tree + `nav.py backlinks
  .claude/DIRECTOR.md` and any `DIRECTOR.md §N` mentions in code/docs) so no link dangles.
  At end: DIRECTOR.md contains no `gh repo create` / `python3 -m director.orchestrator …`
  stand-up blocks except pointers; `grep -rn "DIRECTOR.md §" .` resolves to still-present
  sections; gate GREEN.
- **M3 — Live validation (codex, full loop, dashboard).** Re-sync the runner clone to
  canonical, point its `.harness.json` at a shakedown repo + the Lingu board, export
  secrets from `.env`, and **execute the runbook verbatim**: dispatch one canary `impl`
  ticket via the watched orchestrator, answer its turn-review(s) as the Director, watch the
  per-ticket drill-down live on the dashboard (`--events-dir`), then land the PR with
  `director.merger --once`. Log **every** step where I had to deviate from the runbook as a
  gap and fix the runbook. At end: a real PR is squash-merged onto the shakedown repo's
  `main`; a transcript snippet shows the drill-down streaming the ticket's turn/tool/token
  events; the runbook's commands match what actually worked. (If the run hits a hard blocker
  — rate window, auth — record it and fall back to the cheap `run --linear` path as the
  minimum behavioral proof; never silently skip.)
- **M4 — Completion gate.** `check.py` GREEN; self-review the full diff vs Goal; dispatch
  **review-spec-compliance** then **review-code-quality** (always-on); then the `targeted`
  personas — **review-security** (the runbook documents secret handling, the disposable-repo
  fence, and a live squash-merge) and **review-arch** (the doc-boundary decoupling decision).
  P1 → fix + rerun gate + re-review; P2 → Feedback + tech-debt-tracker. All SATISFIED →
  Outcomes, `status: completed`, `git mv` to `completed/`, commit + push.

## Progress log
- [x] (2026-06-25) Grounded: CLI flags, gate cmd, base_commit dcb3d08, `.env`/`.harness.json`
  config, runner clone present, shakedown repos extant, codex 0.142.0 + claude runtime built.
  Confirmed `.claude/` is outside docs-nav corpus → runbook goes in `docs/`. Plan authored.
- [x] (2026-06-25) M1 — authored `docs/DIRECTOR_RUNBOOK.md` (12 sections, command-first,
  every CLI verified against source at base_commit: run/orchestrator/watch/merger/notify/
  status/config/dashboard flags + the `director_min` answer API). Cross-links to
  `.claude/DIRECTOR.md`, ADR 0003 (`0003-lights-out-director.md`), PLANS.md all resolve.
  Gate GREEN. (remaining for discoverability: AGENTS.md/README pointers — folded into M2.)
- [x] (2026-06-25) M2 — decoupled DIRECTOR.md to the behavioral guide: retitled
  "behavioral guide" + top pointer to the runbook; §0 stand-up recipe → pointer (kept only
  the consumption-model framing); slimmed the launch-command blocks in §5/§10/§12 to runbook
  pointers (kept all judgment/semantics prose); §1–§14 numbering untouched (no renumber → all
  code/ADR/PRINCIPLES §N refs hold). Repointed the 4 live §0 refs → runbook: AGENTS.md
  (doc table + Porting), harness-init/SKILL.md, harness-packaging spec R6.3, base/SETUP.md.
  Decided the decoupling line: **DIRECTOR.md keeps only read-only `director.status`/
  `director.config`; every launch/run command lives in the runbook.** Gate GREEN.
- [x] (2026-06-25) Discovery folded into the runbook: tech-debt row 21 (single-ticket
  `director.run` path is un-observable — no on_event/status) → added a ⚠ caveat in runbook §5
  + a troubleshooting row, so the runbook doesn't send a reader to a blank dashboard.
- [x] (2026-06-25) M3 — **live codex run complete, full loop proven** (LIN-30 → PR #4 →
  merger squash → landed on shakedown `main` `bf15aa21`). Reused the runner clone (synced
  to ee743a6) + `agent-harness-shakedown` repo + Lingu board. Validated: dispatch, hooks,
  codex worker, **per-ticket event observability live on codex**, live token accrual, the
  **watched turnReview loop** (worker escalated → I answered as Director → resumed), and the
  **merger** (real tripwire+hygiene+squash). Surfaced 8 runbook gaps (all fixed) + 2 real
  findings (codex read_timeout 180s; needs_human→reply→done doesn't land the PR). Used
  `director.watch` as the Monitor per runbook §6 (after a course-correct from hand-rolled
  Bash poll-loops). Run cost ~2.96M tokens (mostly cached, F2 pattern); codex rate window
  hit 100% on the weekly secondary by the end.
- [ ] M4 completion gate (reviews + land plan)

## Surprises & discoveries
- **(M3) Runbook dir paths were wrong.** The real run-state dirs default to
  `.claude/harness/director-{status,queue,events}` (confirmed via the module source),
  NOT the `.harness/director-*` the runbook's §6/§7 examples and §10 cleanup used. A
  reader following §10's `rm -rf .harness` would clean nothing and carry stale state.
  → fix: runbook examples should omit the dir flags (rely on defaults) or use the real
  `.claude/harness/...` paths; cleanup must target `.claude/harness/`.
- **(M3) Stale queue is not GC'd across runs.** The runner's `.claude/harness/
  director-queue` still held a `mergeRequest` + `turnReview` from the 2026-06-20/23
  dogfood (PR #2, LIN-28). They showed as `pending` and the stale `mergeRequest` would
  have made `merger --once` act on an already-merged PR. → a fresh run MUST clean
  `.claude/harness/{queue,status,events,workspaces}` first; runbook §10 needs the right path.
- **(M3) Default dashboard port 8787 collided** with an unrelated `bun` process already
  bound to it on this host (not even a Director dashboard). → runbook §7 should note the
  default port may be taken and how to pick another (`--port`).
- **(M3) The dogfood `gh push` safe-fence step trips the auto-mode exfil classifier.**
  Force-pushing the whole private tree to the disposable shakedown repo was denied as
  "bulk relocation to a non-trusted destination." It is also usually unnecessary — an
  existing shakedown repo already carries a valid checkout. → runbook §2 should mark the
  initial canonical→shakedown push as a one-time, possibly-approval-gated step, and note
  reuse avoids it.
- **(M3) Worktree note confirmed live:** several *parallel* codex sessions were running
  (`knowledge-format`, `codex_somersault`, `obs-polish`) — broad `pkill codex` would have
  killed them. Stopping a run must target the orchestrator + its worker codex **by PID/cwd**,
  never by name. The runbook troubleshooting row on this is correct; reinforced.
- **(M3) codex read_timeout stayed at 180s** while the runner config bumped only
  `claude→1200` (`worker_runtime_read_timeout`). LIN-30 attempt 1 ran ~16 min then
  **failed and re-dispatched** (orch.log shows `before_run` twice; events show 2
  `turn_started`, no `turn_ended`) — the retry's `before_run` (`git reset --hard +
  git clean -fd`) **WIPED the uncommitted `runtime-glossary.md`**, so attempt 2 redid it.
  This is the **same class as the 2026-06-20 F3 finding** (read_timeout too short for a
  real worker). Actionable: set `worker_runtime_read_timeout.codex` generously (e.g. 600–1200)
  for heavyweight workers; the runbook troubleshooting row already flags the symptom but
  should name the per-runtime knob. NOT a regression in the harness; a config-tuning gap.
- **(M3, SIGNIFICANT) `needs_human` → reply-continue → `done`+PR never lands the PR.**
  The decider maps `report_outcome(status="needs_human")` → an `escalate` disposition
  (orchestrator.py:230) → ticket marked `escalated`/`started` (`:236-238`). I answered that
  turnReview with `{kind: reply}` ("continue"); the worker resumed and finished with
  `report_outcome(status="done", pr_url=PR#4)` — but **no terminal turnReview was posted
  for the final done, and `_maybe_enqueue_merge` never ran**, so LIN-30 stayed `escalated`
  with a clean open PR that would never auto-land. Observed live: queue had exactly 1
  turnReview (the needs_human), `run.stopped_reason=pass_complete`, `recent=[(LIN-30,
  escalated)]`, `last_message`=the done+PR message — a status/outcome mismatch. I landed
  PR #4 by manually calling `dq.append_merge_request(...)` (what the orchestrator would
  have done) + `merger --once --mock`. **This is a real orchestration hole** — a worker
  that escalates then completes is stranded. → tech-debt row (Important); runbook §11 row
  added so an operator knows to manually enqueue. Root-cause/fix is a separate plan.
- **(M3) FULL LOOP PROVEN end-to-end on codex.** dispatch → clone/sync hooks → codex worker
  (live per-ticket events: 295 events, 3 turn_starts, telemetry; live token accrual 2.96M)
  → attempt-1 read-timeout retry → `needs_human` escalation → **Director answers the
  turnReview** (reply) → worker resumes, writes `docs/references/runtime-glossary.md` +
  registers index, gate GREEN (694 tests), pushes, opens **PR #4** → merger's REAL
  preservation tripwire + hygiene gate (`sweep_evidence_consistent`, `verified_result:
  merged`, `misfire:false`) + code-issued squash → **landed on shakedown `main`**
  (`bf15aa21 docs(references): add runtime glossary (#4)`). Closes the codex live-proof gap
  from the per-ticket-event-stream work.
- **(M3) The worker CAUGHT a flawed ticket spec — exactly right.** My LIN-30 spec demanded
  the exact path `RUNTIME_GLOSSARY.md` (uppercase) **and** "do not modify anything else" —
  both impossible against the repo's own docs gate: D6 requires lowercase-kebab for
  non-top-level docs, and D8 requires registering a new `references/` page in `index.md`.
  The worker verified the baseline gate GREEN, made **zero** repo changes, and escalated
  `needs_human` with precise citations (`KNOWLEDGE_FORMAT.md:136`, `lint_docs.py:219`)
  rather than shipping a broken PR. Validates the worker's judgment + the watched turnReview
  seam end-to-end on codex. Lesson for ticket authors (and the runbook §4 example): a
  too-prescriptive ticket can be self-contradictory against the host's gate.

## Decision log
- 2026-06-25: Runbook in `docs/` not `.claude/` — `.claude/` is outside the docs-nav
  corpus, and discoverability is the user's actual pain; cross-link to keep the pair.
- 2026-06-25: codex worker for the live run — it is the default path a runbook should
  validate first, and it closes the codex live-proof gap from the per-ticket-event-stream
  work (which proved the drill-down only on the claude worker).
- 2026-06-25: Validate in a separate runner clone, not this checkout — keeps shakedown
  team/hooks out of the canonical committed `.harness.json` (true isolation per the
  worktrees-don't-isolate lesson).
- 2026-06-25: Skipped the canonical→shakedown force-push — the shakedown repo already had
  a valid (5-day-old) checkout, and the orchestration flow the runbook documents is
  snapshot-independent; also the push tripped the exfil classifier. Reuse > re-push.
- 2026-06-25: Answered LIN-30's `needs_human` turn-end as a `reply` (HANDLE inline, §2),
  not an escalate — the conflict was mechanical (the repo's own D6/D8 conventions decide
  it), so I directed: use lowercase `runtime-glossary.md` + register it in the index +
  open the PR. No taste fork to surface to the human.

## Feedback (from completion gate)
All five reviews **SATISFIED**, zero P1. (spec-compliance → code-quality always-on;
targeted risk personas review-security + review-arch.) P2s:
- **FIXED inline** (cheap doc improvements, not deferred):
  - (security) runbook §1 `worker_env` said "default `GH_TOKEN`" but the *code* default is
    an **empty** allowlist — reworded to "deny-by-default (empty in code); the reference
    `.harness.json` grants `GH_TOKEN`."
  - (code-quality) runbook §8 `--mock` comment now states unmissably it is **NOT a dry run**
    — it still issues a REAL `gh pr merge --squash` against `main`; only the land-lane worker
    is faked.
  - (code-quality) runbook §12 "See also" no longer hand-mirrors DIRECTOR.md's §-number map
    (a rot vector D5 can't catch) — trimmed to a genre statement.
  - (arch) runbook:22 `§0` pointer reworded to land on the *consumption-model paragraph*, not
    look like a redirect-to-a-redirect.
  - (spec-compliance) tracker row 21's stale "`DIRECTOR.md §0` recommends the safe path"
    citation repointed to runbook §5.
- **→ tech-debt-tracker (deferred, fix-forward):**
  - **(Important)** `needs_human` → reply-continue → `done`+PR strands the open PR (never
    enqueued for the merger) — the M3 orchestration finding; root-cause + fix is a separate
    orchestrator plan.
  - (spec-compliance) the runbook's "(tracked tech-debt)" claim is now true — the row above
    was added in this gate.
- **Noted, not actioned (out of scope / recurrence-gated):**
  - (security) codex pinned `0.142.0` in the runbook vs SECURITY.md's `0.139.0` live-probe
    evidence — a SECURITY.md staleness, not a runbook defect; align on a future SECURITY pass.
  - (arch, proposed rule) promote the genre-boundary line ("a command to type → runbook; a
    decision to make → DIRECTOR.md") into ARCHITECTURE.md invariant 5 / DESIGN.md so the two
    docs don't re-merge over time — track; promote on a 2nd occurrence.
  - (code-quality, proposed rule) a convention that cross-doc pointers cite a *named* section,
    never a re-typed copy of the partner's §-numbers — track; promote on a 2nd occurrence.

## Outcomes & retrospective
**Delivered, all verified.** (1) `docs/DIRECTOR_RUNBOOK.md` — a command-first, copy-pasteable
zero→live-run runbook, every command checked against source and **proven by a real codex run**.
(2) `.claude/DIRECTOR.md` decoupled to a pure behavioral guide (−144 lines; only read-only
`director.status`/`director.config` remain, every launch recipe → a runbook pointer), §1–§14
numbering preserved so all code/ADR/PRINCIPLES `§N` cross-refs still resolve; the 4 live `§0`
references repointed (AGENTS.md, base/SETUP.md, harness-init, packaging spec). (3) Discoverable:
in `docs/` (nav-indexed), linked from AGENTS.md's doc table + Porting block.

**The live codex dogfood (LIN-30) was the behavioral check — full loop proven:** dispatch →
clone/sync hooks → codex worker (live per-ticket events + token accrual) → attempt-1 read-timeout
retry → `needs_human` escalation → **Director answered the turnReview** → worker opened PR #4
(gate GREEN) → merger's REAL tripwire + hygiene gate + squash → **landed on shakedown `main`
(`bf15aa21`)**. Closed the codex live-proof gap for the per-ticket-event observability; used
`director.watch` as the Monitor per the runbook's own §6 (after a user-prompted course-correct
from hand-rolled poll loops — the runbook step *should* be dogfooded, not bypassed).

**Why this beat writing the runbook from memory:** executing the draft surfaced **8 concrete
gaps** that a recollection would have shipped wrong — wrong run-state dir paths
(`.claude/harness/…` not `.harness/…`), no cross-run queue GC, a default-port collision, the
canonical→shakedown push tripping the exfil classifier, kill-by-PID-not-name — plus **2 real
findings** (codex `read_timeout` 180s too short → retry wipes uncommitted work; the
`needs_human`→reply→done orchestration hole). All gaps fixed in the runbook; findings tracked.

**Retrospective.** Two process lessons worth carrying: (a) when *validating* a documented
procedure, **dogfood the procedure's own tooling** (`director.watch`) rather than a convenient
substitute — the substitute doesn't test the doc. (b) A too-prescriptive ticket can be
*self-contradictory* against the host's gate (my LIN-30 demanded an uppercase path + "don't
modify anything else", both impossible under D6/D8) — the worker correctly caught it and
escalated, which is the system working as designed. The single largest cost driver was worker
over-orientation (~2.96M tokens, mostly cached — the F2 pattern) on a trivial docs task.
