"""Dev-stage taxonomy (Phase 3b): ticket type -> harness doc-pipeline workflow.

A ticket's `type` (a Linear label) maps onto a stage of the harness's OWN methodology
(AGENTS.md operating model: product-design -> spec, execplan -> plan+code). The
`TAXONOMY` registry below is the institution-as-data: each type carries the
methodology it follows (by repo path — self-hosting), the doc it emits, the child
types it decomposes into, and the prompt template the orchestrator wraps a worker's
ticket in. Routing is a pure function (`compose_worker_prompt`); decomposition is
worker-driven (the template INSTRUCTS the worker to create typed children — RV1),
and 3a's DAG sequences the result. See docs/product-specs/2026-06-14-dev-stage-taxonomy.md.

Beyond the per-stage template, every worker's FIRST-turn prompt is framed
(`frame_first_turn`) with two stage-agnostic blocks: the `WORKER_PROTOCOL` operating
disciplines and the `TERMINAL_CONTRACT` (graduated-autonomy slice 1, gap #5; ADR 0002).
"""
from __future__ import annotations

_PLANNING_TEMPLATE = """\
You are a PLANNING worker for ticket {identifier}. Decompose the goal below into a
DAG of typed child tickets — do NOT implement. Follow the harness operating model in
AGENTS.md and the entry decision in docs/PLANS.md. For each sub-piece, create a child
ticket labeled with the right next stage (one of: research, design, spec) and
blocked_by {identifier}, using the linear skill (linear_graphql). Leave a brief
decomposition note on this ticket."""

_RESEARCH_TEMPLATE = """\
You are a RESEARCH worker for ticket {identifier}. Investigate the open question below
and produce a research digest under docs/references/ following docs/references/index.md
conventions; cite sources. This is usually a leaf — create a child ticket only if
further research is genuinely needed (labeled research, blocked_by {identifier})."""

_DESIGN_TEMPLATE = """\
You are a DESIGN worker for ticket {identifier}. Produce an architecture/design doc
under docs/design-docs/, grounded in docs/design-docs/core-beliefs.md and
ARCHITECTURE.md. Then, for each piece that needs a product-spec, create a child ticket
labeled spec and blocked_by {identifier}, using the linear skill."""

_SPEC_TEMPLATE = """\
You are a SPEC worker for ticket {identifier}. Follow the product-design procedure in
plugin/skills/product-design/SKILL.md (and the entry decision in docs/PLANS.md) to
write a product-spec at docs/product-specs/YYYY-MM-DD-<slug>.md. Then create impl child
tickets (labeled impl, blocked_by {identifier}) for the build, using the linear skill."""

_IMPL_TEMPLATE = """\
You are an IMPL worker for ticket {identifier}. Follow the execplan procedure in
plugin/skills/execplan/SKILL.md (and docs/PLANS.md, docs/DESIGN.md): write a living
ExecPlan under docs/exec-plans/active/, implement it, keep
`python3 plugin/scripts/check.py` GREEN, and run the completion gate. Split off
additional impl child tickets (labeled impl, blocked_by {identifier}) only if the work
is too large for one plan.

If the ticket has a PR already attached when you start (rework/feedback loop), run the
PR FEEDBACK SWEEP (below) FIRST and address it before any new feature work.

Reproduction-first: before changing code, reproduce and capture the current
behavior/issue signal (a command + its output, or a deterministic behavior) and record
it in the ExecPlan Notes so the fix target is explicit. If the ticket carries
`Validation`/`Test Plan`/`Testing` sections, mirror them into the ExecPlan as
non-negotiable acceptance checkboxes and execute them before done. Temporary local proof
edits to validate an assumption are fine, but revert every such proof edit before commit
and document it in the ExecPlan.

Before you finish — SELF-QA (your own responsibility; this is NOT a gate, and the
PR-merger does only a thin integration check later): (1) keep the host gate GREEN;
(2) self-review spec-compliance (does the build match the spec/ticket?) and code-quality;
(3) write and run task-specific tests for what you built — follow the `qa` skill:
smoke/unit always, plus end-to-end via `playwright`/`playwright-cli` for UI work (graceful
fallback to smoke/unit where no browser is available); (4) open a PR with the `push` skill
whose body states WHAT spec/feature you built, WHICH reviews you ran, and WHICH tests you
wrote and their results — the PR-merger reads this; (5) PR FEEDBACK SWEEP — after opening
the PR and before report_outcome(done), gather the PR's checks and every comment channel
(top-level comments, inline review comments, bot reviews, review summaries via `gh`) and
treat each actionable item as blocking until it is addressed by a code/test/docs change
OR an explicit, justified pushback reply on that thread; re-run validation after changes
and repeat the sweep until nothing actionable is outstanding and checks are green. Only
then call report_outcome(done)."""

