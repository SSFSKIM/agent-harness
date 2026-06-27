"""Worker first-turn framing: the operating + terminal contracts (ADR 0005, ADR 0009).

This module owns the two stage-agnostic blocks injected into every worker's FIRST-turn
prompt by `frame_first_turn`: `WORKER_PROTOCOL` (the single, always-injected operating
contract — the analog of Symphony's `WORKFLOW.md`, carrying the implementation craft) then
the `TERMINAL_CONTRACT` (how/when to call `report_outcome`). The worker's full methodology
surface is exactly these two PLUS the host's auto-loaded `AGENTS.md` and its invocable skills
(product-design / execplan / …), which the worker consults and calls by its own judgment —
there are no per-stage prompt templates (ADR 0005).

The dev-stage taxonomy (a 5-value `planning/research/design/spec/impl` label → DAG metadata)
was REMOVED by ADR 0009: its only runtime use was the dispatch gate (DAG sequencing is pure
`blocked_by`; the stage labels never shaped the prompt or sequencing), so it collapsed to a
single `agent-ready` admission label (`orchestrator.DISPATCH_LABEL`). HOW to do the work —
research, spec, ExecPlan, or a direct patch — is the worker's judgment, not a label.

See docs/adr/0009-collapse-dispatch-taxonomy.md (supersedes the dispatch/DAG-metadata clause
of 0005) and docs/adr/0005-no-stage-prompt-templates.md. (The module name is historical —
it no longer holds a taxonomy; a rename to `worker_protocol` is a deferred cosmetic follow-up.)
"""
from __future__ import annotations

# The multi-turn TERMINAL CONTRACT injected into every worker's first-turn prompt
# (multi-turn-ticket-execution slice). Without it a worker that finishes its work but
# never calls `report_outcome` is read un-watched as "still continuing" and loops to
# `stuck` (a finished ticket mis-reported). This tells the worker, where it reliably
# reads it, that signalling terminal is ITS job and how. Pairs with the report_outcome
# tool `drive` advertises — so `drive` injects it (via `frame_first_turn`), covering
# the orchestrator, run.main, and direct-drive paths alike.
TERMINAL_CONTRACT = """\
This ticket may take several turns on one thread; keep working across turns until the \
work is genuinely done — do not stop merely because a turn ends. YOU signal the \
terminal outcome by calling the `report_outcome` tool, and only when the work truly ends:
- done — the ticket is fully complete: report_outcome(status="done", reason="…"). If \
you filed non-blocking follow-up tickets while working (deferred/out-of-scope work, \
tech debt, extra hardening), include their ids in spawned_ticket_ids so they surface \
on the board.
- blocked — you cannot proceed and have filed follow-up child tickets: \
report_outcome(status="blocked", reason="…", spawned_ticket_ids=["…"]).
- needs_human — a product/taste decision is genuinely required: \
report_outcome(status="needs_human", reason="…").
Do NOT call report_outcome to ask whether to continue. If you need to pause and ask, \
just end your turn with the question — you will receive a directive and continue on the \
same thread. Call report_outcome exactly once, at the end."""


def with_terminal_contract(prompt: str) -> str:
    """Append the multi-turn TERMINAL CONTRACT to a worker's first-turn prompt, so the
    worker knows it must call `report_outcome` when (and only when) its work ends."""
    return f"{prompt}\n\n---\nTURN PROTOCOL\n{TERMINAL_CONTRACT}"


