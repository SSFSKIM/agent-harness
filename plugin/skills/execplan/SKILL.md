---
name: execplan
description: Use when starting non-trivial work (multi-session, ≥3 components, architecture/memory changes) or when declaring an ExecPlan complete — creates/maintains living ExecPlans and runs the completion gate.
---
# ExecPlan procedure

Method and template live in `docs/PLANS.md` — read it first.

## Create
1. Copy the template from docs/PLANS.md to
   `docs/exec-plans/active/YYYY-MM-DD-<slug>.md` (kebab-case slug).
2. **Scope check.** If the work spans independent subsystems, split into linked
   ExecPlans (one per subsystem) before going further — see PLANS.md "When".
3. Fill Goal (observable definition of done), Context (links a novice needs; if
   a product-spec exists for this work in docs/product-specs/, link it and build
   from its design — don't re-derive the spec — see the entry decision in
   PLANS.md),
   Approach (generate ≥2 alternatives yourself, then choose), Assumptions & open
   questions (surface what you take as given; resolve ambiguities autonomously),
   Milestones (narrative — scope, what newly exists, command, acceptance;
   independently verifiable). These front-loading sections are self-gates —
   your own reasoning, not a human dialogue; escalate only Taste/Style/judgment
   (PRODUCT_SENSE.md). Flesh the skeleton out to PLANS.md depth — full file
   paths, validation that proves behavior (not just "it compiles"), the *why* —
   don't ship a skeleton.
4. **Creation-time self-review** (before any implementation; fix inline):
   placeholder scan (no TBD / "handle later"), internal consistency (Approach ↔
   Goal ↔ Milestones agree), scope (still single-subsystem?), ambiguity (each
   requirement reads one way). Catching a bad plan here is far cheaper than at
   the completion gate.
5. Record `base_commit: $(git rev-parse HEAD)` and `review_level:` in the plan
   frontmatter (`none`, `targeted`, `standard`, or `full`), run the gate
   (command in `docs/design-docs/agent-harness.md`), commit.

## Execute (per milestone)
Read the plan's `execution:` field (PLANS.md "Execution mode").
- **`inline`** (default): implement each milestone yourself in this session.
- **`fork`**: dispatch each milestone M_k as `subagent_type:"fork"` (Agent/Task
  tool) when your runtime supports it (Claude Director / Claude worker). The fork
  inherits this session's full context, so the dispatch is one line — "implement
  milestone M_k per the active ExecPlan: TDD, run its acceptance, commit, update the
  plan's Progress/Decision/Surprises log, then return a short summary (what exists /
  key decisions / what the next milestone needs / test evidence / commit SHAs)".
  Between forks stay a thin orchestrator: receive the summary, dispatch the next, do
  no other work (it pollutes the next fork's inheritance). If your runtime has no
  fork subagent (Codex worker), run inline. Either way the durable plan doc + commits
  are the continuity backbone, and completion-gate reviews are always fresh
  subagents — never forks.

## Maintain (as you work, not after)
- Append to Progress log each working block; record Surprises & discoveries
  and Decision log entries the moment they happen.

## Completion gate (the PR-boundary equivalent)
1. Run the gate (command in `docs/design-docs/agent-harness.md`) — must be GREEN.
2. **Behavioral check (conditional).** If the work has a runnable surface — a CLI flow,
   a service, or a UI — actually run the plan's behavioral acceptance and a smoke /
   end-to-end pass, and capture the output; drive a web surface with the `playwright-cli`
   skill (`/playwright-cli`). If the deliverable is pure docs / methodology with nothing
   to run, record **N/A + a one-line why** in the plan — "no behavioral QA" is a recorded
   decision, never a silent omission.
3. **Self-review**: read the full diff
   (`git diff <base_commit from plan frontmatter>..HEAD`) against the plan's
   Goal; fix what you would flag.
4. **Always-on QA review (EVERY ExecPlan, independent of `review_level`):** dispatch
   **review-spec-compliance** first — did the diff build exactly the spec/plan
   (nothing missing, nothing extra, no misread requirement)? Only if it returns
   SATISFIED, dispatch **review-code-quality** — is the diff clean, decomposed,
   tested, maintainable? (Quality matters only once the right thing was built; a
   NOT-SATISFIED compliance verdict is a P1 — fix, rerun gate, re-review before
   quality.) These two run on every completion; `review_level` does NOT gate them.
5. Spend the plan's **risk-budget** persona review (`review_level` governs ONLY these):
   - `none`: no risk personas (step 4 still runs — it is unconditional).
   - `targeted`: dispatch only the persona(s) matching the risk touched
     (architecture/design, reliability/runtime, or security live exec surface).
   - `standard`: dispatch **review-arch** and **review-reliability** in parallel.
   - `full`: dispatch every relevant persona; include **review-security** when
     the diff touches the live exec surface — `hooks/`, `.harness.json` /
     `.claude/lints/` (host commands that run on commit), or
     `docs/.harnessignore` (lint scoping). The rest of the threat model guards
     the disabled memory loop — SECURITY.md is deferred; see its status note.
   Every reviewer (step 4 and step 5) gets the same prompt shape:
   "Review the diff for ExecPlan <slug>. Run `git diff <base_commit>..HEAD`
   (substitute the actual SHA from the plan's frontmatter) to see it. Read
   your grounding doc first. Output P1/P2 findings with file:line and a
   Verdict."
   (The Task tool `subagent_type` depends on how the methodology reached your runtime:
   `agent-harness:review-spec-compliance` / `…:review-code-quality` / `…:review-arch` …
   when it is installed as a PLUGIN (the Director), or the bare `review-spec-compliance` /
   `review-code-quality` / `review-arch` … when the agents are VENDORED into the workspace's
   `.claude/agents/` or `.codex/agents/` (a worker — see
   `director/run.py:install_worker_methodology`). Use whichever your runtime exposes.)
6. Process findings (steps 4 + 5): P1 → fix now, rerun gate from step 1.
   P2 → append to the plan's Feedback section AND
   `docs/exec-plans/tech-debt-tracker.md`.
7. All verdicts SATISFIED → fill Outcomes & retrospective, set
   `status: completed`, `git mv` the file to `docs/exec-plans/completed/`,
   update `docs/QUALITY_SCORE.md` if grades changed, commit.
