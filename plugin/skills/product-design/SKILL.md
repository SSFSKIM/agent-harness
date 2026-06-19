---
name: product-design
description: Use before non-trivial work when the *what* deserves settling before the *how* — requirements that outlive a single plan, fan out across linked plans, or are rich/contested enough to verify independently. Writes a product spec, then hands off to execplan.
---
# Product Design procedure

The spec-first entry mode of the methodology. Read the **Entry decision** in
`docs/PLANS.md` first — if the *what* is already clear enough, skip this and go
straight to the `execplan` skill.

The spec owns the **design** — what to build, why, and how it is shaped
(components, contracts, behaviors). The ExecPlan that follows owns the **build** —
executing it (order, progress, outcomes). The spec is a durable, separate
artifact (`docs/product-specs/`), not a section inside a plan — that is what lets
it outlive one plan and be referenced by several.

## Author the spec
1. **Explore first.** Read the relevant code, docs, recent commits, and the
   `product-specs/` index — understand the current state before drafting, not
   after.
2. **Scope check.** If the work spans multiple independent products/subsystems
   (each shippable and verifiable alone), decompose into separate specs (one per
   piece, this one as the parent index) before refining — don't spec a thing
   that should be several. When this is the **parent**, tag each child with its
   phase/slice as a structured field so the roadmap/status is a *derived view*
   (group-by), never hand-maintained; and this recurses — a child too big
   decomposes the same way. Don't build a separate spec-hierarchy system for it.
3. Draft autonomously — your own reasoning, not a human dialogue. Be concrete:
   name real components, interfaces, behaviors, and files — a requirement so
   vague it could be built two ways is a spec failure. Scale each section to its
   complexity. Fill:
   - **Problem** — what is unsatisfied today, in observable terms.
   - **Requirements** — R1..Rn, each independently verifiable ("a human can
     check X"), not implementation steps.
   - **Design** (for system/code features; scale down or skip for a pure
     policy/methodology doc) — the components and their responsibilities, the
     contracts/interfaces between them, key behaviors, how errors, edge cases,
     and integration points are handled, and how the design will be **verified**
     (testability — name the seams that make behavior checkable). Keep units
     **isolated and legible**: each has one clear purpose behind a contract a
     consumer can use without reading its internals and whose internals can
     change without breaking consumers — a unit that resists this, or a file
     grown large enough to do too much, is a design smell to fix here. Name the
     files to create/modify when in a codebase. Design-level, not code or task
     steps — those are the ExecPlan's.
   - **Non-goals** — what this explicitly does not do (scope fence). **YAGNI —
     cut every requirement not needed now**; a smaller spec is a better spec.
   - **Acceptance criteria** — the demonstrable conditions for "spec satisfied".
4. **Human touch lands here, and only here.** First **enumerate** the open
   factors the spec leaves unsettled, then **triage** each: a
   mechanical/technical one — a best answer exists on the merits — you decide
   yourself and record; a genuine product-direction / taste fork (the kind
   PRODUCT_SENSE.md reserves for the human) you escalate — never "what next?".
   This includes a **design-approach** fork: surface ≥2 approaches only when
   they are genuinely valid and attractive and the choice turns on taste/product
   judgment, not when one is technically best — don't manufacture alternatives
   to look thorough; pick the clear winner and move on. When you do escalate,
   ask one focused, preferably multiple-choice question, and record the
   resolution back into the spec.
5. **Self-review before handoff** (fix inline): completeness (no TBD / vague
   requirement), coverage (error handling, edge cases, integration points
   addressed), internal consistency (no requirement or design element
   contradicts another; acceptance matches requirements), scope (still one
   product?), ambiguity (each requirement reads exactly one way), YAGNI. Flag
   only what would make someone build the wrong thing or write a flawed plan —
   not "this section is less detailed than that one". Catching a bad spec here
   is far cheaper than after an ExecPlan is built on it.
6. Write to `docs/product-specs/YYYY-MM-DD-<slug>.md` with frontmatter
   (`status / last_verified / owner / type: product-spec / description / phase`
   — a spec is gate-required to declare `type`, a one-line `description`, and a
   `phase: <initiative>/<NN>-<slug>` anchoring it on the roadmap, KF v2.0 D11),
   register in `product-specs/index.md`, and cross-link. The `docs-tree` skill owns
   the placement mechanics; run the gate.

## Hand off to ExecPlan
7. Enter the `execplan` skill. The ExecPlan links this spec in its Context and
   builds from its design — its Approach/Assumptions/Milestones cover execution
   choices not already settled in the spec, and it does **not** re-derive the
   spec. If the spec spans independent subsystems, the scope check (PLANS.md)
   splits it into linked ExecPlans, all referencing this spec.
