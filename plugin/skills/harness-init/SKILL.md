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
Creates the docs tree, seed grounding docs, memory bootloader, the
CLAUDE.md→AGENTS.md pointer, and a `.git/hooks/pre-commit` gate hook — the
hook IS the recorded gate command (machine-local absolute paths; rerunning
scaffold rewrites it after a repo/plugin move). New repo: `git init` first.

## 3. Write the map (judgment)

- Fresh AGENTS.md: replace every `<!-- FILL: ... -->` marker — repo description,
  real source-layout map rows, build/test commands. Keep ≤120 lines (D1).
- Host already had AGENTS.md or a substantive CLAUDE.md: scaffold skipped
  them — merge instead. Fold the harness pointers (operating model, link to
  `docs/design-docs/agent-harness.md`, memory paths) into the existing map.
  - Minimal/thin CLAUDE.md → reduce it to a 3-line pointer, content relocated.
  - **Doc-sophisticated host** (a working, layered CLAUDE.md that loads
    subsystem docs, or a deliberate AGENTS+CLAUDE split): do NOT gut it. Make
    AGENTS.md the canonical operating map, add a short harness-pointer header
    to CLAUDE.md, and relocate only genuinely duplicated content (e.g. a schema
    block → `docs/references/`). Forcing the host's own conventions out is the
    over-specificity portability must avoid — graft additively, govern new docs
    going forward, declare the rest legacy.

## 4. Migrate existing docs

Follow `references/migration.md`: triage every existing doc into the tree
(`git mv`, frontmatter backfill, index registration, link fixes). Never
delete content — obsolete pages get `status: archived`. Big repos migrate in
waves: gate first, remaining docs as tech-debt rows.

**Declare the wave boundary in `docs/.harnessignore`** (scaffold seeded it
empty). List the host's pre-existing `docs/` subtrees that won't follow the
convention yet — docs-relative prefixes, dir entries end `/` (e.g.
`business/`, `school-integration/`), bare filenames match one file. The
content lints (D3/D5/D6/D7) skip them, so the gate reaches GREEN without
force-renaming human-curated business/spec/research trees. The file is the
migration backlog: migrate a wave, delete its line. Harness-managed trees
(`memory/`, `design-docs/`, …) and top-level machine docs (`SECURITY.md`,
`DESIGN.md`, …) cannot be exempted — the harness always governs its own tree.

## 5. Adapt the seeds (judgment — confirm with the human)

`docs/design-docs/core-beliefs.md` ships harness defaults; rules like "no
hand-written code" are policy, not mechanics. Confirm which rules the host
adopts, prune or amend, then treat survivors as law. RELIABILITY/SECURITY
seeds grow later via feedback-twice→promote.

## 6. Instance skills & app verification (judgment)

The machine's skills are generic; the host's own procedures live in
`.claude/skills/<name>/SKILL.md` (instance layer — travels with the repo).

- Always: create a `verify` skill encoding this repo's full verification
  order (build → checks → tests, with barriers) so sessions never guess it.
  Start from `templates/verify-skill.md` (copy → fill the FILL markers with the
  host's real commands). Wire it into AGENTS.md under "Mandatory skill usage".
- Runnable app: also create a boot/observe skill (run one instance, read its
  logs/output/UI) — agents must be able to SEE the app to validate work.
- **Make them travel.** `.claude/skills/` only travels if it's tracked. Hosts
  that blanket-ignore `.claude/` (scaffold logs a NOTE when it detects this)
  drop instance skills silently — `git add -f .claude/skills/<name>` to track
  them, matching how the host already tracks any existing instance assets.

## 7. Verify GREEN

    python3 "$PLUGIN/scripts/check.py" --root <host-repo-root>

Iterate on FAILs — every message carries its own FIX (`harness-lint` skill).
Then confirm no template marker survived: `grep -rn --include="*.md" "FILL"
<host-root>/AGENTS.md <host-root>/ARCHITECTURE.md <host-root>/docs/` must print
nothing. (Scope to `*.md` — markers only live in markdown; a bare grep also
hits data files like CSV/JSON that legitimately contain the substring.)
Tests: with no `tests/` dir the step is skipped; a host with its own suite
wires it via the `HARNESS_TEST_CMD` env var (e.g. `HARNESS_TEST_CMD="pytest
-q" python3 ... check.py`) — the default only understands unittest discovery.

## 8. Write back, commit, hand off

- Fill `docs/memory/progress/current.md` with the host's real state (it
  ships with FILL markers).
- Commit the scaffold + migration as its own commit before substantive work.
- Hand off: the next session starts in the host root with
  `claude --plugin-dir "$PLUGIN"` — the feeder activates once
  `docs/memory/MEMORY.md` exists.
