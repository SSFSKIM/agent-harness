---
name: dream
description: Use periodically (or after several work sessions) to consolidate memory — dispatches the dreamer agent over recent session digests and commits the result.
---
# Dream

1. Dispatch the `dreamer` agent (Task tool, subagent_type
   `agent-harness:dreamer`): "Run your full consolidation procedure."
2. Verify the gate is GREEN (command in `docs/design-docs/agent-harness.md`);
   skim `git diff` of
   docs/memory/ (sanity, not approval — dreaming writes directly).
3. Update the marker:
   `date +%F > .claude/harness/last-dream.txt`
4. Commit: `git add docs/memory/ && git commit -m "dream: <one-line summary from report>"`
   (scoped add per DESIGN.md — never `git add -A`).
