# AGENTS.md — {{PROJECT}}

<!-- FILL: one sentence — what this repo is and does. -->

This file is a **map, not an encyclopedia** (max 120 lines, lint-enforced).
Deep truth lives in `docs/` — follow the pointers.

## Operating model — every session, in order

1. **Orient.** Pull the context this task needs from `docs/` (no feeder injects
   it): the latest `docs/journal/` entries, the open `docs/exec-plans/active/`
   plans, and the design-docs index — navigate via this map + Grep/Glob.
2. **Plan.** Non-trivial work gets a plan the human can see; long-running work
   gets a living ExecPlan in `docs/exec-plans/active/`.
3. **Implement.** Match existing style. New knowledge pages: placement table
   in [the harness page](docs/design-docs/agent-harness.md).
4. **Validate.** The harness lint gate must be GREEN before every commit —
   exact command in [the harness page](docs/design-docs/agent-harness.md).
5. **Review.** Declaring an ExecPlan complete triggers the completion gate:
   self-review the diff first, then dispatch the review personas; iterate
   until all are satisfied (execplan skill).
6. **Write back.** Record durable outcomes in their docs home (the placement
   table) and live progress in the active ExecPlan; the `dream-rollouts` skill
   later distills past sessions into the docs tree.

## Map

| Path | What it is |
|---|---|
<!-- FILL: rows for this repo's real source layout (src/, build, test cmds). -->
| `docs/design-docs/core-beliefs.md` | Golden rules (agent-first operating principles) |
| `docs/design-docs/agent-harness.md` | The installed harness: components, memory loop, gate |
| `docs/exec-plans/` | Living plans: `active/`, `completed/`, `tech-debt-tracker.md` |
| `docs/journal/` | Append-only episodic ledger — provenance + what docs can't hold |
| `docs/product-specs/` | What this product is, behavior-wise |
| `docs/references/` | Digests of external APIs this repo depends on |
| `docs/RELIABILITY.md` | Failure-mode rules (review grounding; grows over time) |
| `docs/SECURITY.md` | Threat model (review grounding; grows over time) |

## Laws (short form — full text: docs/design-docs/core-beliefs.md)

- **Not in the repo = does not exist.** Decisions made in chat must be encoded
  into `docs/`.
- **Map, not encyclopedia.** Entry points stay short; depth behind pointers.
- **Minimal blocking gates.** Only the deterministic check gate blocks a
  commit; everything else is fix-forward via the tech-debt tracker.
- **Feedback twice → promote.** A repeated human correction becomes a doc
  rule or a lint.

## Mandatory skill usage

<!-- FILL: repo-local skills in .claude/skills/ that sessions MUST use and
when — at minimum a `verify` skill encoding this repo's check order. -->

Commands not listed in this file or in a mandatory skill are out of scope
for routine work — do not run them ad hoc.
