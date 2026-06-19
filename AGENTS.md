# AGENTS.md — agent-harness

Self-hosting AI-native harness for big software development on local Claude Code.
This file is a **map, not an encyclopedia**.
Deep truth lives in `docs/` — follow the pointers.

## Operating model — every session, in order

1. **Orient.** Read [the charter](docs/CHARTER.md) first — mission, design
   philosophy (기획의도), and locked assumptions — to anchor on intent before a
   long session drifts; `python3 plugin/scripts/nav.py map` renders the whole
   picture against it (charter → initiatives → phases → status). The automatic context feeder is disabled: read
   `docs/memory/MEMORY.md` when you need continuity and follow its loading
   protocol. When you need to explore the docs corpus — its structure,
   relationships, and per-page gist — use the `docs-nav` skill (`nav.py`) by
   querying, not bulk-reading.
2. **Plan.** Pick the entry mode (method: `docs/PLANS.md` entry decision): a
   throwaway in-conversation plan for small work; **Product Design** (write a
   spec in `docs/product-specs/` via the `product-design` skill) when the *what*
   must be settled before the *how*; otherwise a living ExecPlan in
   `docs/exec-plans/active/` (`execplan` skill). No ceremony when risk is low.
3. **Implement.** Respect the layer law in `ARCHITECTURE.md`. Match existing
   style. New knowledge pages: the `docs-tree` skill decides where they live; the
   `docs-nav` skill (`nav.py`) queries existing docs — `map`/`tree` for the
   picture and relationships, `catalog`/`backlinks` to find and pre-check — query,
   don't bulk-read.
4. **Validate.** `python3 plugin/scripts/check.py` must be GREEN before every
   commit (`harness-lint` skill interprets failures).
5. **Review.** Always self-review. A conditional **behavioral check** (run the plan's
   acceptance + a smoke/E2E pass for any runnable surface; web → `playwright-cli`)
   precedes the reviews. Two QA reviews — **spec-compliance** then **code-quality** —
   run at *every* ExecPlan completion (always-on, regardless of `review_level`);
   `review_level` governs only the additional *risk personas* (arch/reliability/security)
   dispatched at the level the plan calls for (`execplan`). Security review is reserved
   for the live exec surface.

## Map

| Path | What it is |
|---|---|
| `docs/CHARTER.md` | Top-level intent: mission, design philosophy (기획의도), locked assumptions — the Orient anchor |
| `ARCHITECTURE.md` | Codemap, layer law, invariants, data flows |
| `docs/KNOWLEDGE_FORMAT.md` | The knowledge format (KF v1.2): frontmatter schema, optional keys (`type`/`tags`/`resource`/`phase`/`supersedes`/`title`/`description`), conformance↔D-rule map |
| `docs/design-docs/core-beliefs.md` | Golden rules + agent-first operating principles |
| `docs/design-docs/index.md` | Design docs catalog |
| `docs/exec-plans/` | Living plans: `active/`, `completed/`, `tech-debt-tracker.md` |
| `docs/generated/` | Script-generated (component inventory); never hand-edit |
| `docs/product-specs/` | What this harness is, product-wise |
| `docs/references/` | llms.txt digests of external APIs we depend on |
| `docs/DESIGN.md` | Taste rules for skills / agents / hooks / scripts |
| `docs/DIRECTOR.md` | Director operating manual: identity, taste-vs-handle, the watched event-loop (`director` launcher skill enters it) |
| `docs/PLANS.md` | ExecPlan methodology |
| `docs/PRODUCT_SENSE.md` | What we optimize: minimum human-in-loop |
| `docs/PRINCIPLES.md` | The human's externalized decision-taste; the Director consults it to simulate the human's call before escalating (lights-out, ADR 0003) |
| `docs/QUALITY_SCORE.md` | Domain × layer grades, gap tracking over time |
| `docs/RELIABILITY.md` | Hook/queue failure modes, idempotency rules |
| `docs/SECURITY.md` | Threat model: transcripts, memory poisoning, hook perms |
| `docs/memory/` | Structured long-term memory (`MEMORY.md` = bootloader) |
| `plugin/` | The machine: skills, agents, hooks, scripts (portable) |
| `tests/` | unittest suite for plugin scripts |

## Laws (short form — full text: docs/design-docs/core-beliefs.md)

- **No hand-written code.** Humans steer via prompts, reviews, docs feedback only.
- **Minimal blocking gates.** Only `check.py` blocks a commit; everything else
  is risk-budgeted or fix-forward via `tech-debt-tracker.md` / ExecPlan feedback.
- **Escalate only on judgment.** Mechanical answers (lint, tests, documented
  decisions) → proceed. Taste / product tradeoffs → ask the human.
- **Struggling = harness gap.** If you fight the repo, diagnose what is missing
  (tool, guardrail, doc), encode the fix into the repo, then retry.
- **Feedback twice → promote.** Any human correction given twice becomes a doc
  rule or a lint.
- **Not in the repo = does not exist.** Decisions made in chat must end up in
  `docs/` or `docs/memory/` (imprint hooks do this; verify when in doubt).
- **Preferred paths, not negative space.** Named commands and skills are the
  routine path. Extra CLI exploration is allowed when it serves the task; if it
  repeats, promote it into docs, a skill, or the gate.
- **General by identity; propagate to the portable layer.** This repo is both the
  portable *machine* and its first *host*. A change to how the harness works must
  land in the portable layer (`plugin/` + `harness-init` templates + `scaffold.py`
  seeds + generic skills, host-agnostic — lint S7), not only self-host `docs/` —
  what lands only self-host doesn't exist for ported hosts. Mechanize the
  propagation where you can (e.g. the machine-doc→seed guard). Full text: core
  belief 13.

## Porting

- The `harness-init` skill bootstraps this harness into another host repo:
  deterministic scaffold (`scaffold.py`) → write the map → migrate existing
  docs → adapt seeds → mechanize the host's invariants (the `architecture-setup`
  skill routes each by FORM — lints under `.claude/lints/` wired via
  `.harness.json`, guide-skills under `.claude/skills/`) → check GREEN. Templates
  live inside the skill. The harness enforces only its own structure; a host's
  app-code rules are the host's, not hardcoded here (ARCHITECTURE invariant 7).

## Memory (read/write paths)

- The automatic feeder/imprint memory loop is disabled pending redesign.
  Maintain `docs/memory/` by hand for now; `/dream` and `garden` remain manual
  tools. Never bypass `docs/memory/` structure.
