---
status: stable
last_verified: {{TODAY}}
owner: harness
---
# agent-harness — the installed harness

This repo is operated by the `agent-harness` Claude Code plugin: docs-as-memory
knowledge system, taste lints whose FAIL messages carry FIX instructions,
review personas grounded 1:1 in docs, and a memory loop (feeder / imprint /
dreaming). Bootstrapped by the `harness-init` skill on {{TODAY}}.

## Run it

- Load: `claude --plugin-dir <path-to-agent-harness>/plugin` from this repo's
  root. The SessionStart feeder activates once `docs/memory/MEMORY.md` exists.
- Gate: `python3 <plugin>/scripts/check.py --root <this-repo-root>` must be
  GREEN before every commit. The `harness-lint` skill interprets failures.
- Tests in the gate: wired via the `HARNESS_TEST_CMD` env var (e.g.
  `HARNESS_TEST_CMD="pytest -q"`); default is unittest discovery when a
  `tests/` directory exists, skipped otherwise.

## Components

| Kind | Name | What it does |
|---|---|---|
{{COMPONENTS}}

## Docs placement

| Knowledge kind | Home |
|---|---|
| Design rationale / principle | `docs/design-docs/` |
| Failure mode / idempotency rule | `docs/RELIABILITY.md` |
| Threat / mitigation | `docs/SECURITY.md` |
| Reusable how-it-works | `docs/memory/knowledge/` |
| Decision + why | `docs/memory/adr/` |
| Known landmine | `docs/memory/limitations/` |
| Unresolved question | `docs/memory/openq/` |
| Product behavior | `docs/product-specs/` |
| External API facts | `docs/references/` |

Procedure for a new page: kebab-case filename → frontmatter (`status /
last_verified / owner`) → write → register in that directory's `index.md` →
cross-link → run the gate (the `docs-tree` skill owns this).

## Memory loop

- Read path: the SessionStart feeder compiles a context pack from
  `docs/memory/`; a first-prompt addendum targets the session's actual topic.
- Write path: PreCompact/SessionEnd hooks enqueue imprint jobs (session
  digests + memory page updates); `/dream` consolidates; `garden` GCs entropy.
- Never bypass the `docs/memory/` structure — lints enforce frontmatter,
  naming, and index registration.

## Growing the grounding docs

`docs/RELIABILITY.md` and `docs/SECURITY.md` start as small seeds. When a
review finding or a human correction surfaces a rule worth keeping, append it
as the next numbered rule (feedback twice → promote). Review personas cite ALL
numbered rules in their grounding doc — the doc grows, the personas keep up.
