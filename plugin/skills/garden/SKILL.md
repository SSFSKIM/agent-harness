---
name: garden
description: Use periodically (or when docs feel stale) to run the entropy GC — dispatches the doc-gardener agent and commits its cleanup.
---
# Garden

1. Dispatch the `doc-gardener` agent (Task tool): "Run your full gardening
   procedure on this repo."
2. Review its report; verify `python3 plugin/scripts/check.py` is GREEN.
3. Commit: `git add -A && git commit -m "garden: <one-line summary from report>"`.
