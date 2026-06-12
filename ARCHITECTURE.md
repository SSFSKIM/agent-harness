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
   gen_inventory --check + unittest. GREEN before every commit.
4. **Generated files** carry a GENERATED header; only scripts write them.
5. **Runtime state** (queues, locks, seen-sessions, processed-log) lives in
   `.claude/harness/` — gitignored, never under `docs/`.

## Data flows

1. **INJECT** — SessionStart hook → `feeder_sessionstart.py` → headless
   Sonnet(1M) reads `docs/memory/` + `docs/exec-plans/active/` → compiles a
   context pack → `additionalContext`. First user prompt →
   `feeder_firstprompt.py` → task-targeted addendum (2-stage feeder).
2. **IMPRINT** — PreCompact/SessionEnd → `imprint_enqueue.py` (at-least-once
   queue) → `imprint_run.py` (single-flight lock; dedupe via `imprint_guard`)
   → headless claude writes a session digest + memory updates → lint_docs.
3. **CONSOLIDATE** — `/dream` → dreamer agent reads `archive/sessions/`
   digests → rewrites knowledge/limitations/openq/adr directly → `check.py`
   green is the termination condition.
4. **REVIEW** — `execplan` completion gate → self-review → review-arch /
   review-reliability / review-security (each grounded 1:1 in its doc) →
   iterate until satisfied.
5. **TIDY** — Stop hook → `tidy_stop.py` → fingerprint-deduped lint subset
   on the dirty tree; FAIL blocks once per state with FIX lines (R11).
   Commits are also gated mechanically by the scaffold-installed
   `.git/hooks/pre-commit` running `check.py`.

## Failure modes

See `docs/RELIABILITY.md`. Headlines: imprint writes are idempotent (dedupe
keys), feeder degrades to a deterministic minimal pack on timeout/error,
imprint worker is single-flight via lock file with stale-lock recovery.
