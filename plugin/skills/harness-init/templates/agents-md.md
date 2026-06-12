# AGENTS.md — {{PROJECT}}

<!-- FILL: one sentence — what this repo is and does. -->

This file is a **map, not an encyclopedia** (max 120 lines, lint-enforced).
Deep truth lives in `docs/` — follow the pointers.

## Operating model — every session, in order

1. **Orient.** A context pack is normally injected at session start (feeder).
   If missing, read `docs/memory/MEMORY.md` and follow its loading protocol.
2. **Plan.** Non-trivial work gets a plan the human can see; long-running work
   gets a living ExecPlan in `docs/exec-plans/active/`.
3. **Implement.** Match existing style. New knowledge pages: placement table
   in [the harness page](docs/design-docs/agent-harness.md).
4. **Validate.** The harness lint gate must be GREEN before every commit —
   exact command in [the harness page](docs/design-docs/agent-harness.md).
5. **Write back.** Update `docs/memory/progress/current.md` before ending a
   long session; imprint hooks handle session digests automatically.

## Map

| Path | What it is |
|---|---|
<!-- FILL: rows for this repo's real source layout (src/, build, test cmds). -->
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
