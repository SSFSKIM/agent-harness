---
status: stable
last_verified: 2026-06-28
owner: harness
type: knowledge
tags: [codex, review, methodology, reliability]
description: Codex review subagents can return a confident SATISFIED with hallucinated evidence (invented types/cites) when their shell output degrades mid-review; always corroborate the verdict with a real-code reviewer and treat its cited file:line as suspect.
---
# Codex review verdicts can confabulate

A field note promoted from session memory. When dispatched as a spec-compliance /
code-quality reviewer (via the `codex` rescue path), Codex can return a confident
verdict (e.g. `SATISFIED`) whose **evidence is fabricated**. Observed: Codex's
shell stdout channel degraded mid-review (it stopped surfacing command output),
and it then "reconstructed" implementation detail that did not exist — an imagined
dataclass and a finalize parameter, when the real code used a plain dict and a
different disposition shape. The conclusion happened to be right, but only because
independent Claude reviewers (`review-arch` + `review-reliability`) verified the
same properties against the real code with accurate line cites.

**Why:** a codex review verdict is only as trustworthy as its ability to *read*
the files; a tooling failure produces plausible-but-invented grounding rather than
an error.

## How to apply

- **Always pair a codex review verdict with at least one real-code reviewer** (a
  risk persona, or a `general-purpose` agent carrying the rubric — see
  [mid-session agents are not dispatchable](mid-session-agents-not-dispatchable.md)),
  and trust the verdict **only where they corroborate**.
- Treat codex's cited `file:line` / type names as **suspect** unless re-confirmed
  against the code.

The review-reliability companion to
[codex review companion scoping](codex-review-companion-scoping.md) (which covers
*which* codex review command to use): together they say **codex review is useful
but flaky — corroborate scope and evidence both.**
