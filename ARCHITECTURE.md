# ARCHITECTURE.md

Codemap + invariants. Read this before modifying `plugin/`.

## Two layers, one repo

- **Instance** (repo root): `AGENTS.md`, `ARCHITECTURE.md`, `docs/` — the
  knowledge base + structured memory of THIS repo.
- **Machine** (`plugin/`): a portable Claude Code plugin. Installed into another
  repo, that repo brings its own instance layer; the machine stays unchanged.

## Layer law (dependency direction — enforced by lint_structure.py)

`scripts → skills → agents → hooks` (left = lowest; an arrow means "may be
referenced by"; nothing references rightward).

- `plugin/scripts/` — pure stdlib python3; all logic lives here.
- `plugin/skills/` — procedures (SKILL.md); may instruct running scripts.
- `plugin/agents/` — personas dispatched by the main session; may follow skills.
- `plugin/hooks/hooks.json` — thin wiring only: every command invokes a script
  via `${CLAUDE_PLUGIN_ROOT}`; hooks contain no logic.

**Cross-cutting rule (Providers analog):** path/env/frontmatter resolution
exists ONLY in `plugin/scripts/harness_lib.py`. Other scripts never call
`os.getcwd()` / `Path.cwd()` / `CLAUDE_PROJECT_DIR` directly (lint S2).

**Prose exceptions:** the layer law governs imports/invocation. Scripts MAY
read skill-owned *data* (harness-init seed templates), and FIX texts MAY
point rightward at skills — the most actionable instruction wins.

## Invariants

1. **Portability:** nothing in `plugin/` hardcodes an absolute path (lint S3).
2. **Headless recursion guard:** every hook entry script exits immediately when
   `HARNESS_HEADLESS=1`; every spawned `claude -p` child sets it. Without this:
   a hook spawns a headless `claude -p` → the child's own hooks fire → ∞.
3. **Deterministic gate:** `check.py` = lint_structure + lint_docs +
   gen_inventory --check + an optional host-lint step (invariant 7) + the test
   step — a host test command from `.harness.json`/env, else unittest discovery
   when a `tests/` dir exists (the host command replaces the default, it is not
   additive). GREEN before every commit.
4. **Generated files** carry a GENERATED header; only scripts write them.
5. **Runtime state** (queues, locks, seen-sessions, processed-log) lives in
   `.claude/harness/` — gitignored, never under `docs/`.
6. **Govern-by-default, declared legacy:** the content lints (D3/D5/D6/D7)
   hold every `docs/*.md` to the convention. A host adopting the harness over
   a pre-existing `docs/` declares its unmigrated subtrees in
   `docs/.harnessignore` (a shrinking migration backlog), matched on
   path-segment boundaries; harness-managed trees (`hl.MANAGED_ROOTS`) and
   top-level machine docs (`hl.MANAGED_DOCS`) are never exemptable.
7. **Host-owned enforcement (the setter axis):** the built-in lints
   (S1–S7, D1–D10) enforce only the harness's OWN structure (`plugin/`,
   `docs/`, and the root map docs `AGENTS.md`/`ARCHITECTURE.md`). A host's
   app-code invariants are not hardcoded by the machine —
   the `architecture-setup` **skill** (run with the repo's full context) derives
   them per-repo and routes each by FORM: **lints** under `.claude/lints/` for
   mechanical invariants (wired into the gate via `<root>/.harness.json`
   `lint_cmd` — `hl.gate_config`; `check.py` runs it as the `host-lint` step),
   **guide-skills** under `.claude/skills/` for methodology. The harness ships
   the substrate (the gate step, the `FAIL … FIX:` contract, the override knobs)
   and the authoring method — never the rules; the lint and skill sets are the
   host's output (zero of either is valid). Harness
   threshold defaults (D1 120 / D7 400 / D4 30d) are per-repo
   overridable via the same file (`size_limits` / `default_size_limit` /
   `stale_days`); absent → defaults unchanged. `lint_cmd`/`test_cmd` are
   executable config that run every commit (SECURITY.md T9).

## Data flows

> **Memory is the docs tree (memory-as-docs).** There is no separate memory
> layer and no automatic INJECT/IMPRINT loop: the old `feeder_*`/`imprint_*`
> scripts + the `dream`/`dreamer` consolidation were retired (deleted —
> `docs/design-docs/memory-architecture.md`). The WRITE path is the manual
> `dream-rollouts` router; the READ path is on-demand navigation (pull, not a
> feeder). The wired runtime is the MEMORY write (#1, manual) + REVIEW (#3) +
> TIDY (#4, the only wired hook) + the deterministic gate.

1. **MEMORY — write (manual `dream-rollouts`)** — `dream_run.py` mines idle past
   sessions: Phase 1 extracts a raw memory each (small model, no-op-preferred);
   Phase 2, on a self-host repo, ROUTES each distilled claim into its docs home
   via a READ-ONLY agent (proposes a JSON plan) + a deterministic applicator
   (appends onto an allowlist: tracker row / design-doc `## Decision log` /
   `## Open decisions` / `docs/journal/`); a bare host falls back to the sandbox
   flat store (`dream_phase2`). Provenance → `docs/journal/`.
2. **MEMORY — read (on-demand pull)** — a session navigates the docs tree
   (AGENTS.md map + Grep/Glob) for the context a task needs; no SessionStart
   feeder compiles or injects a pack.
3. **REVIEW** — `execplan` completion gate → self-review → review-arch /
   review-reliability (each grounded 1:1 in its doc) + review-security when
   the diff touches the live exec surface (hooks / `.harness.json` /
   `.harnessignore`) or the dreaming/docs-sync write path → iterate until
   satisfied.
4. **TIDY** — Stop hook → `tidy_stop.py` → fingerprint-deduped lint subset
   on the dirty tree; FAIL blocks once per state with FIX lines (R11).
   Commits are also gated mechanically by the scaffold-installed
   `.git/hooks/pre-commit` running `check.py`.

## Failure modes

See `docs/RELIABILITY.md`. Headlines: dreaming memory writes are idempotent
(sqlite PK-upsert + router dedupe, R1), the `dream-rollouts` pipeline degrades to
a recorded `failed`/`skipped` status and never blocks a session (R2), and dreaming
is single-flight via a lock file with stale-lock recovery + the Phase-2 DB lock and
6h cooldown (R3).
