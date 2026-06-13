---
name: product-design
description: Use before non-trivial work when the *what* deserves settling before the *how* — requirements that outlive a single plan, fan out across linked plans, or are rich/contested enough to verify independently. Writes a product spec, then hands off to execplan.
---
# Product Design procedure

The spec-first entry mode of the methodology. Read the **Entry decision** in
`docs/PLANS.md` first — if the *what* is already clear enough, skip this and go
straight to the `execplan` skill.

The spec owns "what/why"; the ExecPlan that follows owns "how". The spec is a
durable, separate artifact (`docs/product-specs/`), not a section inside a plan —
that is what lets it outlive one plan and be referenced by several.

## Author the spec
1. Draft autonomously — this is your own reasoning, not a human dialogue. Fill:
   - **Problem** — what is unsatisfied today, in observable terms.
   - **Requirements** — R1..Rn, each independently verifiable ("a human can
     check X"), not implementation steps.
   - **Non-goals** — what this explicitly does not do (scope fence).
   - **Acceptance criteria** — the demonstrable conditions for "spec satisfied".
2. **Human touch lands here, and only here.** Resolve ambiguities autonomously
   and record the choice. Escalate ONLY a genuine product-direction / taste
   fork (the kind PRODUCT_SENSE.md reserves for the human) — never "what next?".
   Record the resolution back into the spec.
3. Write to `docs/product-specs/YYYY-MM-DD-<slug>.md` with frontmatter
   (`status / last_verified / owner`), register in `product-specs/index.md`, and
   cross-link. The `docs-tree` skill owns the placement mechanics; run the gate.

## Hand off to ExecPlan
4. Enter the `execplan` skill. The ExecPlan links this spec in its Context and
   does **not** re-derive the requirements — its Approach/Assumptions/Milestones
   cover only the "how". If the spec spans independent subsystems, the scope
   check (PLANS.md) splits it into linked ExecPlans, all referencing this spec.
