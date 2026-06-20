# AGENTS.md — agent-harness

Self-hosting AI-native harness for big software development on local Claude Code.
This file is a **map, not an encyclopedia**.
Deep truth lives in `docs/` — follow the pointers.

## Operating model — every session, in order

1. **Orient — proportionally.** Orientation is a tool, not a forced first step.
   For a broad or unfamiliar change, anchor on intent before the session drifts:
   read [the charter](docs/CHARTER.md) (mission, design philosophy (기획의도),
   locked assumptions) and run `python3 plugin/scripts/nav.py map` (charter →
   initiatives → phases → status). For a small, well-scoped change, skip the
   survey and go straight to the work — over-orienting a focused ticket just burns
   context. The `docs-nav` skill (`nav.py` — `map`/`catalog`/`tree`/`backlinks`) is
   the on-demand way to explore the docs corpus by querying, not bulk-reading,
   whenever a task actually needs it. Session continuity uses Claude Code's
   **native memory** — the harness ships no feeder/imprint loop; durable knowledge
   lives in `docs/` (decisions in `docs/adr/`, evolution in `docs/logs.md`).
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
| `.claude/DIRECTOR.md` | Director operating manual (central-agent config, not a docs/ page): identity, taste-vs-handle, the watched event-loop — reading it is how a session becomes the Director |
| `docs/PLANS.md` | ExecPlan methodology |
| `docs/PRODUCT_SENSE.md` | What we optimize: minimum human-in-loop |
| `docs/PRINCIPLES.md` | The human's externalized decision-taste; the Director consults it to simulate the human's call before escalating (lights-out, ADR 0003) |
| `docs/QUALITY_SCORE.md` | Domain × layer grades, gap tracking over time |
| `docs/RELIABILITY.md` | Hook/queue failure modes, idempotency rules |
| `docs/SECURITY.md` | Threat model: transcripts, hook perms, exec surface |
| `docs/adr/` | Architecture Decision Records — durable decisions + why |
| `docs/logs.md` | On-demand, milestone-grained project/docs-evolution log |
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
  `docs/` — an ADR in `docs/adr/`, a knowledge page, or a `docs/logs.md` entry.
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

## Porting / adopting

The harness has **two halves with two distribution models** — the *method* travels
into your repo, the *Director* stays here and reaches out:

- **The method → your repo.** The `harness-init` skill bootstraps this harness into another host repo:
  deterministic scaffold (`scaffold.py`) → write the map → migrate existing
  docs → adapt seeds → mechanize the host's invariants (the `architecture-setup`
  skill routes each by FORM — lints under `.claude/lints/` wired via
  `.harness.json`, guide-skills under `.claude/skills/`) → check GREEN. Templates
  live inside the skill. The harness enforces only its own structure; a host's
  app-code rules are the host's, not hardcoded here (ARCHITECTURE invariant 7).
- **The Director → run from here.** The orchestration layer (`director/`) is
  **centralized**, not ported: you run it from *this* repo against your project's
  Linear board + git repo (workers clone your repo into a scratch workspace).
  To stand it up against a project from zero, see
  [.claude/DIRECTOR.md](.claude/DIRECTOR.md) §0 ("Standing up the Director against
  a project") — reading that file is how a session becomes the Director.

## Memory (read/write paths)

- Session continuity uses Claude Code's **native memory** — the harness ships no
  feeder/imprint/dream loop (retired; see `docs/logs.md`). Durable,
  version-controlled knowledge lives in `docs/`: decisions in `docs/adr/`,
  deferred work and open questions in `docs/exec-plans/tech-debt-tracker.md`, and
  the evolution narrative in `docs/logs.md` (read on-demand, not auto-loaded).
  `garden` remains a manual GC tool.
