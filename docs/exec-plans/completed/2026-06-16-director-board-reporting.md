---
status: completed
last_verified: 2026-06-16
owner: harness
type: exec-plan
tags: [director, board, telemetry]
description: Makes the watched Director proactively pull the human at run-level inflection by emitting a synthetic runReport event when a run reaches a terminal stopped_reason so the Director composes and pushes a run digest.
base_commit: 723e0dd537590d89640e2131d5d92f22ed444bd7
review_level: targeted
---
# Director board reporting (run-level pull) — build

## Goal
Make the watched Director **proactively pull the human** at a run-level inflection instead of
only reporting on demand. When an orchestration run reaches a terminal `stopped_reason`
(drained / stuck / max_passes / max_dispatched / poll_failed / pass_complete), `director.watch`
— already the Director's event-wake tail — emits a synthetic **`runReport`** event; the
event-woken Director reads `director.status`, composes a run digest, and `PushNotification`s the
human. Observable:
1. `director.watch` emits exactly ONE `runReport` line when the status snapshot's
   `run.stopped_reason` goes non-None (deduped per run by `(started_at, stopped_reason)`); a
   re-poll emits nothing more; a NEW run (new `started_at`) re-emits.
2. `runReport` is filterable via `--kinds` (the Director arms `turnReview,mergeReview,runReport`),
   and reading the status snapshot is read-only + tolerant (missing/torn → no emit, no crash).
3. `docs/DIRECTOR.md` tells the Director, on a `runReport`, to read `director.status`, compose a
   digest, and push it (the procedure; code never judges report-worthiness).
4. `python3 plugin/scripts/check.py` GREEN.

