---
name: execplan
description: Use when starting non-trivial work (multi-session, ≥3 components, architecture/memory changes) or when declaring an ExecPlan complete — creates/maintains living ExecPlans and runs the completion gate.
---
# ExecPlan procedure

Method and template live in `docs/PLANS.md` — read it first.

## Create
1. Copy the template from docs/PLANS.md to
   `docs/exec-plans/active/YYYY-MM-DD-<slug>.md` (kebab-case slug).
2. Fill Goal (observable definition of done), Context (links a novice needs),
   Milestones (each independently verifiable).
3. Run `python3 plugin/scripts/check.py`; commit.

## Maintain (as you work, not after)
- Append to Progress log each working block; record Surprises & discoveries
  and Decision log entries the moment they happen.

## Completion gate (the PR-boundary equivalent)
1. Run `python3 plugin/scripts/check.py` — must be GREEN.
2. **Self-review first**: read the full diff
   (`git diff <plan-start-commit>..HEAD`) against the plan's Goal; fix what
   you would flag.
3. Dispatch all three personas **in parallel** (Task tool), each with:
   "Review the diff for ExecPlan <slug>. Run `git diff <base>..HEAD` to see
   it. Read your grounding doc first. Output P1/P2 findings with file:line
   and a Verdict."
   - review-arch · review-reliability · review-security
4. Process findings: P1 → fix now, rerun gate from step 1.
   P2 → append to the plan's Feedback section AND
   `docs/exec-plans/tech-debt-tracker.md`.
5. All verdicts SATISFIED → fill Outcomes & retrospective, set
   `status: completed`, `git mv` the file to `docs/exec-plans/completed/`,
   update `docs/QUALITY_SCORE.md` if grades changed, commit.
