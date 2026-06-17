---
status: stable
last_verified: 2026-06-14
owner: harness
---
# PLANS.md — ExecPlan methodology

Internalized from the OpenAI Codex cookbook practice and the published
openai-agents-js `PLANS.md` spec: complex work rides a self-contained
**living ExecPlan**; small changes use throwaway plans.

## Entry decision (pick the mode first)
Before starting, judge the work and pick how to enter. This is your own
risk-budgeted call (like `review_level`), not a checklist gate — the signals
below are questions, not thresholds. Escalate only a product-direction/taste
fork (PRODUCT_SENSE.md), never "what next?".
- **throwaway** — small, low-risk, the *what* is obvious. In-conversation plan.
- **Product Design (spec first)** — the *what* deserves settling before the
  *how*: requirements outlive a single plan, fan out across linked plans, or are
  rich/contested enough to verify independently. Write a spec in
  `docs/product-specs/` (the `product-design` skill), then an ExecPlan that
  references it. The spec owns the design (what/why + how it is shaped:
  components, contracts, behaviors); the ExecPlan owns the build (executing it).
- **ExecPlan** — non-trivial work whose *what* is already clear enough.
  Front-load Approach/Assumptions inline (Template below); no separate spec.

A single rich plan can still carry its spec inline; a tiny change never needs
one. Product Design is also where the rare human touch lands — the agent drafts
the spec autonomously and escalates only a genuine product-direction call.

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

This applies **recursively and at the spec level**: a sub-project that is itself
too big decomposes the same way, each piece getting its own spec → ExecPlan
cycle; a parent (capability) spec just indexes its children and any roadmap is a
derived view of them. No higher-order spec system is needed — run-time fan-out is
the ticket DAG, not a doc subsystem (see `docs/memory/adr/0001-recursive-decomposition.md`).

## Review budget
Two reviews are **always-on** — they run at every ExecPlan completion regardless of the
level below: **spec-compliance** (did the diff build exactly the spec/plan — nothing
missing, nothing extra?) then **code-quality** (clean, tested, maintainable?).
`review_level` governs ONLY the additional *risk personas*:
- `none` — gate + self-review + the two always-on QA reviews; no risk personas.
- `targeted` — + the risk persona(s) matching the risk touched.
- `standard` — + review-arch and review-reliability.
- `full` — + all relevant personas, including review-security.

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
    Links to specs/ADRs/pages a novice needs. Self-contained. If a product-spec
    exists for this work (docs/product-specs/), link it and build from its
    design — the spec owns the design, this plan owns the build (don't re-derive
    the spec).
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
    Each milestone is a short narrative, not a bare checkbox: its scope, what
    will exist at the end that did not before, the command to run, and the
    acceptance to observe (goal → work → result → proof). Independently
    verifiable, moves the Goal forward, never abbreviated for brevity.
    - M1 — <scope>. At the end <what exists>; run <cmd>; expect <observable>.
    ## Progress log
    Granular steps with timestamps; at each stopping point reflect the true
    state, splitting a partial task into done vs remaining.
    - [x] (YYYY-MM-DD HH:MMZ) <step done>
    - [ ] <step remaining> (done: X; remaining: Y)
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

## Quality rules (from the upstream ExecPlan spec; extended 2026-06-14)
- **Goal = demonstrably working behavior.** Phrase the definition of done as
  behavior a human can verify (command → observable output), never as "code
  changed" or "struct added".
- **Define every term of art** at first use in plain language, or don't use it.
- **Prose first.** Narrative sentences carry the plan — milestones included;
  checklists belong only in the Progress log.
- **Unknowns get PoC milestones.** A milestone with significant unknowns is
  first a toy implementation validating feasibility, then the real thing.
- **Resolve ambiguities autonomously.** Never stop to ask "what next?" — pick
  the reasonable path, record it in the Decision log, commit frequently.
  Escalate only true judgment calls (docs/PRODUCT_SENSE.md).
- **Acceptance is provable behavior.** State the command and the output to
  expect; a new test must fail before the change and pass after. Prove the
  change beyond "it compiles".
- **Behavioral check is conditional (completion gate).** When the deliverable has a
  runnable surface (a CLI flow, service, or UI), the completion gate actually runs the
  plan's behavioral acceptance + a smoke/end-to-end pass — a web surface via the
  `playwright-cli` skill — and captures the output. Pure docs/methodology records N/A +
  a one-line why; never a silent skip.
- **Idempotent and recoverable.** Write steps safe to re-run; for a risky,
  destructive, or migration step, give a retry or rollback path.
- **Full paths and the why.** Name files by full repo-relative path; embed the
  non-obvious knowledge a novice needs rather than pointing outside the repo;
  record the *why* for almost every change and keep short proof (a transcript or
  diff) in Surprises/Outcomes.
