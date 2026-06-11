---
name: docs-tree
description: Use when adding or relocating knowledge — decides where a page belongs in the docs tree, applies frontmatter, registers it in the right index.
---
# Docs tree placement

| Knowledge kind | Home |
|---|---|
| Design rationale / principle | `docs/design-docs/` |
| Architectural invariant | `ARCHITECTURE.md` (short) or design-docs |
| Failure mode / idempotency rule | `docs/RELIABILITY.md` |
| Threat / mitigation | `docs/SECURITY.md` |
| Component taste rule | `docs/DESIGN.md` |
| Reusable how-it-works | `docs/memory/knowledge/` |
| Decision + why | `docs/memory/adr/` |
| Known landmine | `docs/memory/limitations/` |
| Unresolved question | `docs/memory/openq/` |
| Product behavior | `docs/product-specs/` |
| External API facts | `docs/references/` (llms.txt style) |

Procedure: kebab-case filename → frontmatter (`status / last_verified /
owner`) → write the page → register in that directory's `index.md` →
cross-link related pages → `python3 plugin/scripts/check.py`.
