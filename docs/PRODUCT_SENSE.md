---
status: stable
last_verified: 2026-06-12
owner: harness
---
# PRODUCT_SENSE.md — what this harness optimizes

The scarce resource is **human time and attention**. The product is a local
harness where big-software work proceeds with minimum human-in-loop.

## Human touchpoints (the only two)
1. Open a session and give a task.
2. (Optional) Check direction at ExecPlan milestones.

Everything else — planning, implementation, lints, persona review, doc
gardening, imprinting, dreaming — runs inside the harness.

## Escalation rule (agent-initiated)
Escalate to the human ONLY for judgment: product direction, taste tradeoffs
not covered by docs, irreversible/outward-facing actions. If a lint, test, or
documented decision answers it, proceed without asking.

## Throughput beats ceremony
Agent throughput exceeds human review capacity. Prefer short-lived changes,
fix-forward, and mechanical gates over human approval steps.
