---
status: stable
last_verified: 2026-06-28
owner: harness
---
# Design docs

Catalog of design documents. Add new pages here (lint D8 enforces).

- agent-harness.md — the installed harness: components, gate command
- core-beliefs.md — golden rules + agent-first operating principles
- symphony-parity-gap.md — how `director/` diverges from original Symphony (`docs/symphony-original/`): the two bets, what we match/exceed, the ranked gaps
- okf-comparison.md — Google's Open Knowledge Format (OKF v0.1) vs our docs system: the shared markdown+frontmatter substrate, what OKF advanced (type/resource/tags/spec/viz), what we advanced (enforced gate, staleness, epistemic taxonomy), ranked adoptions
- recursion-guard.md — the `HARNESS_HEADLESS` env guard that prevents infinite SessionStart recursion when a hook spawns a headless claude child (migrated from the retired `docs/memory/knowledge/`)

## Field notes (promoted from session memory)

Reusable agent & review methodology lessons, promoted out of an agent's private
memory into the repo so they are shared and resolvable.

- codex-review-verdict-can-confabulate.md — codex review verdicts can hallucinate evidence when shell output degrades; corroborate with a real-code reviewer
- own-context-for-synthesis-tasks.md — read both sides yourself for synthesis/comparison; delegate only breadth-sweep find/locate work
