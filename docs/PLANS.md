---
status: stable
last_verified: 2026-06-14
owner: harness
---
# PLANS.md — ExecPlan methodology

Internalized from the OpenAI Codex cookbook practice (the `codex_exec_plans`
spec): complex work rides a **living ExecPlan**; small changes use throwaway
plans. We adapt the spec to our operating model — upstream assumes a *stateless
reader with one file*, so it forbids external references and demands total
self-containment. Our agent has memory + the AGENTS.md map + the real repo on
disk, so we instead **point precisely to the docs it reads directly** and split
spec design from implementation design (below).

## When
ExecPlan if any: multi-session work, touches ≥3 components, changes
architecture/memory semantics, or needs a completion gate. Otherwise throwaway.

## Two docs: spec design vs implementation design
A non-trivial feature gets a **design-doc** AND an ExecPlan; they divide cleanly:
- **design-doc** (`docs/design-docs/<name>.md`) = **spec design** — the
  conceptual what/why, external mapping (e.g. "Codex mechanism → our
  adaptation"), scope decisions. A stable reference the agent reads directly;
  don't duplicate it into the plan.
- **ExecPlan** = **implementation design** — the technical contract: the
  signatures/types that must exist at each milestone's end, the concrete seams,
  commands, acceptance. Technical detail lives HERE, not pushed up to the
  design-doc.
A small change needs neither — just a throwaway in-conversation plan.

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
    Point precisely (file + section) to the design-doc and any in-repo/on-disk
    docs the agent should read directly — don't duplicate them. External sources
    outside the repo (vendored trees, vault notes) = mark as fidelity refs; if
    one may be absent elsewhere, record its load-bearing decisions in the
    Decision log so the plan survives without it.
    ## Milestones
    - [ ] M1 ... (each independently verifiable. A PoC/feature milestone names
      its acceptance as "exact command -> observed output"; when it defines a new
      cross-component interface or touches persistent/destructive state, also the
      signatures/types that must exist at its end + a one-line idempotence/
      recovery note. Pure-doc milestones need neither.)
    ## Progress log
    - YYYY-MM-DD: ...
    ## Surprises & discoveries
    ## Decision log
    - YYYY-MM-DD: <decision> — <why>
    ## Feedback (from completion gate)
    ## Outcomes & retrospective

## Rules
- Update Progress/Surprises/Decisions as you work, not after.
- The agent executes from the plan **plus the docs it points to** — point
  precisely; never embed or duplicate a doc that already lives in the repo.
- Completion = gate passed (execplan skill) → move to completed/, fill
  Outcomes & retrospective.

## Quality rules (2026-06-12 from the upstream ExecPlan spec; refined 2026-06-14)
- **Goal = demonstrably working behavior.** Phrase the definition of done as
  behavior a human can verify (command → observable output), never as "code
  changed" or "struct added".
- **Acceptance is per-milestone and loose.** A PoC/feature milestone names its
  acceptance as a reproducible command → expected output (not just "PASSED");
  the completion gate covers pure-doc/refactor milestones, which are exempt.
  This is the guard against "compiles but does nothing meaningful".
- **Technical contracts are conditional and live in the plan.** When a milestone
  defines a new cross-component interface or touches persistent state, state the
  signatures/types that must exist at its end and a short idempotence/recovery
  note inline in that milestone — not a separate mandatory section, and not
  pushed to the design-doc.
- **Define every term of art** at first use in plain language, or don't use it.
- **Prose first.** Narrative sentences carry the plan; checklists belong only
  in Milestones and the Progress log.
- **Unknowns get PoC milestones.** A milestone with significant unknowns is
  first a toy implementation validating feasibility, then the real thing.
- **Resolve ambiguities autonomously.** Never stop to ask "what next?" — pick
  the reasonable path, record it in the Decision log, commit frequently.
  Escalate only true judgment calls (docs/PRODUCT_SENSE.md).