# The WORKER OPERATING PROTOCOL — the single, always-injected operating contract (ADR 0005,
# the analog of Symphony's WORKFLOW.md). It carries the stage-agnostic disciplines (gap #5 /
# ADR 0002) AND the implementation craft (folded in from the retired `_IMPL_TEMPLATE` — ADR
# 0005), phrased CONDITIONALLY ("when you implement / open a PR") since a purpose-unit ticket
# (ADR 0004) normally includes the build. It is host-AGNOSTIC on purpose: it names disciplines
# and the worker's own tools (`pull`/`push`/`gh`/`playwright`), never host methodology paths or
# a specific gate command — routing to product-design vs an ExecPlan, and the host's gate, are
# the host's AGENTS.md + skills (auto-loaded), the worker's judgment, NOT injected here.
WORKER_PROTOCOL = """\
These hold on every turn:
- Single living source of truth. Your working doc (whatever the host's methodology uses — a \
research digest, design doc, product-spec, or ExecPlan) is the canonical home for your plan \
and progress narrative. Maintain it in place as you work — check items off and record \
decisions and surprises the moment they happen, and keep that single canonical progress note \
rather than fragmenting it across many separate notes or comments.
- One canonical board comment, mirroring that doc. So the human curating the board sees \
your progress without opening repo docs, keep exactly ONE comment on this ticket as a \
board-visible mirror of the source-of-truth narrative. Lead it with the exact marker \
line `## 🤖 Worker Progress` so you can find it again: create it once (commentCreate), \
and on every later update — including after a retry that starts a fresh session — read \
the ticket's comments, find the one beginning with that marker, and edit it in place \
(commentUpdate) rather than adding a second. It mirrors the doc; it is not a competing \
second narrative.
- You propose state, you do not set it. Never transition this ticket between board \
states yourself (issueUpdate is not yours — it will be refused). Report your terminal \
outcome with report_outcome (done/blocked/needs_human) and the orchestrator moves the \
board.
- A ticket is one purpose; keep the whole pipeline inside it. Do NOT split a ticket by \
stage. You issue a NEW ticket on exactly two triggers, and otherwise stay on this one: \
(1) genuine size — the work divides into independently shippable sub-projects/slices, \
each its own spec→ExecPlan cycle, as a child ticket blocked_by this one; or (2) deferred \
work surfaced while working — out of scope, OR in-scope tech debt / additional production \
tests / hardening whose inline fix would break your momentum. Anything smaller stays in \
this ticket's scope. Every ticket you issue must be self-contained: a clear title, a \
description of the work, acceptance criteria, and provenance — link the parent ticket and \
the source doc (spec / design / research) it derives from — so a fresh worker can start \
from the ticket alone. Create it with the linear skill, labeled `agent-ready` (so the \
orchestrator will pick it up) and blocked_by/related to this one, and note it.
- Proportional context — orient only as much as THIS ticket needs. Do NOT survey the whole \
repo for a focused change. Orientation is a tool, not a mandatory step: for a broad or \
unfamiliar change the `docs-nav` skill (`nav.py map`/`catalog`/`tree`/`backlinks`) surfaces \
repo structure and status on demand; for a small, well-scoped change skip the survey and go \
straight to the work. And keep your working context lean — do not re-read files or re-run \
commands whose output you already have, and never pull a large command/test log back into \
context (capture the pass/fail signal, not the whole log). Re-sent context is the dominant \
cost of a turn, so reading less IS working cheaper.
- When you implement and open a PR (most purpose-unit tickets carry a build): \
**Reproduce first** — before changing code, capture the current behavior/issue signal (a \
command + its output, or a deterministic behavior) and record it in your working doc, so the \
fix target is explicit. \
**Sync before substantial work** — bring your base up to origin/main (the `pull` skill) and \
record the result (merge source, clean/conflicts-resolved, resulting HEAD), so a stale base \
doesn't surface conflicts late. **Mirror acceptance** — if the ticket carries \
Validation/Test Plan/Testing sections, mirror them into your working doc as non-negotiable \
acceptance checkboxes and run them before done. **Revert proof edits** — temporary local \
edits to validate an assumption are fine, but revert every one before commit and note it in \
your working doc. **Self-QA** (your responsibility, not a gate; the \
merger does only a thin integration check later): keep the host's gate/CI green (run the full \
gate once near completion + after a real change, targeted checks while iterating — don't \
re-burn the whole gate after every edit); self-review spec-compliance and code-quality; write \
and run task-specific tests (smoke/unit always, end-to-end via `playwright`/`playwright-cli` \
for UI, graceful fallback where no browser exists). **Open the PR** with the `push` skill; its \
body states WHAT you built, WHICH reviews you ran, and WHICH tests you wrote + their results. \
**PR feedback sweep** before report_outcome(done): gather the PR's checks and every comment \
channel (top-level, inline review, bot, summaries via `gh`); treat each actionable item as \
blocking until addressed by a code/test/docs change OR a justified pushback reply; re-run \
validation and repeat until nothing is outstanding and checks are green. Explicitly RESOLVE \
each thread you address (a reply alone does not resolve it; the merger refuses to land with \
unresolved threads). Report the sweep's result as structured report_outcome evidence — \
checks_state, unresolved_threads (0 when resolved), acceptance_verified — which the merger \
re-verifies independently. **Rework** — if a ticket arrives with a PR already attached: \
incremental review feedback → run the sweep first; but if the APPROACH itself was rejected \
(not line edits) → RESET, not patch: close the existing PR, branch fresh from origin/main, \
write a fresh plan, proceed as a new attempt."""


def frame_first_turn(prompt: str) -> str:
    """Frame a worker's FIRST-turn prompt with the two stage-agnostic protocol blocks
    every dispatch path needs: the WORKER PROTOCOL (operating contract) then the TURN
    PROTOCOL (terminal contract). Injected once in `run.drive`, so the orchestrator,
    run.main, and direct-drive callers all receive it via the single seam. Delegates the
    terminal block to `with_terminal_contract` (kept byte-stable)."""
    framed = f"{prompt}\n\n---\nWORKER PROTOCOL\n{WORKER_PROTOCOL}"
    return with_terminal_contract(framed)
