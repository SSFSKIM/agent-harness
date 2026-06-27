---
status: stable
last_verified: 2026-06-28
owner: harness
type: knowledge
tags: [director, worker, autonomy, security]
description: Don't revive headless `claude -p` (a discarded/dormant pattern); the Director is the watched main session, and the worker (Codex) self-approves its own command/file actions per its approvalPolicy/sandbox — the Director is not the per-action security approver.
---
# No headless Director; the worker owns per-action approval

A field note promoted from session memory and treated as a **standing design
decision** — it is cited as non-superseded by
[ADR 0003 (lights-out Director)](../adr/0003-lights-out-director.md).

Headless `claude -p` is a **discarded/dormant** pattern in this repo — its only
uses belonged to the memory loop that `ARCHITECTURE.md` marks DISABLED. There is
no live headless path. Don't reach for it as a "headless judge" for escalation, or
as the foundation of an "autonomous un-watched Director" (that reproduces the
retired imprint single-flight + spawn pattern).

## The real Director ↔ Worker division (verify before designing un-watched anything)

- **The worker self-approves** command/file actions *inside its sandbox* per its
  `approvalPolicy` / `sandbox` (set in `director/worker/app_server.py` at
  `thread_start`; conservative defaults). Only genuine escalations
  (sandbox-escape) or real user-input questions reach the seam → Director. So the
  **Director is not the per-action security approver — the worker is.**
- The Director's legit roles: orchestration (issue/manage tickets), answering the
  rare genuine question, and the **Linear-write guardrail** — legit precisely
  because the worker's `linear_graphql` uses the *host's* key, which is outside
  the worker's sandbox, so only the host can bound it.

## How to apply

The lever for un-watched autonomy is **tuning the worker's approvalPolicy /
sandbox** (loosen → fewer Director round-trips), **not** spawning a second
headless agent. A conservative default makes "throughput dies when the human
leaves" look like a Director problem when it is a worker-policy setting. Keep the
Director the **watched main session**.

> **Boundary the decision draws (per ADR 0003):** a *daemonized Claude Code* main
> session — event-woken, always-ready, still able to receive human messages — is
> **not** the rejected pattern. This memory rejects a stateless per-event
> subprocess used as a security *approver*; a stateful session that is the *taste
> judge* still satisfies "keep the Director the watched main session."
