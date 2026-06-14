---
status: stable
last_verified: {{TODAY}}
owner: harness
---
# agent-harness — the installed harness

This repo is operated by the `agent-harness` Claude Code plugin: docs-as-memory
knowledge system, taste lints whose FAIL messages carry FIX instructions,
review personas grounded 1:1 in docs, and a dreaming memory loop that distills
past sessions into the docs tree. Bootstrapped by the `harness-init` skill on
{{TODAY}}.

## Run it

- Load: `claude --plugin-dir <plugin>` from this repo's root — the plugin's
  location on this machine is recorded in `.git/hooks/pre-commit` (its
  check.py path reveals the plugin dir). Memory is read on demand from the docs
  tree (pull, not a SessionStart feeder).
- Gate: run `.git/hooks/pre-commit` — scaffold installs it with this
  machine's exact `check.py` invocation (no placeholders to resolve; rerun
  scaffold.py after moving the repo or plugin and the hook is rewritten).
  Must be GREEN before every commit; the `harness-lint` skill interprets
  failures. `--no-verify` only for emergencies — fix forward right after.
- Tests in the gate: wired via the `HARNESS_TEST_CMD` env var (e.g.
  `HARNESS_TEST_CMD="pytest -q"`) or `.harness.json` `test_cmd`; default is
  unittest discovery when a `tests/` directory exists, skipped otherwise.
- Host enforcement: this repo's own architecture invariants are mechanized by
  the `architecture-setup` skill (harness-init step 7), routed by FORM — host
  lints under `.claude/lints/` (wired into the gate via `.harness.json`
  `lint_cmd`) for mechanical invariants, guide-skills under `.claude/skills/` for
  methodology. Override a harness threshold default for this repo in the same
  file (`size_limits` / `default_size_limit` / `stale_days`). See ARCHITECTURE.md
  invariant 7; the rules are this repo's, not the machine's.

## Components

| Kind | Name | What it does |
|---|---|---|
{{COMPONENTS}}

## Docs placement

| Knowledge kind | Home |
|---|---|
| Design rationale / principle / reusable how-it-works | `docs/design-docs/` |
| Architectural invariant | `ARCHITECTURE.md` (short) or design-docs |
| Decision + why | a design-doc's `## Decision log` |
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

Pre-existing docs that don't follow the convention yet are declared in
`docs/.harnessignore` (a migration backlog the content lints skip). Migrate a
subtree, then delete its line; harness-managed trees can't be listed there.

## Memory — one brain = docs

`docs/` IS the long-term memory (`docs/design-docs/memory-architecture.md`).
There is no separate memory layer; the placement table above is the one taxonomy
both manual placement and the dreaming router use.

- **Write (live):** the `dream-rollouts` skill (`dream_run.py`) mines past session
  transcripts — Phase 1 extracts a raw memory each (small model, no-op-preferred),
  Phase 2 ROUTES each distilled claim into its docs home via a read-only agent (it
  proposes a routing plan) + a deterministic applicator (it appends onto an
  allowlist). Episodic / provenance residue → `docs/journal/`.
- **Read = on-demand navigation** (pull, not a feeder): find task-relevant memory
  in docs via the AGENTS.md map + Grep/Glob (`memory-architecture.md`).
- A bare host with no docs library uses the sandbox-store fallback (`dream_phase2`,
  a gitignored `.claude/harness/memories/` store) instead of routing into docs.
- The `garden` skill + `doc-gardener` agent (docs entropy GC) keep the tree from
  rotting; they are independent of the memory loop.

## Growing the grounding docs

`docs/RELIABILITY.md` and `docs/SECURITY.md` start as small seeds. When a
review finding or a human correction surfaces a rule worth keeping, append it
as the next numbered rule (feedback twice → promote). Review personas cite ALL
numbered rules in their grounding doc — the doc grows, the personas keep up.
