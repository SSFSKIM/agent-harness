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
   SessionStart → feeder spawns claude → its SessionStart → ∞.
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
   threshold defaults (D1 120 / D7 400 / D4 30d / MEMORY 60) are per-repo
   overridable via the same file (`size_limits` / `default_size_limit` /
   `stale_days`); absent → defaults unchanged. `lint_cmd`/`test_cmd` are
   executable config that run every commit (SECURITY.md T9).

## Data flows

> **The automatic memory loop (INJECT/IMPRINT/CONSOLIDATE) is currently
> DISABLED.** Its hooks (SessionStart, UserPromptSubmit, PreCompact,
> SessionEnd) are unwired from `hooks.json`. The redesign has now landed as the
> **memory-as-docs** pivot (`docs/design-docs/memory-architecture.md`): the write
> path is the dreaming `dream-rollouts` router (Phase 1 extract → Phase 2 routes
> distilled claims into the docs tree + `docs/journal/`), so the old `imprint`/
> `dream`/`garden` loop is being retired onto that engine (M5). The read path
> is now on-demand navigation (pull, not a feeder — see
> `memory-architecture.md`). The active runtime is REVIEW (#4) +
> TIDY (#5) + the deterministic gate.

1. **INJECT** *(disabled — hook unwired)* — SessionStart hook →
   `feeder_sessionstart.py` → headless Sonnet(1M) reads `docs/memory/` +
   `docs/exec-plans/active/` → compiles a context pack → `additionalContext`.
   First user prompt → `feeder_firstprompt.py` → task-targeted addendum.
2. **IMPRINT** *(disabled — hooks unwired)* — PreCompact/SessionEnd →
   `imprint_enqueue.py` (at-least-once queue) → `imprint_run.py` (single-flight
   lock; dedupe via `imprint_guard`) → headless claude writes a session digest
   + memory updates → lint_docs.
3. **CONSOLIDATE** *(manual; no automatic input while IMPRINT is off)* —
   `/dream` → dreamer agent reads `archive/sessions/` digests → rewrites
   knowledge/limitations/openq/adr directly → `check.py` green terminates.
4. **REVIEW** — `execplan` completion gate → self-review → review-arch /
   review-reliability (each grounded 1:1 in its doc) + review-security only when
   the diff touches the live exec surface (hooks / `.harness.json` /
   `.harnessignore`; the rest of SECURITY.md is dormant with the disabled memory
   loop — deferred 2026-06-13) → iterate until satisfied.
5. **TIDY** — Stop hook → `tidy_stop.py` → fingerprint-deduped lint subset
   on the dirty tree; FAIL blocks once per state with FIX lines (R11).
   Commits are also gated mechanically by the scaffold-installed
   `.git/hooks/pre-commit` running `check.py`.

## Failure modes

See `docs/RELIABILITY.md`. Headlines: imprint writes are idempotent (dedupe
keys), feeder degrades to a deterministic minimal pack on timeout/error,
imprint worker is single-flight via lock file with stale-lock recovery.
