---
status: stable
last_verified: 2026-06-12
owner: harness
type: methodology
tags: [product-sense, human-attention, harness]
description: What the harness optimizes for, treating human time and attention as the scarce resource that big-software work should consume minimally.
---
# PRODUCT_SENSE.md — what this harness optimizes

The scarce resource is **human time and attention**. The product is a local
harness where big-software work proceeds with minimum human-in-loop.

## Human touchpoints (the only two)
1. Open a session and give a task.
2. (Optional) Check direction at ExecPlan milestones.

Everything else — planning, implementation, lints, risk-budgeted persona
review, doc gardening — runs inside the harness.

## Escalation rule (agent-initiated)
Escalate to the human ONLY for judgment: product direction, taste tradeoffs
not covered by docs, irreversible/outward-facing actions. If a lint, test, or
documented decision answers it, proceed without asking.

## Throughput beats ceremony
Agent throughput exceeds human review capacity. Prefer short-lived changes,
fix-forward, mechanical gates, and risk-budgeted review over human approval
steps or agent ceremony.
