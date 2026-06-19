---
status: stable
last_verified: 2026-06-18
owner: harness
type: design-doc
tags: [core-beliefs, golden-rules, agent-first]
description: The agent-first golden rules that serve as defaults for the self-hosting reference repo and seed material that hosts adopt, amend, or reject at harness-init.
---
# Core beliefs (golden rules)

Agent-first operating principles. These are defaults for the self-hosting
reference repo and seed material for hosts. A host adopts, amends, or rejects
policy rules during `harness-init`; only mechanical, repeated, high-cost
violations should become blocking lints.

1. **No hand-written code.** Humans contribute prompts, reviews, and docs
   feedback — never code. All artifacts (code, docs, scripts, configs) are
   agent-written.
2. **Not in the repo = does not exist.** Knowledge in chat threads or heads is
   invisible to agents. Encode decisions as versioned repo artifacts.
3. **Map, not encyclopedia.** Entry points stay short and stable; depth lives
   behind pointers (progressive disclosure).
4. **Taste is enforced mechanically when it is truly mechanical.** Boundaries
   that are always true and cheaply decidable belong in lints; project judgment
   belongs in guide-skills, docs, or review feedback.
5. **Prefer shared utilities over hand-rolled helpers** for invariants that
   must stay centralized (within this repo: harness_lib).
6. **Parse, don't validate, at boundaries.** Hook stdin, queue entries, and
   frontmatter are parsed into known shapes before use; no YOLO data poking.
7. **Internalize dependencies.** Prefer boring tech and stdlib; reimplementing
   a small helper beats importing an opaque package.
8. **Minimal blocking gates, fix-forward.** Only deterministic checks
   (check.py) block commits. Review cost is risk-budgeted; cheap fixes beat
   long waits. Non-blocking findings go to tech-debt-tracker.md.
9. **Struggling agent = harness gap.** Diagnose the missing tool/guardrail/doc,
   encode it, retry. Never just "try harder."
10. **Feedback twice → promote to doc or lint.** The same human correction must
    never be needed a third time.
11. **Tech debt is a high-interest loan.** GC continuously (doc-gardener),
    not in big batches.
12. **Spec is a separable, risk-budgeted artifact.** When the *what* outlives a
    single plan, fans out across plans, or is rich enough to verify
    independently, it earns its own durable spec (`product-specs/`, the
    `product-design` skill); otherwise it stays a thin inline layer in the
    ExecPlan. Pick the entry mode (throwaway / Product Design / ExecPlan) by
    judgment, not a fixed gate.
13. **General by identity; harness changes propagate to the portable layer.**
    The harness exists to be a portable, adaptable substrate for *any* repo;
    this self-hosting repo (`plugin/` + its own `docs/`) is the machine's first
    host and proving ground, **not the destination**. So any change to how the
    harness *works* must land in the **portable layer** — `plugin/` code,
    `harness-init` templates, `scaffold.py` seeds, generic skills — and stay
    host-agnostic (no self-host paths; lint S7), not only in self-host `docs/`.
    **What lands only self-host does not exist for ported hosts.** Mechanize the
    propagation wherever possible (e.g. every machine doc must have a scaffold
    seed — `tests/test_scaffold.py::test_machine_docs_all_propagate_to_hosts`);
    where a check can't, it is a completion/handoff checklist item. (This rule is
    itself self-host *development* discipline — it is not a default a host project
    adopts, so it is not seeded into the host `core-beliefs.md` template.)