## Context
- **Spec (design owner, build from it — don't re-derive):**
  `docs/product-specs/2026-06-16-director-board-reporting.md` (R1–R6, D-1..D-5). Purpose =
  attention/pull (not durable record); trigger = run-level inflection, terminal-only emit;
  mechanism = extend `director.watch` to tail the status snapshot; watched-mode only.
- **Reuse:** `director/status.py::read_status` (tolerant snapshot reader; schema
  `{run:{started_at,pass,stopped_reason}, in_flight, recent, stuck, updated_at}`),
  `director/watch.py` (`new_pending` dedup tail + `_emit` + `main` with `--kinds`/`--queue-dir`/
  `--poll`/`--once`), `docs/DIRECTOR.md` §5 (event-woken loop) + §8 (on-demand report-up).
  `tests/test_director_watch.py` already exists — extend it.
- **No change** to `director/orchestrator.py` or `director/status.py`: the orchestrator already
  records `StatusWriter.finished(reason)` at the run terminal; `watch` only READS the snapshot.
- **Composer is the Director (the LLM, D-5):** the slice's code only SIGNALS (`watch` emits);
  the Director composes the digest + pushes (DIRECTOR.md procedure) — consistent with "code never
  judges done-ness/report-worthiness" (orchestration line D-5/D-30).

## Approach (self-generated alternatives)
Design is the spec's (D-1..D-5); here only execution choices.
- **Where the run-terminal seen-state lives:** a SECOND seen-set in `watch.main` keyed
  `(started_at, stopped_reason)` (parallel to the request `seen` keyed by request_id). Chosen —
  symmetric with `new_pending`, distinguishes runs (new `started_at` re-emits).
- **Emit shape:** a synthetic event `{kind:"runReport", reason, run, summary{by_status,stuck,
  in_flight}}` via a shared `_emit_line` (refactor `_emit` to project-then-`_emit_line`). The
  small `summary` makes the Monitor notification informative; the Director reads `director.status`
  for the full digest. Chosen over emitting the raw snapshot (too large for a notification line).
- **Pure helper vs inline:** factor `new_run_report(snapshot, seen, kinds)` + `_run_summary` as
  pure functions (testable without a live loop), mirroring `new_pending`. Chosen.

## Assumptions & open questions (self-interrogation)
- **Assumption — `run.stopped_reason` non-None == "run terminal".** True by `status.py`:
  `finished(reason)` is the only setter, called once at the end. *If wrong* (an intermediate
  non-None ever appears): the dedup key still fires once per distinct (started_at, reason).
- **Assumption — one `finished()` per run, so terminal-only = one runReport per run.** Matches
  `run_until_drained`/`run_once`. *If wrong:* the seen-set bounds it to one per (started_at,reason).
- **Open — `pass_complete` (run_once --once) also emits.** Resolved autonomously: emit on ANY
  non-None terminal; the Director judges relevance (a degenerate single pass is rare and harmless).
- **Open — multiple back-to-back runs reusing the same status.json.** A new run sets a new
  `started_at` (first claim), so its terminal is a new key → re-emits. A run with NO claims
  (started_at stays None) never sets a terminal worth reporting. Acceptable.

## Milestones
- **M1 — `watch` run-terminal emit.** In `director/watch.py`: add `new_run_report(snapshot, seen,
  kinds=None)` (returns a `runReport` event when `run.stopped_reason` is non-None and
  `(started_at, reason)` is unseen AND `runReport` passes the `kinds` filter, else None; mutates
  seen) + `_run_summary(snapshot)` (tally `recent` by `status`, `len(stuck)`, `len(in_flight)`) +
  refactor `_emit` over a shared `_emit_line`. `main` gains `--status-dir`; each poll, after the
  queue pass, calls `new_run_report(status.read_status(base=status_dir), run_seen, kinds)` and
  `_emit_line`s a non-None result. At the end: a status.json with a terminal run makes `watch
  --once` emit one runReport; re-poll none; new run re-emits; `--kinds` filters it; missing/torn
  snapshot → no emit, no crash. Run: `python3 -m unittest discover -s tests -p
  "test_director_watch.py"` (+ new assertions). Expect GREEN.
- **M2 — DIRECTOR.md procedure + integration test + completion gate.** `docs/DIRECTOR.md`: §5
  step 2 watch line gains `runReport` + `--status-dir`; new section "Run-level reporting — pull the
  human" (on a `runReport`: read `director.status`, compose a digest — outcome · done/failed/
  blocked/escalated counts · what's stuck and why · open merge escalations · what needs the human —
  and `PushNotification` per the taste-vs-handle line; code never judges). Integration test: drive
  `orchestrator.run_until_drained` on a MockBoard to a real `status.json`, then `watch --once
  --status-dir <that>` emits a runReport whose `reason` matches the run's `stopped_reason`. At the
  end: the mechanism is proven against an orchestrator-produced snapshot, and the Director has a
  documented procedure. Run: `python3 plugin/scripts/check.py` GREEN; then the targeted completion
  gate (review-reliability via codex — dedupe/tolerance/no-spam is the risk). (No real-codex live
  wire-pin: the slice's code only SIGNALS; the Director's compose+push half is prose, verified by
  the procedure + the emit mechanism test.)

## Progress log
- [x] (2026-06-16) M1 — watch run-terminal emit. `director/watch.py`: `new_run_report(snapshot,
  seen, kinds)` (emits a `runReport` when `run.stopped_reason` is non-None and `(started_at,reason)`
  unseen + passes `--kinds`; tolerant of None/empty → None) + `_run_summary` (recent by-status +
  stuck/in-flight counts) + `_emit_line` refactor; `main` gained `--status-dir` + a `run_seen` set
  + a status pass after the queue pass (read_status tolerant). Docstring updated. 6 watch tests:
  emit-once-per-run + new-run-re-emits, no-emit-until-terminal, tolerant of missing/empty, --kinds
  excludes runReport, and a `main --once` test driving a real `StatusWriter` snapshot → runReport.
  Gate GREEN (317).
