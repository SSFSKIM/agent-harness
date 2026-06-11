# AGENTS.md — agent-harness

Self-hosting AI-native harness for big software development on local Claude Code.
This file is a **map, not an encyclopedia** (max 120 lines, lint-enforced).
Deep truth lives in `docs/` — follow the pointers.

## Operating model — every session, in order

1. **Orient.** A context pack is normally injected at session start (feeder).
   If missing, read `docs/memory/MEMORY.md` and follow its loading protocol.
2. **Plan.** Non-trivial work gets a living ExecPlan in `docs/exec-plans/active/`
   (method: `docs/PLANS.md`; procedure: `execplan` skill). Small changes need
   only a throwaway in-conversation plan.
3. **Implement.** Respect the layer law in `ARCHITECTURE.md`. Match existing
   style. New knowledge pages: the `docs-tree` skill decides where they live.
4. **Validate.** `python3 plugin/scripts/check.py` must be GREEN before every
   commit (`harness-lint` skill interprets failures).
5. **Review.** Declaring an ExecPlan complete triggers the completion gate:
   self-review the diff first, then dispatch review-arch, review-reliability,
   review-security in parallel; iterate until all are satisfied (`execplan` skill).

## Map

| Path | What it is |
|---|---|
| `ARCHITECTURE.md` | Codemap, layer law, invariants, data flows |
| `docs/design-docs/core-beliefs.md` | Golden rules + agent-first operating principles |
| `docs/design-docs/index.md` | Design docs catalog |
| `docs/exec-plans/` | Living plans: `active/`, `completed/`, `tech-debt-tracker.md` |
| `docs/generated/` | Script-generated (component inventory); never hand-edit |
| `docs/product-specs/` | What this harness is, product-wise |
| `docs/references/` | llms.txt digests of external APIs we depend on |
| `docs/DESIGN.md` | Taste rules for skills / agents / hooks / scripts |
| `docs/PLANS.md` | ExecPlan methodology |
| `docs/PRODUCT_SENSE.md` | What we optimize: minimum human-in-loop |
| `docs/QUALITY_SCORE.md` | Domain × layer grades, gap tracking over time |
| `docs/RELIABILITY.md` | Hook/queue failure modes, idempotency rules |
| `docs/SECURITY.md` | Threat model: transcripts, memory poisoning, hook perms |
| `docs/memory/` | Structured long-term memory (`MEMORY.md` = bootloader) |
| `plugin/` | The machine: skills, agents, hooks, scripts (portable) |
| `tests/` | unittest suite for plugin scripts |

## Laws (short form — full text: docs/design-docs/core-beliefs.md)

- **No hand-written code.** Humans steer via prompts, reviews, docs feedback only.
- **Minimal blocking gates.** Only `check.py` blocks a commit; everything else
  is fix-forward via `tech-debt-tracker.md` or ExecPlan feedback.
- **Escalate only on judgment.** Mechanical answers (lint, tests, documented
  decisions) → proceed. Taste / product tradeoffs → ask the human.
- **Struggling = harness gap.** If you fight the repo, diagnose what is missing
  (tool, guardrail, doc), encode the fix into the repo, then retry.
- **Feedback twice → promote.** Any human correction given twice becomes a doc
  rule or a lint.
- **Not in the repo = does not exist.** Decisions made in chat must end up in
  `docs/` or `docs/memory/` (imprint hooks do this; verify when in doubt).

## Memory (read/write paths)

- Read: feeder injects a compiled context pack at SessionStart + a targeted
  addendum on the session's first prompt.
- Write: PreCompact/SessionEnd hooks enqueue imprint jobs; `/dream` (dreamer
  agent) consolidates; `garden` (doc-gardener agent) GCs docs entropy.
  Never bypass `docs/memory/` structure; lint enforces frontmatter and indexes.
