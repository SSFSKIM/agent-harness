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

- Load: `claude --plugin-dir <plugin>` from this repo's root — the plugin's
  location on this machine is recorded in `.git/hooks/pre-commit` (its
  check.py path reveals the plugin dir). The SessionStart feeder activates
  once `docs/memory/MEMORY.md` exists.
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

Pre-existing docs that don't follow the convention yet are declared in
`docs/.harnessignore` (a migration backlog the content lints skip). Migrate a
subtree, then delete its line; harness-managed trees can't be listed there.

## Memory loop — currently DISABLED (hand-maintained memory)

The automatic memory loop ships **off**: the SessionStart/UserPromptSubmit
(feeder) and PreCompact/SessionEnd (imprint) hooks are unwired pending a more
sophisticated redesign. Until then `docs/memory/` is **maintained by hand** —
write progress/ADRs/knowledge/limitations directly; lints still enforce
frontmatter, naming, and index registration.

- Retained but dormant (re-enable by restoring the hook entries in the
  plugin's `hooks.json`): `feeder_*` (read path: context pack + addendum),
  `imprint_*` (write path: session digests + memory updates). The `/dream`
  (consolidate) and `garden` (entropy GC) skills run manually.
- Never bypass the `docs/memory/` structure even when editing by hand.

## Growing the grounding docs

`docs/RELIABILITY.md` and `docs/SECURITY.md` start as small seeds. When a
review finding or a human correction surfaces a rule worth keeping, append it
as the next numbered rule (feedback twice → promote). Review personas cite ALL
numbered rules in their grounding doc — the doc grows, the personas keep up.
