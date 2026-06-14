"""Dev-stage taxonomy (Phase 3b): ticket type -> harness doc-pipeline workflow.

A ticket's `type` (a Linear label) maps onto a stage of the harness's OWN methodology
(AGENTS.md operating model: product-design -> spec, execplan -> plan+code). The
`TAXONOMY` registry below is the institution-as-data: each type carries the
methodology it follows (by repo path — self-hosting), the doc it emits, the child
types it decomposes into, and the prompt template the orchestrator wraps a worker's
ticket in. Routing is a pure function (`compose_worker_prompt`); decomposition is
worker-driven (the template INSTRUCTS the worker to create typed children — RV1),
and 3a's DAG sequences the result. See docs/product-specs/2026-06-14-dev-stage-taxonomy.md.
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
is too large for one plan."""

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
