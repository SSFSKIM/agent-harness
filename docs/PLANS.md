---
status: stable
last_verified: 2026-06-12
owner: harness
---
# PLANS.md — ExecPlan methodology

Internalized from the OpenAI Codex cookbook practice: complex work rides a
self-contained **living ExecPlan**; small changes use throwaway plans.

## When
ExecPlan if any: multi-session work, touches ≥3 components, changes
architecture/memory semantics, or needs a completion gate. Otherwise throwaway.

## Template (copy into docs/exec-plans/active/YYYY-MM-DD-<slug>.md)

    ---
    status: active
    last_verified: <today>
    owner: <who drives>
    base_commit: <git rev-parse HEAD at plan creation>
    ---
    # <Title>
    ## Goal
    One paragraph. Definition of done, observable.
    ## Context
    Links to specs/ADRs/pages a novice needs. Self-contained.
    ## Milestones
    - [ ] M1 ... (each independently verifiable)
    ## Progress log
    - YYYY-MM-DD: ...
    ## Surprises & discoveries
    ## Decision log
    - YYYY-MM-DD: <decision> — <why>
    ## Feedback (from completion gate)
    ## Outcomes & retrospective

## Rules
- Update Progress/Surprises/Decisions as you work, not after.
- A novice agent must be able to execute from the plan alone.
- Completion = gate passed (execplan skill) → move to completed/, fill
  Outcomes & retrospective.
