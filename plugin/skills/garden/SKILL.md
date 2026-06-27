---
name: garden
description: Use periodically (or when docs feel stale) to run the entropy GC — dispatches the doc-gardener agent and commits its cleanup.
---
# Garden

1. Dispatch the doc-gardener agent: "Run your full gardening procedure on this
   repo." (HOW depends on your runtime — use whichever it exposes:
   • Claude Director (plugin): Task tool, `subagent_type:"agent-harness:doc-gardener"`.
   • Claude worker: the bare `doc-gardener` (vendored into `.claude/agents/`).
   • Codex worker: ask Codex to spawn the `doc_gardener` agent — the UNDERSCORE name
     (Codex rejects hyphens), registered from its `CODEX_HOME/agents/*.toml`.)
2. Review its report; verify the gate is GREEN (command in
   `docs/design-docs/agent-harness.md`).
3. Commit: `git add docs/ && git commit -m "garden: <one-line summary from report>"`
   (scoped add per DESIGN.md — never `git add -A`).
