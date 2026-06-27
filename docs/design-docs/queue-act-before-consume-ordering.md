---
status: stable
last_verified: 2026-06-28
owner: review-reliability
type: knowledge
tags: [director, queue, reliability, idempotency]
description: In the Director queue, do the durable side-effect BEFORE consuming/answering the item — consuming first means a crash in the window between drops the side-effect silently while the item is already gone, unrecoverable.
---
# Queue: act before consume

A field note promoted from session memory. Generalized into the gate's reliability
rules as **R19** in [`RELIABILITY.md`](../RELIABILITY.md), and cited by the
operator-console product-spec.

When code pairs a **durable side-effect** with **consuming a Director-queue item**
(writing the item's answer, which removes it from the pending set), do the
side-effect **first** and consume only after it succeeds. Consuming first means a
crash/raise in the window between the two **drops the side-effect silently while
the item is already gone — unrecoverable**.

**Why:** the queue answer is the "handled/consumed" marker (atomic temp+rename),
but the *pairing order* is the bug surface, not the write itself.

## How to apply

- On a non-merged drain, surface the escalation *before* consuming; on a requeue,
  append the next-attempt request *before* answering the prior one.
- If the side-effect raises, **leave the item pending** (don't consume) so it is
  retried; a dedup on the side-effect is an idempotent no-op, not a re-consume.
- Mirror this for any new consume+act pair on the queue (`director/queue`,
  `director/merger`, `director/director_min`).

This bug class was caught by the codex completion-gate reviewer **twice** in the
serialized-merge work and **never** showed in the green unit gate — a crash-window
ordering bug a normal test won't surface. Treat it as a standing invariant. It is
the other "the green gate won't catch this" hazard alongside
[parallel sessions share one master index](parallel-sessions-share-master-index.md).
