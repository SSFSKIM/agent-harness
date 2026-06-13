# Migrating an existing repo's docs into the harness convention

Detailed playbook for harness-init step 4. Goal: machine-critical docs pass the
harness contract, and existing host docs get a discoverable project-specific
home without losing content or git history. Do not force every host into one
universal taxonomy.

## Triage table

| Existing artifact | Destination |
|---|---|
| README.md | Stays at root; link it from the AGENTS.md map. Extract durable knowledge into docs/ pages. |
| CONTRIBUTING / style guides | `docs/design-docs/` (or fold into core-beliefs.md if short) |
| ADRs (`adr/`, `docs/adr/`, RFCs) | `docs/memory/adr/` + register in its index.md |
| Architecture overviews | `ARCHITECTURE.md` at root (codemap + invariants) or `docs/design-docs/` |
| How-it-works guides, runbooks | `docs/memory/knowledge/` |
| Known issues, quirks, gotchas | `docs/memory/limitations/` |
| Roadmaps, TODO lists | `docs/exec-plans/active/` (living plans) or tech-debt-tracker rows |
| External API / service notes | `docs/references/` (llms.txt-style digests) |
| Product / feature specs | `docs/product-specs/` (harness-managed by default) |
| Historical / superseded docs | Keep in place or move alongside successors; set `status: archived` (D4-exempt) |
| Host-specific bodies of knowledge | Create/keep the natural root (`docs/business/`, `docs/marketing/`, `docs/curriculum/`, etc.); opt into blocking governance only when useful |

## Per-document procedure

1. `git mv` (preserves history) to the destination when moving helps the
   agent. For machine-critical and managed roots, rename to
   lowercase-kebab-case.md (D6). For host-owned project roots, preserve
   meaningful existing names unless the host opts the root into governance.
2. Backfill frontmatter (D3): `status / last_verified / owner`.
   - `status: draft` for content believed current, `archived` for historical.
   - **Do not stamp `last_verified: <today>` blind.** The stamp asserts the
     page was checked against reality. Re-read the page; fix or trim what is
     wrong, then stamp. If not worth re-verifying now, mark `archived`.
   - `owner`: the team/agent accountable; `harness` as fallback.
3. Register managed pages in their directory's `index.md` with a one-line
   description (D8). Host-owned project roots may use whatever index or README
   shape makes the agent effective.
4. Fix inbound links repo-wide (D5): grep the old path, update references.
5. Pages over 400 lines (D7): split detail into linked sub-pages, or move to
   a size-exempt area only if it genuinely belongs there
   (`exec-plans/`, `references/`).

## AGENTS.md / CLAUDE.md merge

- Existing AGENTS.md: keep it the single map. Add the harness rows
  (agent-harness.md, docs/memory/, exec-plans/, RELIABILITY/SECURITY) and the
  5-step operating model; cut detail until ≤120 lines — relocated detail goes
  to docs/ pages it links.
- Existing CLAUDE.md with real content: move that content into AGENTS.md or
  the right docs/ page, then reduce CLAUDE.md to the 3-line pointer
  (single-map principle — two competing manuals drift).

## Common FAILs while migrating

| FAIL | Fix |
|---|---|
| D3 missing frontmatter | Backfill per step 2 above |
| D4 stale last_verified | Re-verify content then bump the date, or set `status: archived` |
| D5 broken link | Old path moved — grep and update; or create the missing target |
| D6 not kebab-case | `git mv` to lowercase-kebab-case.md |
| D7 over size limit | Split into sub-pages behind a pointer |
| D8 not in index.md | Add a one-line entry to the category index |
| D9 component unmentioned | Ensure `docs/design-docs/agent-harness.md` exists (scaffold creates it; do not delete the components table) |

## Wave strategy for big repos

Do not block init on a full migration. Wave 1: scaffold + map + gate GREEN
(possible with zero migrated host docs). Wave 2+: triage highest-traffic docs
first; add a tech-debt row per remaining batch so the gardener and future
sessions keep pulling the thread. Use `.harness.json` `managed_doc_roots` only
for roots where the host wants blocking frontmatter/naming/size/index behavior.
