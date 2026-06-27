---
status: accepted
last_verified: 2026-06-28
owner: harness
type: adr
tags: [director, orchestration, modes, autonomy, daemon]
description: Collapse the Director's multi-"mode" surface into ONE operating mode (Director ⟷ Board); human-presence and run-loop bounds are properties, the pure-code/batch paths are fixtures, and the always-on daemon is the default.
---
# One operating mode — Director ⟷ Board

Refines [[0002-graduated-autonomy]] and [[0003-lights-out-director]] (recursive
decomposition, [[0001-recursive-decomposition]]): those split the old "mode bit"
into independent axes; this ADR finishes the arc by **removing the residual
multi-mode framing entirely** — there is one operating mode, and the former
"modes" are reclassified as *properties* or *fixtures*.

## Decision

**There is exactly one operating mode: an always-present Director (judging agent)
adjudicating an always-present Board (the Linear work queue).** Everything today
presented as a co-equal "mode" is reclassified:

| Today's "mode" | Reclassified as | Why it is not a mode |
|---|---|---|
| `watched` / attended | **property** — *human present* | Same code path as lights-out (`make_queue_decider`); only *who answers* a turn-end differs. |
| `lights-out` | **property** — *human absent (async-reachable)* | Identical path + posture; the human is simply not at the keyboard, so the Director consults `PRINCIPLES.md` and parks/pings the residual (DIRECTOR.md §13 procedure). |
| `daemon` (always-on loop) | **the mode itself — and the default** | "Always-present" *means* always-on; the daemon is how the one Director runs, not a third thing you switch into. |
| `batch` (`run_until_drained`) / `--once` | **fixture** — bounded dev/test/CI run | Drain-and-exit is a convenience for tests and quick runs, not an operating posture. |
| `--autonomous` (`autonomous_decide`) | **fixture** — no-judge CI/`--mock`/detached | In production a Director (human or daemonized) is *always* present, so the pure-code decider never runs in production. |

Two sub-decisions make this concrete:

1. **The daemon is the default loop for real runs.** `python3 -m
   director.orchestrator --team T` (no loop flag) runs `run_forever`. `--batch`
   (`run_until_drained`) and `--once` (`run_once`) remain as explicitly-labeled
   fixtures. `--daemon` stays as an accepted, **documented-deprecated alias** (it
   now selects the default) — removed in a later cleanup once invocations/runbook
   no longer reference it.

2. **`--mock` implies the bounded loop.** The offline fixture has no live board to
   poll forever, so `--mock` runs drain-and-exit — one more `--mock` override
   beside the ones it already applies (the no-judge decider, `install_skills=False`,
   `tools="none"`, hooks off). This keeps tests and quick offline runs bounded and
   is what makes "daemon = default" safe to ship.

The **status `mode` field is kept but reframed**: it is a runtime *heartbeat label*
(`daemon` for the always-on loop; the bounded `--batch`/`--once` fixtures don't poll, so
they emit no heartbeat and `mode` stays `None`) — not a user-chosen mode. No schema change.

## Why

- **It completes ADR 0002→0003.** 0003 already says attended and lights-out are the
  *same* `make_queue_decider` path ("no new orchestrator flag") and rebinds
  "autonomous" to the no-agent niche. The only thing left was the *framing*:
  DIRECTOR.md still titled §6 "The three modes" and §12 called the daemon "the third
  mode." The muddle the human flagged was **naming, not mechanism** — so the fix is
  to delete the false peer-distinctions, not to rebuild anything.
- **One mode is the honest description of the production system.** In production
  there is always a Director and always a Board; the human drifts in and out
  (a property), and the loop runs forever (the mode). Presenting five "modes"
  mis-describes a system that has one.
- **"All are not needed" is about framing, not capability.** The bounded loops and
  the pure-code decider are useful *mechanisms* (tests, CI, quick runs). They are
  retained — demoted from "modes" to "fixtures," not deleted. Deleting them would
  trade a real capability for naming purity (rejected: ExecPlan Approach C).
- **Aligning the CLI is what actually resolves the complaint.** A docs-only reframe
  would leave `--daemon`/`--autonomous` advertised as co-equal modes — the muddle
  surviving in the interface. Making the daemon the default and demoting the
  fixtures makes the *interface* present one mode too.

## Consequences

- **No security/posture change.** Posture is identical across all of today's
  "modes" (shared `on-request` + `auto_review` + network — SECURITY T11). This
  collapse is orthogonal to the threat model; nothing in the exec/sandbox surface
  moves.
- **The Daemonized Claude Code runtime stays a separate track** (0003): this ADR
  fixes the *model + CLI*, which is the groundwork that runtime consumes. The
  [[no-headless-director-codex-owns-approval]] memory **stands** — the always-on
  Director is a stateful main session, not a per-decision spawn.
- **Code (ExecPlan M2):** `director/orchestrator.py` default → `run_forever`;
  `--mock` → bounded; `--batch` added; `--once`/`--daemon`(alias) kept;
  `--autonomous` re-documented as a fixture; comment/heartbeat wording in
  `director/run.py`, `director/config.py`, `director/status.py` reframed.
- **Docs (ExecPlan M2/M3):** `.claude/DIRECTOR.md` §5/§6/§12/§13 and
  `docs/DIRECTOR_RUNBOOK.md` rewritten to "one mode + properties + fixtures."
- **Refines, does not supersede, 0002/0003.** Their decisions stand (graduated
  autonomy; the two-axes split; PRINCIPLES.md; taste-vs-mechanical). This ADR only
  retires the *"N modes"* presentation those decisions left behind. Each carries a
  forward "refined by 0007" pointer.
- **Live risk to watch:** the daemon-default flip is a real CLI behavior change — a
  bare real run now never exits without a signal. Mitigations: `--mock`/`--batch`/
  `--once` cover bounded needs; Ctrl-C → graceful drain already exists; the runbook
  is updated in the same change. A stray invocation that expected drain-and-exit now
  runs on — caught by the runbook update and the deprecated-`--daemon` continuity.
- Runs the standard ExecPlan completion gate (spec-compliance + code-quality +
  review-arch + review-reliability). Plan:
  `docs/exec-plans/active/2026-06-28-one-operating-mode.md`.