- [x] (2026-06-16) M2 — DIRECTOR.md procedure + integration test. `docs/DIRECTOR.md`: §5 step 2
  watch line gains `runReport` + `--status-dir` (and step 3 routes `runReport` → §9); new §9
  "Run-level reporting (pull the human when a run ends)" — on a runReport: read `director.status`,
  compose a digest, and decide the pull on the taste-vs-handle line (stuck/poll_failed/failure-pattern
  = "you're needed" push; clean drained = quiet record; failure-pattern is the Director's judgment,
  not code); watched-mode only. Integration test `OrchestratorToWatchIntegrationTest`: a real
  `orchestrator.run_until_drained` (faked dispatch → drained) writes status.json → `watch --once
  --status-dir` emits one runReport with `reason=="drained"`. Gate GREEN (318). Completion gate
  (targeted: review-reliability via codex) next.

## Surprises & discoveries

## Decision log
- 2026-06-16: second seen-set keyed `(started_at, stopped_reason)` for run reports (symmetric with
  the request seen-set); emit a compact `runReport` event (not the raw snapshot) via a shared
  `_emit_line`; `watch` only READS the status snapshot (orchestrator/status.py untouched).

## Feedback (from completion gate)
One codex reviewer (review-reliability, gpt-5.5, high effort) — two P1s; one fixed, one
downgraded-and-tracked with rationale:
- **[P1, fixed] `started_at=None` dedupe collision.** A no-claim run (stuck-from-start — all
  blockers unmet) finishes with `started_at=None`; two such runs share key `(None, stopped_reason)`
  so the 2nd's runReport is swallowed — losing a real "human needed to unblock" pull. **FIXED:**
  `StatusWriter.wave()` now sets `started_at` at the first wave (every run calls `wave()` before
  any claim), giving every run a stable identity. Revises the plan's "no status.py change"
  assumption — a 2-line root-cause fix. Test: a no-claim wave→stuck→finished run has `started_at`.
- **[P2, downgraded from P1, tracked] snapshot-overwrite race.** The single `status.json` is a
  latest-state surface: if a 2nd run overwrites it within one 0.5s poll interval of the 1st
  finishing, `watch` misses the 1st's terminal. Downgraded because the watched-Director model (the
  only mode this applies to, R5) runs one `run_until_drained` at a time, human/LLM-paced — it never
  launches sub-poll-interval back-to-back runs. The fix (a durable terminal-event append-log) is a
  different mechanism that edges toward the *rejected* durable-record/separate-channel direction, so
  it's out of the chosen snapshot-tail design's scope → tracked, not built. Gate GREEN (318).

## Outcomes & retrospective
**Board reporting — the last enumerated Phase 4 roadmap item — is built.** `director.watch` now
tails the orchestration status snapshot alongside the queue and emits a `runReport` when a run
reaches a terminal `stopped_reason`; the event-woken Director (DIRECTOR.md §9) reads
`director.status`, composes a run digest, and `PushNotification`s the human — the taste-vs-handle
line deciding a real "you're needed" pull (stuck / poll_failed / failure-pattern) vs a quiet "run
complete." Watched-mode only; code only SIGNALS (the Director judges report-worthiness, never code
— consistent with D-5/D-30). Blast radius stayed tiny: `watch.py` + `DIRECTOR.md` + a 2-line
`status.py` run-identity fix; `orchestrator.py` untouched.

With this, **every enumerated Phase 4 roadmap slice is shipped** (worker authority guardrail →
visibility/escalation → un-watched autonomy → multi-turn → PR-merge incl. re-enqueue → board
reporting). The remaining Phase-4-adjacent work is the deferred security track (worker fs-wide
cred read + egress → container + vault-proxy plans) — its own future effort.

Tracked limitation: the snapshot-tail can miss a run terminal under sub-poll-interval back-to-back
runs (P2; not the watched single-run use case). Retro: the completion gate again earned its keep —
the no-claim run-identity collision was a real swallow-a-pull bug invisible to the green gate; and
the overwrite-miss is the honest tradeoff of choosing a latest-state snapshot surface over an
append-log (chosen knowingly, per the spec's mechanism decision).
