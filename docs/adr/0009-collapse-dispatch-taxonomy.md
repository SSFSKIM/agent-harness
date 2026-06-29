---
status: accepted
last_verified: 2026-06-28
owner: harness
type: adr
tags: [taxonomy, dispatch, ticket, worker, autonomy, simplification]
description: "Collapse the 5-value dev-stage ticket taxonomy (planning/research/design/spec/impl) to a single agent-ready dispatch-admission label, default on. The taxonomy's only runtime use was the dispatch gate — DAG sequencing is pure blocked_by, child_types was dead metadata, and the stage labels never shaped the prompt (ADR 0005). Supersedes the dispatch/DAG-metadata clause of 0005."
---
# Collapse the dispatch taxonomy to a single `agent-ready` label

## Decision

The Director admits a ready ticket for dispatch **iff it carries one label — `agent-ready`**
(`orchestrator.DISPATCH_LABEL`). The gate is **on by default**: `dispatch_requires_label`
flips `False → True` (a host can still opt out to dispatch every ready ticket).

We **delete** the 5-value dev-stage taxonomy — `planning / research / design / spec / impl` —
and its code: `TAXONOMY`, `ticket_type`, `_PRIORITY`, `child_types`, and the now-trivial
`compose_worker_prompt` (the orchestrator inlines the ticket's own prompt). `director/taxonomy.py`
is retained only as the home of `WORKER_PROTOCOL` + `TERMINAL_CONTRACT` + `frame_first_turn`
(a rename to `worker_protocol` is a deferred cosmetic follow-up).

## Why

[[0005-no-stage-prompt-templates]] kept the dev-stage label "as dispatch/DAG metadata only."
A trace of every consumer (the worker-policy-polish investigation) showed that claim no longer
earns its structure:

- **DAG sequencing never read the type.** `eligible_tickets` orders purely on each blocker's
  board `state_type` (the explicit `blocked_by` edges) — never on `ticket_type`. The stage
  label only *annotated* nodes for human reading; it did not sequence them.
- **`child_types` was dead metadata** — defined, tested for shape, read by nothing at runtime.
- **The label never shaped the prompt** (0005 already established this — the worker's
  methodology surface is `WORKER_PROTOCOL` + `AGENTS.md` + invocable skills, chosen by its
  own judgment).

So the taxonomy's *entire* runtime footprint was one line: "is this ticket typed?", used as a
dispatch-admission gate. A 5-value vocabulary for a boolean question is over-structuring. Worse,
it forces the wrong moment of decision: pre-labeling a ticket `research` vs `impl` is a human's
upfront guess at HOW the work will go — when the worker, an LLM holding the whole methodology
surface, right-sizes that better at execution time. This is the same trust-the-worker principle
behind 0005's template removal and the decider's "self-resolve and continue" default.

A ticket should carry the **goal**; *whether* an agent should pick it up is the one bit a human
still owns, and `agent-ready` expresses exactly that bit. HOW to do it — research, spec design,
an ExecPlan, or a direct patch — is the worker's call, via `AGENTS.md` + skills.

> **Ownership reframed 2026-06-29 by [[0011-agent-ready-is-agent-governed]]:** "the one bit a
> human still owns" reads too strong against the project's least-human-in-loop north star.
> `agent-ready` is an **agent-governed readiness signal** — the Director and Partner set it
> autonomously (most tickets `agent-ready`); the human curates at the *edges* (remove it to
> veto/pause, redirect), not as a per-ticket admission gate. The gate *mechanism* below
> (default-on, `eligible_tickets(require_label=True)`) is unchanged — only this framing flips.

## Default on

The F1 shakedown bug (the Director ran Linear's default onboarding issues as ~700k-token
workers) was fixed by an *opt-in* gate. With a single explicit opt-in label the safe default
inverts: **dispatch nothing unless a human tagged it `agent-ready`**. Untagged tickets —
onboarding junk, half-shaped human WIP — are ignored out of the box. A host that wants the old
permissive "dispatch every ready ticket" sets `dispatch_requires_label: false`.

## Consequences / migration

- **Hosts must tag dispatchable tickets `agent-ready`.** A board relying on the old 5 stage
  labels, or on default-off dispatch-all, will dispatch **nothing** until tickets are tagged
  (or the host opts out). This is the intended, fail-safe direction.
- Workers issue child tickets labeled `agent-ready` (`WORKER_PROTOCOL` updated) so spawned
  follow-ups / size-splits are picked up by the gate.
- Stage labels are not *forbidden* — a human may still tag `research`/`spec` on Linear for
  their own board organization; the code simply ignores them now.

## Supersedes

The "dev-stage **label / `ticket_type` stays — as metadata only**: the dispatch filter and the
typed DAG (`blocked_by` sequencing + observability)" clause of [[0005-no-stage-prompt-templates]].
The rest of 0005 — no per-stage prompt templates; `WORKER_PROTOCOL` + `AGENTS.md` is the whole
methodology surface — **stands**. This ADR extends 0005's trust-the-worker logic from the prompt
to the dispatch label.
