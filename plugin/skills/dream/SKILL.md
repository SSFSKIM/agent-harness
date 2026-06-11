---
name: dream
description: Use periodically (or after several work sessions) to consolidate memory — dispatches the dreamer agent over recent session digests and commits the result.
---
# Dream

1. Dispatch the `dreamer` agent (Task tool, subagent_type
   `agent-harness:dreamer`): "Run your full consolidation procedure."
2. Verify `python3 plugin/scripts/check.py` is GREEN; skim `git diff` of
   docs/memory/ (sanity, not approval — dreaming writes directly).
3. Update the marker:
   `date +%F > .claude/harness/last-dream.txt`
4. Commit: `git add -A && git commit -m "dream: <one-line summary from report>"`.
   (`-A` is safe: the runtime state dir `.claude/harness/` is gitignored.)
