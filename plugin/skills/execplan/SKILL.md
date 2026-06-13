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
3. Record `base_commit: $(git rev-parse HEAD)` and `review_level:` in the plan
   frontmatter (`none`, `targeted`, `standard`, or `full`), run the gate
   (command in `docs/design-docs/agent-harness.md`), commit.

## Maintain (as you work, not after)
- Append to Progress log each working block; record Surprises & discoveries
  and Decision log entries the moment they happen.

## Completion gate (the PR-boundary equivalent)
1. Run the gate (command in `docs/design-docs/agent-harness.md`) — must be GREEN.
2. **Self-review first**: read the full diff
   (`git diff <base_commit from plan frontmatter>..HEAD`) against the plan's
   Goal; fix what you would flag.
3. Spend the plan's review budget:
   - `none`: no subagent review; self-review + GREEN gate is enough.
   - `targeted`: dispatch only the persona(s) matching the risk touched
     (architecture/design, reliability/runtime, or security live exec surface).
   - `standard`: dispatch **review-arch** and **review-reliability** in parallel.
   - `full`: dispatch every relevant persona; include **review-security** when
     the diff touches the live exec surface — `hooks/`, `.harness.json` /
     `.claude/lints/` (host commands that run on commit), or
     `docs/.harnessignore` (lint scoping). The rest of the threat model guards
     the disabled memory loop — SECURITY.md is deferred; see its status note.
   Each persona prompt:
   "Review the diff for ExecPlan <slug>. Run `git diff <base_commit>..HEAD`
   (substitute the actual SHA from the plan's frontmatter) to see it. Read
   your grounding doc first. Output P1/P2 findings with file:line and a
   Verdict."
   (Task tool subagent_type is plugin-namespaced: `agent-harness:review-arch` etc.)
4. Process findings: P1 → fix now, rerun gate from step 1.
   P2 → append to the plan's Feedback section AND
   `docs/exec-plans/tech-debt-tracker.md`.
5. All verdicts SATISFIED → fill Outcomes & retrospective, set
   `status: completed`, `git mv` the file to `docs/exec-plans/completed/`,
   update `docs/QUALITY_SCORE.md` if grades changed, commit.
