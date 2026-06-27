---
status: stable
last_verified: 2026-06-28
owner: harness
type: knowledge
tags: [git, worktree, commit-gate, operating-gotcha]
description: Doing real work inside a worktree of this repo hits two traps — a fresh worktree only materializes tracked files (gate-needed untracked assets are absent), and the pre-commit hook gates the MAIN repo not your worktree; a backgrounded commit also hangs the hook.
---
# Worktree operating gotchas (gate + hook)

A field note promoted from session memory. Three traps bite when doing real work
inside a `git worktree` of this repo. They extend
[worktrees don't isolate from concurrent agents](worktrees-dont-isolate-from-concurrent-agents.md)
and [parallel sessions share one master index](parallel-sessions-share-master-index.md).

## 1. A fresh worktree only materializes *tracked* files

Untracked-but-locally-present assets the gate depends on are silently absent.
Concretely in this repo: `docs/symphony-original/` (the vendored Symphony
SPEC/WORKFLOW that the doc link-check resolves against) is **gitignored**, so a
new worktree doesn't have it → `lint_docs` D5 fails with broken-link errors on
files you never touched. **Fix = restore env parity** (`cp -R` the gitignored
asset into the worktree; it won't be committed). Diagnose env mismatch *before*
"fixing" links — this is not a defect in your diff.

## 2. The pre-commit hook gates the MAIN repo, not your worktree

`.git/hooks/pre-commit` runs `check.py --root <main repo>`, so **any** worktree
commit is gated against the main tree — which a concurrent session may have left
transiently RED. So work like this:

- Run `python3 plugin/scripts/check.py` **in the worktree** yourself (that is the
  real gate for your branch), then `git commit --no-verify`.
- Stage only your own files by name (never `git add -A` — the shared-index
  hazard).

## 3. A backgrounded commit in a worktree hangs the hook

Committing inside a worktree via a background shell hangs the pre-commit hook:
it spawns idle `check.py --root <main repo>` processes and **empties the
worktree's index** (`git status` shows the whole tree as staged-deletion +
untracked). No data is lost — `HEAD`/refs/objects stay intact, only the index is
trashed and the commit hangs.

**Recovery (non-destructive):** stop the background commit (which kills its
`check.py` children) → `git reset --mixed HEAD` in the worktree (rebuilds the
index from `HEAD`, never touches the working tree) → `git commit --no-verify` in
the **foreground**.

**Rule:** commit in this repo's worktrees in the **foreground** with
`--no-verify` after a manual gate — never via a background shell. The
hook + non-interactive background shell + worktree-vs-main-root mismatch is the
trap.
