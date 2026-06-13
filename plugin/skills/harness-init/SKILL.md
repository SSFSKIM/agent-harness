---
name: harness-init
description: Use when setting up, installing, initializing, bootstrapping, or porting this harness into a new or existing host repo — scaffolds the docs-tree convention, migrates existing docs into it, and wires memory + lint gate to GREEN.
---
# Harness init — bootstrap a host repo

Port the harness (docs-as-memory substrate + lints + personas) into a host
repo. The plugin stays where it lives; the host gains the minimum machine
contract plus a project-specific docs shape chosen from the repo itself.
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
- Do not treat the scaffolded `ARCHITECTURE.md` as complete. It is an
  authoring frame for the host's real mental map; step 7 writes/refines it from
  source-code exploration.

## 4. Shape and migrate existing docs

Follow `references/migration.md`, but do not force every host into the same
knowledge taxonomy. The scaffold creates the minimum machine-critical docs and
harness-managed roots (`design-docs/`, `exec-plans/`, `memory/`,
`product-specs/`). For additional project-specific docs, infer the repo's
natural shape: a fundraising repo may need `docs/business/`, a growth repo may
need `docs/marketing/`, a school repo may need `docs/curriculum/`. Create or
keep those roots when they make the agent more capable.

Never delete content — obsolete pages get `status: archived` when migrated.
Big repos migrate in waves: gate first, remaining docs as tech-debt rows.
Project-specific roots are host-owned by default: the gate does not block on
their frontmatter, filename, line count, or index registration unless the host
opts that root into `.harness.json` `managed_doc_roots` or sets
`doc_governance: strict`.

`docs/.harnessignore` remains a strict-mode migration tool. Use it when a host
has opted into global docs governance but still needs a declared legacy wave.
Harness-managed trees (`memory/`, `design-docs/`, `exec-plans/`) and top-level
machine docs (`SECURITY.md`, `DESIGN.md`, …) cannot be exempted — the harness
always governs its own execution surface.

## 5. Adapt the seeds (judgment — confirm with the human)

`docs/design-docs/core-beliefs.md` ships harness defaults; rules like "no
hand-written code" are policy, not mechanics. Confirm which rules the host
adopts, prune or amend, then treat survivors as operating defaults. Promote to
blocking lint only when the rule is mechanical, repeated, and costly if missed.
RELIABILITY/SECURITY seeds grow later via feedback-twice→promote.

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

## 7. Author architecture + mechanize host invariants (architecture-setup skill — judgment)

Docs *map* the architecture first; only then does the harness enforce the parts
that deserve enforcement. Run the `architecture-setup` skill with the host's
full repo context to write/refine THIS repo's `ARCHITECTURE.md` from the real
source tree, then derive its layer law/invariants and mechanize each into its
right FORM:

- The skill classifies each invariant — **deterministic lint** (mechanical,
  always-true, costly if missed → `.claude/lints/`, template
  `templates/host-lint.py`, wired via `<root>/.harness.json` `lint_cmd`),
  **guide-skill** (methodology → `.claude/skills/`), judge (semantic; deferred),
  or fix-forward. The harness hardcodes no app-code rule; the lint AND
  guide-skill sets are this repo's output (zero of either is valid).
- The host `ARCHITECTURE.md` must answer "where is the thing that does X?",
  name boundaries/absences, and record an `Invariant -> FORM` table. It is the
  host's map, not a copy of the harness self-host architecture.
- Threshold defaults are overridable, not mandates: if the host's map or pages
  legitimately exceed a harness default (e.g. a 295-line AGENTS.md), set
  `.harness.json` `size_limits` / `default_size_limit` / `stale_days` instead of
  fighting D1/D7/D4.
- Plugin component inventory/coverage are advisory for external-plugin hosts by
  default so plugin updates do not retroactively break host commits. If this
  host wants them blocking, set `.harness.json` `component_inventory: strict`
  and/or `component_coverage: strict`.
- `.harness.json` + `.claude/lints/` are executable config that run on every
  commit (SECURITY.md T9) — `git add -f` them (and any authored
  `.claude/skills/`) if the host blanket-ignores `.claude/`, and review changes
  to the executable config as code.

## 8. Verify GREEN

    python3 "$PLUGIN/scripts/check.py" --root <host-repo-root>

Iterate on FAILs — every message carries its own FIX (`harness-lint` skill).
Then confirm no template marker survived: `grep -rn --include="*.md" "FILL"
<host-root>/AGENTS.md <host-root>/ARCHITECTURE.md <host-root>/docs/` must print
nothing. (Scope to `*.md` — markers only live in markdown; a bare grep also
hits data files like CSV/JSON that legitimately contain the substring.)
Tests: with no `tests/` dir the step is skipped; a host with its own suite
wires it via the `HARNESS_TEST_CMD` env var (e.g. `HARNESS_TEST_CMD="pytest
-q" python3 ... check.py`) — the default only understands unittest discovery.

## 9. Write back, commit, hand off

- Fill `docs/memory/progress/current.md` with the host's real state (it
  ships with FILL markers).
- Commit the scaffold + migration as its own commit before substantive work.
- Hand off: the next session starts in the host root with
  `claude --plugin-dir "$PLUGIN"` — `docs/memory/MEMORY.md` is the continuity
  entrypoint while the automatic feeder is disabled.
