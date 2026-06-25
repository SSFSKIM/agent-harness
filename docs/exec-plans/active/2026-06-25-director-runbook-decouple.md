---
status: active
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
- [ ] M1 draft runbook (done: —; remaining: author + register + gate)
- [ ] M2 decouple DIRECTOR.md
- [ ] M3 live codex validation
- [ ] M4 completion gate

## Surprises & discoveries

## Decision log
- 2026-06-25: Runbook in `docs/` not `.claude/` — `.claude/` is outside the docs-nav
  corpus, and discoverability is the user's actual pain; cross-link to keep the pair.
- 2026-06-25: codex worker for the live run — it is the default path a runbook should
  validate first, and it closes the codex live-proof gap from the per-ticket-event-stream
  work (which proved the drill-down only on the claude worker).
- 2026-06-25: Validate in a separate runner clone, not this checkout — keeps shakedown
  team/hooks out of the canonical committed `.harness.json` (true isolation per the
  worktrees-don't-isolate lesson).

## Feedback (from completion gate)

## Outcomes & retrospective
