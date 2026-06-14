# AGENTS.md — agent-harness

Self-hosting AI-native harness for big software development on local Claude Code.
This file is a **map, not an encyclopedia** (max 120 lines, lint-enforced).
Deep truth lives in `docs/` — follow the pointers.

## Operating model — every session, in order

1. **Orient.** A context pack is normally injected at session start (feeder,
   currently off). If absent: read the active plans in `docs/exec-plans/active/`,
   scan `docs/design-docs/index.md`, and skim the latest `docs/journal/` month.
2. **Plan.** Non-trivial work gets a living ExecPlan in `docs/exec-plans/active/`
   (method: `docs/PLANS.md`; procedure: `execplan` skill). Small changes need
   only a throwaway in-conversation plan.
3. **Implement.** Respect the layer law in `ARCHITECTURE.md`. Match existing
   style. New knowledge pages: the `docs-tree` skill decides where they live.
4. **Validate.** `python3 plugin/scripts/check.py` must be GREEN before every
   commit (`harness-lint` skill interprets failures).
5. **Review.** Declaring an ExecPlan complete triggers the completion gate:
   self-review the diff first, then dispatch review-arch + review-reliability in
   parallel (review-security only when the diff touches the live exec surface —
   hooks / `.harness.json` / `.harnessignore`; the rest of the threat model is
   dormant with the disabled memory loop); iterate until satisfied (`execplan`).

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
| `docs/journal/` | Episodic ledger — dream-run provenance + residual memory |
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
  `docs/` (the dreaming router files them into their docs home; verify in doubt).
- **Negative space.** Commands/scripts not named in this map or a skill are
  out of scope for routine work — do not run them ad hoc.

## Porting

- The `harness-init` skill bootstraps this harness into another host repo:
  deterministic scaffold (`scaffold.py`) → write the map → migrate existing
  docs → adapt seeds → mechanize the host's invariants (the `architecture-setup`
  skill routes each by FORM — lints under `.claude/lints/` wired via
  `.harness.json`, guide-skills under `.claude/skills/`) → check GREEN. Templates
  live inside the skill. The harness enforces only its own structure; a host's
  app-code rules are the host's, not hardcoded here (ARCHITECTURE invariant 7).

## Memory (one brain = docs)

- The `docs/` tree IS the long-term memory (progressive disclosure: this map →
  subtree indexes → leaf pages). No separate memory layer — see
  `docs/design-docs/memory-architecture.md`.
- **Write (live):** the `dream-rollouts` skill (`dream_run.py`) mines past
  session transcripts — Phase 1 extracts, Phase 2 ROUTES each distilled claim
  into its docs home (design-docs / tech-debt-tracker / `docs/journal/`). A
  read-only agent proposes a routing plan; a deterministic applicator appends.
  Episodic / provenance residue lands in `docs/journal/`.
- **Read:** the feeder INJECT path is off; its relevance/cost is an open question
  (`memory-architecture.md`). For now, orient from the map + active plans.
- The old `imprint`/`dream`/`garden` loop is dormant, being retired onto this
  engine. Bare hosts (no docs library) use the sandbox-store fallback.
