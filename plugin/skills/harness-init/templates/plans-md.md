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

**Scope check first.** If the work spans independent subsystems (each
independently shippable and testable), split into linked ExecPlans — one per
subsystem, this plan as the parent index — *before* filling Milestones.
Capturing multi-subsystem work in a single plan is a plan failure: you lose
independent verifiability and the plan stops fitting in one context.

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
    ## Approach (self-generated alternatives)
    Generate ≥2 viable approaches yourself and choose — your own reasoning, not
    a human dialogue. (review_level: none → one line naming the choice + why.)
    - A: <approach> — tradeoff
    - B: <approach> — tradeoff
    - Chosen: <X> — why (mirror into Decision log)
    ## Assumptions & open questions (self-interrogation)
    - Assumption: <taken as given> — what breaks if wrong
    - Open: <ambiguity> → resolved autonomously as <choice>; escalate ONLY a
      Taste/Style/product-judgment call (PRODUCT_SENSE.md), never "what next?"
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
- **Front-loading is self-gates, not human gates.** Approach, Assumptions, and
  the creation-time self-review are the agent reasoning with itself. The human
  touches only Taste/Style/product judgment (PRODUCT_SENSE.md) — never "what
  next?".
- **Self-review at creation, not only at completion.** Before any
  implementation, scan the plan for placeholders, internal contradictions, scope
  creep, and ambiguous requirements; fix inline. Catching a bad plan here is far
  cheaper than catching it at the completion gate.
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
