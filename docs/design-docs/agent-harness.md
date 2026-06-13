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
- Host enforcement: a host's own app-code invariants are mechanized as host
  lints under `.claude/lints/`, wired via `.harness.json` `lint_cmd`; the
  `architecture-setter` persona authors them and a host overrides threshold
  defaults in the same file. Self-host enforces only `plugin/`+`docs/` (S/D
  lints); see ARCHITECTURE.md invariant 7.

## Components

| Kind | Name | What it does |
|---|---|---|
| skill | `docs-tree` | Use when adding or relocating knowledge — decides where a page belongs in the docs tree, a |
| skill | `dream` | Use periodically (or after several work sessions) to consolidate memory — dispatches the d |
| skill | `execplan` | Use when starting non-trivial work (multi-session, ≥3 components, architecture/memory chan |
| skill | `garden` | Use periodically (or when docs feel stale) to run the entropy GC — dispatches the doc-gard |
| skill | `harness-init` | Use when setting up, installing, initializing, bootstrapping, or porting this harness into |
| skill | `harness-lint` | Use to run the deterministic gate (taste lints + structure lints + generated-file check +  |
| agent | `architecture-setter` | Constructive counterpart to review-arch: derives the host's invariants and authors host lin |
| agent | `doc-gardener` | Entropy GC persona. Dispatch periodically (garden skill) to detect code↔docs drift, golden |
| agent | `dreamer` | Memory consolidation persona (CONSOLIDATE). Dispatch via the dream skill to compress recen |
| agent | `review-arch` | Architecture & design-taste review persona. Dispatch at ExecPlan completion gates with the |
| agent | `review-reliability` | Reliability review persona. Dispatch at ExecPlan completion gates with the diff range. Gro |
| agent | `review-security` | Security review persona. Dispatch at ExecPlan completion gates with the diff range. Ground |

## Docs placement

| Knowledge kind | Home |
|---|---|
| Design rationale / principle | `docs/design-docs/` |
| Architectural invariant | `ARCHITECTURE.md` (short) or design-docs |
| Component taste rule | `docs/DESIGN.md` |
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

## Memory loop — currently DISABLED (hand-maintained memory)

The automatic memory loop is **off**: the SessionStart/UserPromptSubmit
(feeder) and PreCompact/SessionEnd (imprint) hooks are unwired from
`hooks.json` pending a more sophisticated redesign (see
`docs/memory/openq/memory-loop-redesign.md`). Until then `docs/memory/` is
**maintained by hand** — write progress/ADRs/knowledge/limitations directly
(lints still enforce frontmatter, naming, and index registration).

- Retained but dormant (re-enable by restoring the hook entries):
  - Read path: `feeder_sessionstart.py` (context pack) + `feeder_firstprompt.py`
    (task-targeted addendum).
  - Write path: `imprint_enqueue.py`/`imprint_run.py` (session digests + memory
    updates). `/dream` (consolidate) and `garden` (entropy GC) skills still run
    manually but have no automatic input while imprint is off.
- Never bypass the `docs/memory/` structure even when editing by hand.

## Growing the grounding docs

`docs/RELIABILITY.md` and `docs/SECURITY.md` start as small seeds. When a
review finding or a human correction surfaces a rule worth keeping, append it
as the next numbered rule (feedback twice → promote). Review personas cite ALL
numbered rules in their grounding doc — the doc grows, the personas keep up.
