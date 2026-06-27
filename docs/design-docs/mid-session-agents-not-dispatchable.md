---
status: stable
last_verified: 2026-06-28
owner: harness
type: knowledge
tags: [agents, platform, dogfooding, operating-gotcha]
description: A plugin agent .md created mid-session is not dispatchable by subagent_type until the next session — the agent registry loads at session start; dogfood it via a general-purpose agent carrying the new agent's rubric verbatim.
---
# Mid-session agents are not dispatchable

A field note promoted from session memory. When you create a new agent under
`plugin/agents/` (or any plugin agent dir) **during a session**, the Agent tool
will **not** find it by `subagent_type` that same session — e.g.
`Agent type 'agent-harness:review-spec-compliance' not found` — even though the
file is on disk and correct. The agent registry is loaded at **session start**;
mid-session additions register only from the next session on. The same applies to
skills created mid-session.

## How to apply

- To verify/dogfood a freshly-created agent **in the same session**, dispatch a
  `general-purpose` agent carrying the new agent's rubric verbatim (same prompt
  body, diff range, output contract) — functionally identical. The named
  `subagent_type` works from the next session.
- Don't conclude the agent file is malformed; **check the available-agents list in
  the error first** — the registry simply hasn't reloaded.

This is why the dedicated review personas (`review-spec-compliance`,
`review-code-quality`, …) can't be exercised in the session that authors them —
[codex review verdict can confabulate](codex-review-verdict-can-confabulate.md)
notes that codex-or-Claude-with-rubric is then the only spec/quality review path.
