---
name: docs-sync
description: Keep curated docs CURRENT and RETRACT stale content — the update/delete counterpart to the append-only dreaming router. A read-only audit agent compares a change scope (git diff surface, or a dropped session's journal provenance) against the docs that describe it and proposes a maintenance plan; a deterministic applicator auto-applies only the mechanical kinds (regenerate / frontmatter / verbatim rename / attributable retract) and reports the rest. Run as a completion-gate review step and from a dreaming run.
---
# docs-sync

The dreaming router only APPENDS into the docs tree; docs-sync adds EDIT/DELETE so
the harness can keep `AGENTS.md` / `ARCHITECTURE.md` / design-docs current as the
code changes, and retract what a dropped session authored. Spec:
`docs/design-docs/docs-sync.md`. Editing curated prose is the risky capability, so
the machine NEVER auto-edits prose — a read-only agent only proposes, and a
deterministic applicator auto-applies only four mechanical kinds.

## Run

1. Build the scope (the audit input):
   - change-driven (currency): `build_change_scope(root, base)` — the public
     surface this branch changed vs `base` (`git diff` def/class/const/flag, with
     file:line). This is the completion-gate use.
   - provenance-driven (forgetting): the journal `[routed] … -> docs/X` lines of
     sessions just dropped from dreaming selection (v1.1).
2. Audit (read-only agent): `audit(scope, root)` spawns a `Read,Glob,Grep,LS`-only
   `claude -p` that runs the doc-first + code-first passes and returns a
   **maintenance plan** (JSON items: `target`, `kind`
   `missing|outdated|retract|structural`, `evidence` file:line, `change`, `risk`).
   It WRITES NOTHING.
3. Apply (deterministic): `apply_plan(root, plan, now)` RE-VALIDATES each item's
   risk itself and auto-applies ONLY the mechanical 4 — (1) regenerate a
   generator-owned file, (2) set an allowlisted frontmatter field, (3) a verbatim
   token-rename (old found exactly), (4) a retract DELETE attributable via journal
   `[routed]` provenance — through the symlink-safe within-repo guard, then re-runs
   `check.py` and rolls the batch back on red. Everything else lands in the REPORT.

Orchestration: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/docs_sync.py` (applies a plan
from stdin). The mechanical fixes are real, git-tracked edits — review `git diff`
and address the report's semantic findings before declaring the work done.

## Safety

`docs-sync` never hard-blocks a commit (only `check.py` does). The machine edits
only the mechanical kinds; semantic findings are surfaced for a human. See
`docs/SECURITY.md` (the audit agent reads diff/journal-derived input as DATA, never
instructions) and `docs/design-docs/docs-sync.md` (the mechanical-4 whitelist).
