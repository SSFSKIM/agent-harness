---
name: harness-init
description: Use when setting up, installing, initializing, bootstrapping, or porting this harness into a new or existing host repo — scaffolds the docs-tree convention, migrates existing docs into it, and wires memory + lint gate to GREEN.
---
# Harness init — bootstrap a host repo

Port the harness (docs-as-memory + lints + personas + memory loop) into a
host repo. The plugin stays where it lives; the host gains the convention.
Resolve `PLUGIN` once: this SKILL.md sits at `<plugin>/skills/harness-init/`,
so PLUGIN is two directories up.

## 1. Explore (existing repos; fresh/empty → skip)

Inventory before writing: README, docs/, CONTRIBUTING, ADRs, existing
AGENTS.md/CLAUDE.md. Note build/test commands and source layout — the map
needs them in step 3.

## 2. Scaffold (deterministic)

    python3 "$PLUGIN/scripts/scaffold.py" --root <host-repo-root>

Idempotent — seeded files are never overwritten (CREATE/SKIP per path);
`.gitignore` is append-only; the component inventory is (re)generated.
Creates the docs tree, seed grounding docs, memory bootloader, and the
CLAUDE.md→AGENTS.md pointer. New repo: `git init` first.

## 3. Write the map (judgment)

- Fresh AGENTS.md: replace every `<!-- FILL: ... -->` marker — repo description,
  real source-layout map rows, build/test commands. Keep ≤120 lines (D1).
- Host already had AGENTS.md or a substantive CLAUDE.md: scaffold skipped
  them — merge instead. Fold the harness pointers (operating model, link to
  `docs/design-docs/agent-harness.md`, memory paths) into the existing map;
  reduce CLAUDE.md to the 3-line pointer with its content relocated.

## 4. Migrate existing docs

Follow `references/migration.md`: triage every existing doc into the tree
(`git mv`, frontmatter backfill, index registration, link fixes). Never
delete content — obsolete pages get `status: archived`. Big repos migrate in
waves: gate first, remaining docs as tech-debt rows.

## 5. Adapt the seeds (judgment — confirm with the human)

`docs/design-docs/core-beliefs.md` ships harness defaults; rules like "no
hand-written code" are policy, not mechanics. Confirm which rules the host
adopts, prune or amend, then treat survivors as law. RELIABILITY/SECURITY
seeds grow later via feedback-twice→promote.

## 6. Verify GREEN

    python3 "$PLUGIN/scripts/check.py" --root <host-repo-root>

Iterate on FAILs — every message carries its own FIX (`harness-lint` skill).
Then confirm no marker survived: `grep -rn "FILL" <host-root>/AGENTS.md
<host-root>/docs/` must print nothing.
Tests: with no `tests/` dir the step is skipped; a host with its own suite
wires it via the `HARNESS_TEST_CMD` env var (e.g. `HARNESS_TEST_CMD="pytest
-q" python3 ... check.py`) — the default only understands unittest discovery.

## 7. Write back, commit, hand off

- Fill `docs/memory/progress/current.md` with the host's real state (it
  ships with FILL markers).
- Commit the scaffold + migration as its own commit before substantive work.
- Hand off: the next session starts in the host root with
  `claude --plugin-dir "$PLUGIN"` — the feeder activates once
  `docs/memory/MEMORY.md` exists.
