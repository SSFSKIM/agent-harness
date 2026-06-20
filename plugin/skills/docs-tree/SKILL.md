---
name: docs-tree
description: Use when adding or relocating knowledge — decides where a page belongs in the docs tree, applies frontmatter, registers it in the right index.
---
# Docs tree placement

This skill decides *where a new page goes*. To *find* what already exists —
query by type/tag, check backlinks before editing, sweep for stale/orphan/drift
— use the `docs-nav` skill (`nav.py`) instead of bulk-reading.

| Knowledge kind | Home |
|---|---|
| Design rationale / principle | `docs/design-docs/` |
| Architectural invariant | `ARCHITECTURE.md` (short) or design-docs |
| Failure mode / idempotency rule | `docs/RELIABILITY.md` |
| Threat / mitigation | `docs/SECURITY.md` |
| Component taste rule | `docs/DESIGN.md` |
| Reusable how-it-works | `docs/design-docs/` |
| Decision + why | `docs/adr/` |
| Known landmine / unresolved question | `docs/exec-plans/tech-debt-tracker.md` |
| Product behavior | `docs/product-specs/` (harness-managed by default) |
| External API facts | `docs/references/` (llms.txt style) |
| Host-specific business/marketing/curriculum/etc. knowledge | Create or use a natural `docs/<domain>/` root; opt it into governance only when useful |

Procedure for machine-critical and harness-managed roots: kebab-case filename →
frontmatter (`status / last_verified / owner`) → write the page → register it
in that directory's `index.md` → cross-link related pages → run the gate
(command in `docs/design-docs/agent-harness.md`).

Optionally add the recommended keys from `docs/KNOWLEDGE_FORMAT.md` (the format
contract): `type` (concept-kind), `tags` (`[a, b]` facets), `resource` (the
code/asset the page documents), `description` (one-sentence summary), `title`
(only to override a poor H1). All optional and ungated — they make the page
queryable and self-describing for navigation.

Procedure for host-owned project roots: choose the structure that makes the
agent most capable in this repo. Use frontmatter/indexes when they help, but do
not force the harness convention unless the root is listed in `.harness.json`
`managed_doc_roots` or the host has set `doc_governance: strict`.

## When to cross-link

Links are the corpus's load-bearing structure — `nav` traverses them, D5 enforces
them, "orphan" is defined against them. Add one wherever a reader *here* would
benefit from the jump:

- **Name, don't restate.** When you mention a concept/decision/component that has
  its own page, link it instead of re-explaining — the linked page is the single
  source of truth, so the two never drift.
- **Link upward** from a new page to what it builds on: the product-spec it
  implements, the ADR that motivated it, the knowledge page it extends.
- **Anti-orphan.** Make sure something already in the corpus links *to* the new
  page. `index.md` registration (D8) is the baseline inbound link; add a
  contextual link from the most-related page too, or `nav.py orphans` will
  (rightly) flag it as unreachable.
- **First mention, not every mention.** Link the first, most-relevant occurrence;
  repeating the link on each occurrence is noise, not navigation.
- **Relationship in prose.** Links are untyped, so say *how* the pages relate
  (supersedes, depends-on, refines) in the surrounding text — the edge only
  records *that* they relate.

Link *mechanics* (syntax, path resolution, anchors, why backlinks are never
hand-written) live in `docs/KNOWLEDGE_FORMAT.md` §4. To see what already links
*to* a page before you edit it, use `docs-nav` (`nav.py backlinks <page>`).
