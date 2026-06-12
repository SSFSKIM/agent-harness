---
status: open
last_verified: 2026-06-12
owner: imprint-job
---
# Open question: should tracker `fixed` rows cite the implementing commit SHA?

## Background

Surfaced by `agent-harness:review-arch` reviewing commit `28382ef` (tech-debt m4).

When a tech-debt row is moved to `fixed`, the current tracker schema has no field for
the implementing commit SHA or verified source location. A premature `fixed` close is
possible if the review only checks the tracker row, not the actual code.

## Proposed rule (review-arch, not blocking)

> A debt row may only move to `fixed` when the implementing commit SHA or the verified
> source location is cited in the tracker row.

## Why this matters

The tech-debt tracker is also read by doc-gardener and imprint jobs. A falsely-`fixed`
row provides false confidence. Citing the commit makes verification a one-step lookup.

## Considerations

- Current tracker format is a markdown table with fixed columns (Item, Severity, Found,
  Source, Status). Adding a SHA column changes the schema; or the SHA could go in the
  Item cell.
- For doc-only fixes (like m4), the "implementing commit" *is* the tracker update — so
  the rule needs a carve-out or a clarifying definition of "implementing".
- Not blocking current work; can be addressed in a future gardening session.
