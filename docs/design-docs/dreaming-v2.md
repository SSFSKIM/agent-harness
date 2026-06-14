---
status: draft
last_verified: 2026-06-13
owner: harness
---
# Dreaming v2 — a Codex-faithful memory-synthesis pipeline

Replicate OpenAI Codex's `codex-memories` pipeline (the open-source sibling of
the blog's "dreaming") as our memory write path. Source studied:
`sources/에이전트 추가아이디어/Agent Native/dreaming-v3-codex-memory-report.md`
and the live source at `/Users/new/Documents/GitHub/codex_somersault`
(`codex-rs/memories/**`, `state/memory_migrations/**`, `config/src/types.rs`).

**Term:** a *rollout* = one past agent session (for us: a Claude Code session
transcript `.jsonl`). "Dreaming" = a background 2-phase synthesis that turns
rollouts into curated, progressively-disclosed memory.

> **Output target superseded (2026-06-14) — see `memory-architecture.md`.** The
> Phase 1 EXTRACTION engine, curation store, and no-op gate below all stand. What
> changes is the Phase 2 OUTPUT: instead of a flat `MEMORY.md` in a self-contained
> `.claude/harness/memories/` store, dreaming becomes a router that authors
> distilled insights into the `docs/` tree (the one brain), leaving only an
> episodic ledger as residual. Read THIS doc for the engine; read
> `memory-architecture.md` for where the output now goes. The old feeder/imprint
> loop this doc calls "parallel" — and the `docs/memory/` tree it stays out of —
> were **retired/deleted** (2026-06-14, portable-propagation); treat every
> `docs/memory/`, `feeder`, `imprint`, and "parallel, not a replacement" mention
> below as historical design narrative, not current state.

## Scope (user decision 2026-06-13)
- **sqlite usage table** (fork 1 = b): a real `stage1_outputs` + `jobs` store
  with the `usage_count`/`last_usage` curation columns, closest to Codex.
- **Write-path first; replicate the dreaming, don't rewire all hooks** (fork
  2 = b): build Phase 1 (extract) + Phase 2 (consolidate) + the store + the
  locked-down synthesis agent. The feeder/INJECT read path stays OFF; trigger is
  the manual `/dream` skill (a SessionStart background trigger is a later add).

## The two phases (Codex → our adaptation)

**Phase 1 — extract (per rollout, scale-out).** Claim a bounded set of eligible
past sessions from the store, filter the transcript to memory-relevant turns,
call a *small* model with the stage-one prompt, get strict JSON
(`raw_memory`, `rollout_summary`, `rollout_slug`), redact secrets, upsert into
`stage1_outputs`. No-op is the default and preferred (empty fields → nothing
stored). Adapts Codex `phase1.rs`.

**Phase 2 — consolidate (global, serialized).** Claim a single global lock,
select the top-N stage-1 outputs (ranked by usage), sync them into the memory
workspace (`raw_memories.md` + `rollout_summaries/`), diff against the previous
baseline, and — only if the workspace is git-dirty — spawn ONE locked-down agent
that rewrites `MEMORY.md` (+ optional `skills/`) and `memory_summary.md` using
the diff for surgical add/forget. Reset the git baseline on success. Adapts
Codex `phase2.rs` + `consolidation.md`.

## Key adaptations (Codex is Rust/server; we are a local Claude Code plugin)

| Codex | Our adaptation |
|---|---|
| `threads` table (session registry) | a `sessions` view discovered from Claude transcript files (`~/.claude/projects/<proj>/*.jsonl`); mtime = idle/age signal |
| rollout jsonl | Claude transcript jsonl (our imprint already reads these) |
| SQLite state DB (built in) | NEW `sqlite3` (stdlib, S1-legal) DB at `.claude/harness/memories.db` (gitignored runtime, ARCH invariant 5) |
| `~/.codex/memories/` + its own `.git` baseline | a self-contained workspace `.claude/harness/memories/` with a NESTED `.git` baseline for diff/forgetting (Codex-faithful: out of the main repo, out of the lint-governed `docs/memory/`) |
| Phase 1 model `gpt-5.4-mini`/Low | `claude -p --model haiku` |
| Phase 2 model `gpt-5.4`/Medium | `claude -p --model sonnet` |
| rate-limit guard (backend quota) | SKIP (local, no backend quota) — Codex-server-specific |
| locked-down agent: `writable_roots=[memory_root]`, no network, ephemeral, no memory tool | `claude -p` with least-privilege `--allowedTools`, `cwd = workspace`, HARNESS_HEADLESS guard, **+ a post-hoc git check that reverts any write outside the workspace** (Claude Code has no writable-roots sandbox — the post-check is how we path-scope, also closing the open "imprint child unscoped Write" tracker item) |
| lease/claim job queue, concurrent workers | KEEP the schema (`jobs` lease columns) but at single-dev scale the single-flight lock + at-least-once is what we actually need; concurrency cap small |

## The curation loop (the point — fork 1)
Selection ranks by `usage_count DESC, COALESCE(last_usage, source_updated_at)
DESC` and evicts rows unused past `max_unused_days`. The usage *recording*
(citations → `record_stage1_output_usage`) has no live source while the read
path is off, so the table starts usage-empty and selection falls back to
recency (`source_updated_at`) — exactly Codex's never-used fallback. Usage
recording is wired when the read path returns (out of scope here); the schema is
built ready for it.

## Config defaults (Codex `MemoriesConfig`, adopted)
`max_rollouts_per_startup=2 · max_rollout_age_days=10 · min_rollout_idle_hours=6
· max_raw_memories_for_consolidation=256 · max_unused_days=30`. (Dropped:
`min_rate_limit_remaining_percent` — no backend quota.) Overridable via env /
`.harness.json` later; constants for now.

## Security (the dormant memory-loop threats reactivate WITH this loop)
This rebuilds the write path the deferred T1/T2/T4/T6/T7 model guards
(SECURITY.md is scoped-dormant; reactivate here). Carried over faithfully from
Codex + our model: transcripts/rollout text are DATA not instructions (T1);
secret redaction before the model sees anything (T4); least-privilege headless
child (T5).

**Phase 1 (extract) — the strongest posture, because it ingests untrusted
transcript content:** the model runs with `--allowedTools ""` (NO Read/Write/
Bash/network), so an instruction injected into a rollout has no mechanism to act
— stronger than Codex's writable-roots sandbox, which still permits reads. This
supersedes the earlier "pass a path" T6 wording for Phase 1: we carry a
redacted+filtered DIGEST (never the raw rollout) and pipe it via STDIN (out of
`ps`/ARG_MAX), so there is no file to point at and nothing to read. Redaction
runs before the model AND on its output before storage (defense in depth).

**Phase 2 (consolidate)** still needs file access (it writes `MEMORY.md`), so it
keeps the path-scoped form: reads diff/summaries (digest-derived) → inline DATA
guard (T7); **the post-hoc workspace-scope check is the real path restriction
(T2/poisoning).**

## What this is NOT (v2 boundaries)
No feeder/INJECT rewiring; no SessionStart auto-trigger (manual `/dream`); no
usage-recording source yet; no `extensions/ad_hoc` user-edit notes; the existing
hand-maintained `docs/memory/` tree is untouched (dreaming is a parallel,
self-contained workspace).
