---
name: dream-rollouts
description: Consolidate recent Claude Code sessions into Codex-style structured memory at .claude/harness/memories/MEMORY.md. Runs the two-phase dreaming pipeline (Haiku extract then Sonnet consolidate). Parallel to the docs/memory `dream` skill — does not touch docs/memory.
---
# Dream (rollouts)

Runs the Codex-faithful memory pipeline over this repo's past Claude Code
sessions. Writes ONLY under `.claude/harness/memories/` (gitignored runtime) —
the `docs/memory/` tree and the `dream` skill are untouched. Single-flight via a
lock; safe to re-run.

1. Run the orchestrator:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/dream_run.py`
   - Phase 1 discovers eligible idle past sessions (`~/.claude/projects/<this
     repo>/*.jsonl`, aged 6h–10d), claims up to 2, and extracts one raw memory
     each with a small model. No-op is preferred — low-signal sessions store
     nothing.
   - Phase 2 selects the top stage-1 outputs, and — only if the memory workspace
     actually changed — runs ONE locked-down model to rewrite `MEMORY.md` +
     `memory_summary.md`.
2. Read the result JSON:
   - `phase1.results` — per rollout: `saved` / `no_output` / `failed`.
   - `phase2.status` — `consolidated` (memory updated) / `clean` (nothing
     changed) / `empty` (no memories to consolidate yet) / `rejected` (see
     `escaped`/`problems`) / `skipped` (lock/cooldown).
   - `rejected` with a non-empty `escaped` means a consolidation tried to write
     OUTSIDE the workspace; the write was reverted and the run rolled back. This
     is a poisoning signal worth investigating.
3. The synthesized memory lives at `.claude/harness/memories/MEMORY.md` and
   `memory_summary.md` (first line `v1`). It is gitignored runtime state —
   nothing to commit.
