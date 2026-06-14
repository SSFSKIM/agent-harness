---
name: dream-rollouts
description: Mine recent Claude Code sessions into long-term memory via the two-phase dreaming pipeline (small-model extract → route into the docs tree). On a self-hosting repo it writes git-tracked docs (tracker rows, design-doc entries, docs/journal/) that you must review and commit; on a bare host it falls back to a sandbox memory store.
---
# Dream (rollouts)

Runs the memory pipeline over this repo's past Claude Code sessions. On a
self-hosting repo (one with `docs/design-docs/`) Phase 2 ROUTES distilled memory
into the docs tree — **these are real, git-tracked changes you must review and
commit** (`docs/design-docs/memory-architecture.md`). On a bare host (no docs
library) it falls back to the sandbox store (`.claude/harness/memories/`,
gitignored). Single-flight via a lock; safe to re-run.

1. Run the orchestrator:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/dream_run.py`
   - Phase 1 discovers eligible idle past sessions (`~/.claude/projects/<this
     repo>/*.jsonl`, aged 6h–10d), claims up to 2, and extracts one raw memory
     each with a small model. No-op is preferred — low-signal sessions store
     nothing.
   - Phase 2 selects the top stage-1 outputs and routes each distilled claim to
     its docs home via a READ-ONLY agent (proposes a JSON plan) + a deterministic
     applicator (appends onto an allowlist). The bare-host fallback instead
     rewrites the sandbox `MEMORY.md` + `memory_summary.md`.
2. Read the result JSON:
   - `phase1.results` — per rollout: `saved` / `no_output` / `failed`.
   - `phase2.status` — self-host: `routed` (with an `applied` count of
     tracker/design/journal writes) / `empty` / `skipped` / `failed`. Bare host:
     `consolidated` / `clean` / `empty` / `rejected` (a write tried to escape the
     workspace — reverted; a poisoning signal) / `skipped`.
3. **Review + commit the routed docs changes (self-host).** A `routed` run appends
   to `docs/exec-plans/tech-debt-tracker.md`, design-doc `## Decision log` /
   `## Open decisions` entries, and `docs/journal/YYYY-MM.md`. The writes are
   bounded, deduped, and secret-redacted, but routing is a model judgment — inspect
   `git diff` and commit what is correct to close the loop. (Bare host: the
   synthesized memory is gitignored runtime — nothing to commit.)
