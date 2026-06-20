---
status: stable
last_verified: 2026-06-21
owner: harness
type: design-doc
tags: [harness, plugin, docs-as-memory, self-host]
description: An overview of the installed agent-harness plugin that operates this repo, covering its docs-as-memory system, taste lints, and review personas.
---
# agent-harness — the installed harness

This repo is operated by the `agent-harness` Claude Code plugin: docs-as-memory
knowledge system, taste lints whose FAIL messages carry FIX instructions, and
review personas grounded 1:1 in docs. Session continuity uses Claude Code's
native memory (the old feeder/imprint/dream loop was retired). **Self-host**:
the machine itself lives in this repo at `plugin/`.

## Run it

- Load: `claude --plugin-dir ./plugin` from this repo's root. Session continuity
  uses Claude Code's native memory — no feeder/imprint loop. Durable knowledge:
  `docs/adr/` (decisions), `docs/exec-plans/tech-debt-tracker.md` (debt/open
  questions), `docs/logs.md` (evolution).
- Gate: `python3 plugin/scripts/check.py` must be GREEN before every commit.
  The `harness-lint` skill interprets failures.
- Navigate docs: `python3 plugin/scripts/nav.py map|roadmap|tree|relations|catalog|links|backlinks|followups|stale|orphans|drift`
  — read-only live query over the corpus (the `docs-nav` skill): `map`/`roadmap`
  for the whole picture, `tree`/`relations` for typed relationships, `followups`
  for derived work, the rest for catalog/graph/gardening. Not in the gate.
- The gate is mechanical: scaffold installs `.git/hooks/pre-commit` running
  it (`--no-verify` only for emergencies — fix forward right after).
- Tests in the gate: wired via the `HARNESS_TEST_CMD` env var (e.g.
  `HARNESS_TEST_CMD="pytest -q"`) or `.harness.json` `test_cmd`; default is
  unittest discovery when a `tests/` directory exists, skipped otherwise.
- Host enforcement: a host's own app-code invariants are mechanized by the
  `architecture-setup` skill, routed by FORM — host lints under `.claude/lints/`
  (wired via `.harness.json` `lint_cmd`) for mechanical invariants, guide-skills
  under `.claude/skills/` for methodology; a host overrides freshness and
  strictness defaults in the same file. Self-host enforces only `plugin/`+`docs/`
  (S/D lints); see
  ARCHITECTURE.md invariant 7.
- Docs governance is tiered: machine-critical docs and harness-managed roots
  (`design-docs`, `exec-plans`, `memory`, `product-specs`) are strict;
  host-owned business/marketing/research docs are flexible unless listed in
  `.harness.json` `managed_doc_roots` or the host sets
  `doc_governance: strict`.
- Plugin component inventory and coverage are self-host strict but advisory for
  external-plugin hosts unless the host opts into `.harness.json`
  `component_inventory: strict` or `component_coverage: strict`.

## Components

| Kind | Name | What it does |
|---|---|---|
| skill | `architecture-setup` | Use to set up/revise a repo's architecture & taste enforcement — derives invariants, routes |
| skill | `docs-nav` | Use when finding/orienting — the whole picture (`map`/`roadmap`), typed relationships (`tree`/`relations`), follow-ups, catalog/backlinks, stale/orphan/drift (nav.py) |
| skill | `docs-tree` | Use when adding or relocating knowledge — decides where a page belongs in the docs tree, a |
| skill | `execplan` | Use when starting non-trivial work (multi-session, ≥3 components, architecture/memory chan |
| skill | `garden` | Use periodically (or when docs feel stale) to run the entropy GC — dispatches the doc-gard |
| skill | `harness-init` | Use when setting up, installing, initializing, bootstrapping, or porting this harness into |
| skill | `harness-lint` | Use to run the deterministic gate (taste lints + structure lints + generated-file check +  |
| skill | `product-design` | Use before non-trivial work when the *what* needs settling first — writes a product spec, then hands off to execplan |
| agent | `doc-gardener` | Entropy GC persona. Dispatch periodically (garden skill) to detect code↔docs drift, golden |
| agent | `review-arch` | Architecture & design-taste review persona. Dispatch at ExecPlan completion gates with the |
| agent | `review-reliability` | Reliability review persona. Dispatch at ExecPlan completion gates with the diff range. Gro |
| agent | `review-security` | Security review persona. Dispatch at ExecPlan completion gates with the diff range. Ground |
| agent | `review-spec-compliance` | Spec-compliance review persona — always-on at every ExecPlan completion gate. Built exact |
| agent | `review-code-quality` | Code-quality review persona — always-on at every ExecPlan completion gate, after spec-com |

## Docs placement

| Knowledge kind | Home |
|---|---|
| Design rationale / principle | `docs/design-docs/` |
| Architectural invariant | `ARCHITECTURE.md` (short) or design-docs |
| Component taste rule | `docs/DESIGN.md` |
| Failure mode / idempotency rule | `docs/RELIABILITY.md` |
| Threat / mitigation | `docs/SECURITY.md` |
| Reusable how-it-works | `docs/design-docs/` |
| Decision + why | `docs/adr/` |
| Known landmine / unresolved question | `docs/exec-plans/tech-debt-tracker.md` |
| Project / docs evolution | `docs/logs.md` |
| Product behavior | `docs/product-specs/` (harness-managed by default) |
| External API facts | `docs/references/` |
| Host-specific business/marketing/curriculum/etc. | Natural `docs/<domain>/` roots chosen during `harness-init` |

Procedure for a new harness-managed page: kebab-case filename → frontmatter
(required `status / last_verified / owner / type / description`, plus `phase` on
product-specs; optional `tags / title`; validate-if-present `resource / supersedes`
per `docs/KNOWLEDGE_FORMAT.md` KF v2.0) → write → register in that
directory's `index.md` → cross-link → run the gate (the `docs-tree` skill owns
this). The format itself is specified in `docs/KNOWLEDGE_FORMAT.md` (KF v2.0).
Host-owned project roots may use the structure that best fits the repo unless
they are opted into managed governance.

## Memory — native (no loop)

The harness ships **no automatic memory loop**. Session continuity uses Claude
Code's native memory; the old feeder/imprint/dream machine (and the `docs/memory/`
tree) was **retired** (packaging Slice 1 — see `docs/logs.md`). Durable,
version-controlled knowledge lives in `docs/`:

- **Decisions + why** → `docs/adr/` (ADRs, registered in `docs/adr/index.md`).
- **Deferred work + open questions + limitations** → `docs/exec-plans/tech-debt-tracker.md`.
- **Evolution narrative** → `docs/logs.md` (milestone-grained, read on-demand).
- **Reusable how-it-works** → `docs/design-docs/`.

`garden` (entropy GC) remains a manual tool. The lints still enforce frontmatter,
naming, and index registration on every governed page.

## Growing the grounding docs

`docs/RELIABILITY.md` and `docs/SECURITY.md` start as small seeds. When a
review finding or a human correction surfaces a rule worth keeping, append it
as the next numbered rule (feedback twice → promote). Review personas cite
relevant written rules for taste/contract findings, and may also block on
demonstrable bugs with concrete evidence.
