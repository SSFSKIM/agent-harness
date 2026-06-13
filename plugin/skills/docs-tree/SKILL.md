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
| Product behavior | `docs/product-specs/` (harness-managed by default) |
| External API facts | `docs/references/` (llms.txt style) |
| Host-specific business/marketing/curriculum/etc. knowledge | Create or use a natural `docs/<domain>/` root; opt it into governance only when useful |

Procedure for machine-critical and harness-managed roots: kebab-case filename →
frontmatter (`status / last_verified / owner`) → write the page → register it
in that directory's `index.md` → cross-link related pages → run the gate
(command in `docs/design-docs/agent-harness.md`).

Procedure for host-owned project roots: choose the structure that makes the
agent most capable in this repo. Use frontmatter/indexes when they help, but do
not force the harness convention unless the root is listed in `.harness.json`
`managed_doc_roots` or the host has set `doc_governance: strict`.
