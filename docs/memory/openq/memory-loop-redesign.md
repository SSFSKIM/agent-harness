---
status: open
last_verified: 2026-06-13
owner: harness
type: openq
tags: [memory, feeder, imprint, hooks, redesign]
description: The automatic memory loop (feeder/imprint hooks) is disabled pending a redesign that earns its place in every session.
---
# Open question: redesign the automatic memory loop

## Decision (2026-06-13)
The automatic memory loop is **disabled** — the SessionStart/UserPromptSubmit
(feeder / INJECT) and PreCompact/SessionEnd (imprint / IMPRINT) hooks were
unwired from `plugin/hooks/hooks.json` (only the Stop tidy-gate remains). The
mechanism needs more sophistication before it earns its place in every session;
running it half-baked spends headless-Claude cost + latency on every
session-start and every prompt for uncertain benefit. Until the redesign,
`docs/memory/` is maintained by hand (still lint-governed). Scripts (`feeder_*`,
`imprint_*`) and the `dream`/`garden` skills are retained, dormant.

## What a better version must solve (the sophistication gap)
- **Read path (feeder):** firing a headless Sonnet(1M) on every SessionStart +
  every first prompt is heavy and often low-signal. Open: when is injection
  actually worth it (vs the model just reading the index)? relevance targeting,
  caching, a cheaper compile, or event-gating instead of always-on.
- **Write path (imprint):** at-least-once enqueue + single-flight worker writes
  digests on PreCompact/SessionEnd. Open: dedupe/merge quality (PR-like
  MemoryManager merge), poison-entry isolation (tracker rows), commit ownership
  of the dirty memory writes, state-file rotation.
- **Consolidate (dream):** depends on imprint digests; with imprint off it has
  no input. A redesign should define where consolidation input comes from.
- **Trigger model:** maybe not lifecycle hooks at all — could be an explicit
  skill, a budget-gated step, or a smarter event filter.

## Re-enable (until the redesign lands)
Restore the four hook entries in `plugin/hooks/hooks.json` (SessionStart →
`feeder_sessionstart.py`, UserPromptSubmit → `feeder_firstprompt.py`,
PreCompact + SessionEnd → `imprint_enqueue.py`) and regenerate the inventory
(`gen_inventory.py`). The scripts and their tests are unchanged.

## Related
Tracker rows: imprint poison-entry isolation, state-file rotation, imprint
child unscoped Write, compile_pack degradation test. `docs/RELIABILITY.md`
(R2/R6/R11) and `docs/SECURITY.md` (T1/T5/T6/T7) still describe the dormant
scripts' contracts for when they return.