# institution-as-data: type -> stage workflow. child_types encodes the decomposition
# policy (the pipeline planning -> {research,design} -> spec -> impl).
TAXONOMY: dict[str, dict] = {
    "planning": {
        "label": "planning",
        "stage": "decompose a goal into a typed ticket DAG",
        "methodology_refs": ["AGENTS.md", "docs/PLANS.md"],
        "output": "decomposition note + typed child tickets",
        "child_types": ["research", "design", "spec"],
        "template": _PLANNING_TEMPLATE,
    },
    "research": {
        "label": "research",
        "stage": "investigate an unknown",
        "methodology_refs": ["docs/references/index.md"],
        "output": "research digest (docs/references/)",
        "child_types": [],
        "template": _RESEARCH_TEMPLATE,
    },
    "design": {
        "label": "design",
        "stage": "architecture / high-low design",
        "methodology_refs": ["docs/design-docs/core-beliefs.md", "ARCHITECTURE.md"],
        "output": "design doc (docs/design-docs/)",
        "child_types": ["spec"],
        "template": _DESIGN_TEMPLATE,
    },
    "spec": {
        "label": "spec",
        "stage": "product design (the what)",
        "methodology_refs": ["plugin/skills/product-design/SKILL.md", "docs/PLANS.md"],
        "output": "product-spec (docs/product-specs/)",
        "child_types": ["impl"],
        "template": _SPEC_TEMPLATE,
    },
    "impl": {
        "label": "impl",
        "stage": "implementation (the build)",
        "methodology_refs": ["plugin/skills/execplan/SKILL.md", "docs/PLANS.md", "docs/DESIGN.md"],
        "output": "exec-plan (docs/exec-plans/) + code",
        "child_types": [],  # leaf by default; may split into more impl
        "template": _IMPL_TEMPLATE,
    },
}

# Most-specific-first: a ticket carrying several stage labels routes to the latest stage.
_PRIORITY = ["impl", "spec", "design", "research", "planning"]

# The multi-turn TERMINAL CONTRACT injected into every worker's first-turn prompt
# (multi-turn-ticket-execution slice). Without it a worker that finishes its work but
# never calls `report_outcome` is read un-watched as "still continuing" and loops to
# `stuck` (a finished ticket mis-reported). This tells the worker, where it reliably
# reads it, that signalling terminal is ITS job and how. Pairs with the report_outcome
# tool `drive` advertises — so `drive` (not compose_worker_prompt) injects it, covering
# the orchestrator, run.main, and direct-drive paths alike.
TERMINAL_CONTRACT = """\
This ticket may take several turns on one thread; keep working across turns until the \
work is genuinely done — do not stop merely because a turn ends. YOU signal the \
terminal outcome by calling the `report_outcome` tool, and only when the work truly ends:
- done — the ticket is fully complete: report_outcome(status="done", reason="…").
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


# The stage-agnostic WORKER OPERATING PROTOCOL injected into every worker's first-turn
# prompt (graduated-autonomy slice 1, gap #5). These two disciplines hold for ALL five
# stages; the four impl-specific disciplines (reproduction-first, acceptance mirroring,
# temp-proof revert, PR feedback sweep) live in _IMPL_TEMPLATE, not here. Harvested from
# docs/symphony-original/WORKFLOW.md's stage-agnostic craft (NOT its lifecycle/board
# steps — our orchestrator/merger own those). See docs/memory/adr/0002-graduated-autonomy.md
# + docs/product-specs/2026-06-17-worker-operating-protocol.md.
WORKER_PROTOCOL = """\
These hold for every stage, on every turn:
- Single living source of truth. Your stage's output doc (research digest, design doc, \
product-spec, or ExecPlan) is the canonical home for your plan and progress narrative. \
Maintain it in place as you work — check items off and record decisions and surprises \
the moment they happen, and keep that single canonical progress note rather than \
fragmenting it across many separate notes or comments.
- No scope-creep. If you discover meaningful work outside this ticket's scope, do NOT \
expand the ticket. File a separate typed child ticket (labeled with the right stage, \
blocked_by/related to this one as appropriate) using the linear skill, note it, then \
stay on the current scope."""


def frame_first_turn(prompt: str) -> str:
    """Frame a worker's FIRST-turn prompt with the two stage-agnostic protocol blocks
    every dispatch path needs: the WORKER PROTOCOL (operating disciplines) then the TURN
    PROTOCOL (terminal contract). Injected once in `run.drive`, so the orchestrator,
    run.main, and direct-drive callers all receive it via the single seam. Delegates the
    terminal block to `with_terminal_contract` (kept byte-stable)."""
    framed = f"{prompt}\n\n---\nWORKER PROTOCOL\n{WORKER_PROTOCOL}"
    return with_terminal_contract(framed)


def ticket_type(ticket: dict) -> str | None:
    """The dev-stage type of a ticket from its labels, or None (untyped) if it carries
    no stage label. Multiple stage labels resolve by _PRIORITY (most specific first)."""
    labels = set(ticket.get("labels") or [])
    for t in _PRIORITY:
        if TAXONOMY[t]["label"] in labels:
            return t
    return None


def compose_worker_prompt(ticket: dict) -> str:
    """The prompt a worker receives for this ticket: the type's stage-workflow template
    (methodology refs + output path + typed-child-creation instruction) wrapped around
    the ticket's own task. An untyped ticket gets its raw prompt unchanged (backward
    compatible with the pre-3b orchestrator)."""
    t = ticket_type(ticket)
    base = ticket.get("prompt", "")
    if t is None:
        return base
    identifier = ticket.get("identifier") or ticket.get("id") or "this ticket"
    return TAXONOMY[t]["template"].format(identifier=identifier) + "\n\nTASK:\n" + base
