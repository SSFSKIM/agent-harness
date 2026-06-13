---
status: stable
last_verified: {{TODAY}}
owner: harness
---
# PLANS.md — ExecPlan methodology

Internalized from the OpenAI Codex cookbook practice and the published
openai-agents-js `PLANS.md` spec: complex work rides a self-contained
**living ExecPlan**; small changes use throwaway plans.

## When
ExecPlan if any: multi-session work, touches ≥3 components, changes
architecture/memory semantics, or needs a durable decision log. Otherwise
throwaway. The plan owns its review budget; do not spend full-review ceremony on
low-risk work.

## Review budget
- `none` — gate + self-review only. Small, low-risk, mechanically checked work.
- `targeted` — gate + self-review + the persona(s) matching the risk touched.
- `standard` — gate + self-review + review-arch and review-reliability.
- `full` — gate + self-review + all relevant personas, including security.

## Template (copy into docs/exec-plans/active/YYYY-MM-DD-<slug>.md)

    ---
    status: active
    last_verified: <today>
    owner: <who drives>
    base_commit: <git rev-parse HEAD at plan creation>
    review_level: targeted
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
- Completion = gate passed + the plan's review budget satisfied (execplan
  skill) → move to completed/, fill Outcomes & retrospective.

## Quality rules (from the upstream ExecPlan spec)
- **Goal = demonstrably working behavior.** Phrase the definition of done as
  behavior a human can verify (command → observable output), never as "code
  changed" or "struct added".
- **Define every term of art** at first use in plain language, or don't use it.
- **Prose first.** Narrative sentences carry the plan; checklists belong only
  in Milestones and the Progress log.
- **Unknowns get PoC milestones.** A milestone with significant unknowns is
  first a toy implementation validating feasibility, then the real thing.
- **Resolve ambiguities autonomously.** Never stop to ask "what next?" — pick
  the reasonable path, record it in the Decision log, commit frequently.
  Escalate only true judgment calls (docs/PRODUCT_SENSE.md).
