# AGENTS.md — {{PROJECT}}

<!-- FILL: one sentence — what this repo is and does. -->

This file is a **map, not an encyclopedia**. Keep it short; the default line
cap is host-overridable when the map genuinely needs more room.
Deep truth lives in `docs/` — follow the pointers.

## Operating model — every session, in order

1. **Orient — proportionally.** Orientation is a tool, not a forced first step.
   For a broad or unfamiliar change, anchor on intent: read
   [the charter](docs/CHARTER.md) (mission, design philosophy, locked assumptions)
   and run the `docs-nav` skill's `nav.py map`. For a small, well-scoped change,
   skip the survey and go straight to the work — over-orienting a focused ticket
   just burns context. The `docs-nav` skill (`nav.py`) is the on-demand way to
   explore the docs corpus by querying, not bulk-reading, whenever a task needs it.
   The automatic context feeder may be disabled: read `docs/memory/MEMORY.md`
   when you need continuity and follow its loading protocol.
2. **Plan.** Pick the entry mode (method: `docs/PLANS.md` entry decision): a
   throwaway in-conversation plan for small work; **Product Design** (write a
   spec in `docs/product-specs/` via the `product-design` skill) when the *what*
   must be settled before the *how*; otherwise a living ExecPlan in
   `docs/exec-plans/active/` (execplan skill). No ceremony when risk is low.
3. **Implement.** Match existing style. New knowledge pages: placement table
   in [the harness page](docs/design-docs/agent-harness.md). Find existing docs
   by querying — the `docs-nav` skill (`nav.py`: map/tree/catalog/backlinks/…)
   — not by bulk-reading.
4. **Validate.** The harness lint gate must be GREEN before every commit —
   exact command in [the harness page](docs/design-docs/agent-harness.md).
5. **Review.** Two QA reviews (spec-compliance then code-quality) run at *every*
   ExecPlan completion; `review_level` governs only the additional risk personas
   dispatched at the level the plan calls for. Always self-review (execplan skill).
6. **Write back.** Update `docs/memory/progress/current.md` before ending a
   long session. The automatic memory loop may be disabled; follow the harness
   page for the current mode.

## Map

| Path | What it is |
|---|---|
<!-- FILL: rows for this repo's real source layout (src/, build, test cmds). -->
| `docs/CHARTER.md` | Top-level intent: mission, design philosophy, locked assumptions — the Orient anchor |
| `docs/design-docs/core-beliefs.md` | Golden rules (agent-first operating principles) |
| `docs/design-docs/agent-harness.md` | The installed harness: components, memory loop, gate |
| `docs/exec-plans/` | Living plans: `active/`, `completed/`, `tech-debt-tracker.md` |
| `docs/memory/` | Structured long-term memory (`MEMORY.md` = bootloader) |
| `docs/product-specs/` | What this product is, behavior-wise |
| `docs/references/` | Digests of external APIs this repo depends on |
| `docs/RELIABILITY.md` | Failure-mode rules (review grounding; grows over time) |
| `docs/SECURITY.md` | Threat model (review grounding; grows over time) |

## Laws (short form — full text: docs/design-docs/core-beliefs.md)

- **Not in the repo = does not exist.** Decisions made in chat must be encoded
  into `docs/` or `docs/memory/`.
- **Map, not encyclopedia.** Entry points stay short; depth behind pointers.
- **Minimal blocking gates.** Only the deterministic check gate blocks a
  commit; everything else is fix-forward via the tech-debt tracker.
- **Feedback twice → promote.** A repeated human correction becomes a doc
  rule or a lint.

## Mandatory skill usage

<!-- FILL: repo-local skills in .claude/skills/ that sessions MUST use and
when — at minimum a `verify` skill encoding this repo's check order. -->

Named commands and skills are the preferred routine path. Extra CLI exploration
is allowed when it serves the task; if it repeats, promote it into docs, a
skill, or the gate.
