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
1. **Explore first.** Read the relevant code, docs, recent commits, and the
   `product-specs/` index — understand the current state before drafting, not
   after.
2. **Scope check.** If the work spans multiple independent products/subsystems
   (each shippable and verifiable alone), decompose into separate specs (one per
   piece, this one as the parent index) before refining requirements — don't
   spec a thing that should be several.
3. Draft autonomously — this is your own reasoning, not a human dialogue. Fill:
   - **Problem** — what is unsatisfied today, in observable terms.
   - **Requirements** — R1..Rn, each independently verifiable ("a human can
     check X"), not implementation steps. Keep the *how* out — that is the
     ExecPlan's job.
   - **Non-goals** — what this explicitly does not do (scope fence). **YAGNI —
     cut every requirement not needed now**; a smaller spec is a better spec.
   - **Acceptance criteria** — the demonstrable conditions for "spec satisfied".
4. **Human touch lands here, and only here.** Resolve ambiguities autonomously
   and record the choice. Escalate ONLY a genuine product-direction / taste
   fork (the kind PRODUCT_SENSE.md reserves for the human) — never "what next?".
   When you do escalate, ask one focused, preferably multiple-choice question.
   Record the resolution back into the spec.
5. **Self-review before handoff** (fix inline): placeholder scan (no TBD / vague
   requirement), internal consistency (no requirement contradicts another;
   acceptance criteria match the requirements), scope (still one product?),
   ambiguity (each requirement reads exactly one way). Catching a bad spec here
   is far cheaper than after an ExecPlan is built on it.
6. Write to `docs/product-specs/YYYY-MM-DD-<slug>.md` with frontmatter
   (`status / last_verified / owner`), register in `product-specs/index.md`, and
   cross-link. The `docs-tree` skill owns the placement mechanics; run the gate.

## Hand off to ExecPlan
7. Enter the `execplan` skill. The ExecPlan links this spec in its Context and
   does **not** re-derive the requirements — its Approach/Assumptions/Milestones
   cover only the "how". If the spec spans independent subsystems, the scope
   check (PLANS.md) splits it into linked ExecPlans, all referencing this spec.
