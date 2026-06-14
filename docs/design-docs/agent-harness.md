---
status: stable
last_verified: 2026-06-12
owner: harness
---
# agent-harness — the installed harness

This repo is operated by the `agent-harness` Claude Code plugin: docs-as-memory
knowledge system, taste lints whose FAIL messages carry FIX instructions,
review personas grounded 1:1 in docs, and a memory loop (feeder / imprint /
dreaming). **Self-host**: the machine itself lives in this repo at `plugin/`.

## Run it

- Load: `claude --plugin-dir ./plugin` from this repo's root. The
  SessionStart feeder activates once `docs/memory/MEMORY.md` exists.
- Gate: `python3 plugin/scripts/check.py` must be GREEN before every commit.
  The `harness-lint` skill interprets failures.
- The gate is mechanical: scaffold installs `.git/hooks/pre-commit` running
  it (`--no-verify` only for emergencies — fix forward right after).
- Tests in the gate: wired via the `HARNESS_TEST_CMD` env var (e.g.
  `HARNESS_TEST_CMD="pytest -q"`) or `.harness.json` `test_cmd`; default is
  unittest discovery when a `tests/` directory exists, skipped otherwise.
- Host enforcement: a host's own app-code invariants are mechanized by the
  `architecture-setup` skill, routed by FORM — host lints under `.claude/lints/`
  (wired via `.harness.json` `lint_cmd`) for mechanical invariants, guide-skills
  under `.claude/skills/` for methodology; a host overrides threshold defaults in
  the same file. Self-host enforces only `plugin/`+`docs/` (S/D lints); see
  ARCHITECTURE.md invariant 7.

## Components

| Kind | Name | What it does |
|---|---|---|
| skill | `architecture-setup` | Use to set up/revise a repo's architecture & taste enforcement — derives invariants, routes |
| skill | `docs-tree` | Use when adding or relocating knowledge — decides where a page belongs in the docs tree, a |
| skill | `execplan` | Use when starting non-trivial work (multi-session, ≥3 components, architecture/memory chan |
| skill | `garden` | Use periodically (or when docs feel stale) to run the entropy GC — dispatches the doc-gard |
| skill | `harness-init` | Use when setting up, installing, initializing, bootstrapping, or porting this harness into |
| skill | `harness-lint` | Use to run the deterministic gate (taste lints + structure lints + generated-file check +  |
| agent | `doc-gardener` | Entropy GC persona. Dispatch periodically (garden skill) to detect code↔docs drift, golden |
| agent | `review-arch` | Architecture & design-taste review persona. Dispatch at ExecPlan completion gates with the |
| agent | `review-reliability` | Reliability review persona. Dispatch at ExecPlan completion gates with the diff range. Gro |
| agent | `review-security` | Security review persona. Dispatch at ExecPlan completion gates with the diff range. Ground |

## Docs placement

| Knowledge kind | Home |
|---|---|
| Design rationale / principle / reusable how-it-works | `docs/design-docs/` |
| Architectural invariant | `ARCHITECTURE.md` (short) or design-docs |
| Decision + why | a design-doc's `## Decision log` (or an ADR page) |
| Unresolved question | a design-doc's `## Open decisions` |
| Known landmine / limitation / debt | `docs/exec-plans/tech-debt-tracker.md` |
| Failure mode / idempotency rule | `docs/RELIABILITY.md` |
| Threat / mitigation | `docs/SECURITY.md` |
| Component taste rule | `docs/DESIGN.md` |
| Product behavior | `docs/product-specs/` |
| External API digest | `docs/references/` (vendored) |
| Episodic / provenance | `docs/journal/` (append-only) |

Procedure for a new page: kebab-case filename → frontmatter (`status /
last_verified / owner`) → write → register in that directory's `index.md` →
cross-link → run the gate (the `docs-tree` skill owns this).

## Memory — one brain = docs

`docs/` IS the long-term memory (`docs/design-docs/memory-architecture.md`).
There is no separate memory layer; the placement table above is the one taxonomy
both manual placement and the dreaming router use.

- **Write (live):** the `dream-rollouts` skill (`dream_run.py`) mines past session
  transcripts — Phase 1 extracts a raw memory each (small model, no-op-preferred),
  Phase 2 ROUTES each distilled claim into its docs home via a read-only agent (it
  proposes a routing plan) + a deterministic applicator (it appends onto an
  allowlist). Episodic / provenance residue → `docs/journal/`.
- **Read = on-demand navigation** (pull, not a feeder): the agent finds
  task-relevant memory in docs via the map + Grep/Glob (`memory-architecture.md`).
- Dormant, being retired onto the dreaming engine: `feeder_*`, `imprint_*`, and the
  `dream`/`garden` skills (the old automatic memory loop). A bare host with no docs
  library uses the sandbox-store fallback (`dream_phase2`).

## Growing the grounding docs

`docs/RELIABILITY.md` and `docs/SECURITY.md` start as small seeds. When a
review finding or a human correction surfaces a rule worth keeping, append it
as the next numbered rule (feedback twice → promote). Review personas cite ALL
numbered rules in their grounding doc — the doc grows, the personas keep up.
