---
name: docs-tree
description: Use when adding or relocating knowledge — decides where a page belongs in the docs tree, applies frontmatter, registers it in the right index.
---
# Docs tree placement

The `docs/` tree IS the memory (one brain — `docs/design-docs/memory-architecture.md`).
This is the same taxonomy the dreaming router applies; route each atomic claim to
exactly one home.

| Knowledge kind | Home |
|---|---|
| Design rationale / principle / reusable how-it-works | `docs/design-docs/` |
| Architectural invariant | `ARCHITECTURE.md` (short) or design-docs |
| Decision + why | the relevant design-doc's `## Decision log` (or a design-doc ADR page) |
| Unresolved question | the relevant design-doc's `## Open decisions` |
| Known landmine / limitation / debt | `docs/exec-plans/tech-debt-tracker.md` (a row) |
| Failure mode / idempotency rule | `docs/RELIABILITY.md` |
| Threat / mitigation | `docs/SECURITY.md` |
| Component taste rule | `docs/DESIGN.md` |
| Product behavior | `docs/product-specs/` |
| External API digest | `docs/references/` (llms.txt style, vendored) |
| Episodic / provenance / no clear home | `docs/journal/YYYY-MM.md` (append-only) |

Procedure: kebab-case filename → frontmatter (`status / last_verified /
owner`) → write the page → register in that directory's `index.md` →
cross-link related pages → run the gate (command in
`docs/design-docs/agent-harness.md`).
