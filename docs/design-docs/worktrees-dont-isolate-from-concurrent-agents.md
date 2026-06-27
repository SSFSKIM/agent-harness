---
status: stable
last_verified: 2026-06-28
owner: review-reliability
type: knowledge
tags: [git, worktree, concurrency, operating-gotcha, recovery]
description: A git worktree shares the repo's single .git (refs + objects + core.bare), so it does NOT isolate you from other sessions mutating the repo; use a separate clone for true isolation, and follow the ref-clobber recovery playbook.
---
# Worktrees don't isolate from concurrent agents

A field note promoted from session memory. A `git worktree` gives a separate
working **directory** but shares the one `.git` — object store, refs, and
`core.bare` — with the main repo and every other worktree. So a worktree does
**not** isolate you from concurrent agents/sessions operating on the same repo.
A working tree can even be **reverted under you** between two of your commits, so
a later commit silently drops the earlier one's *content* while git history stays
linear.

## When to reach for what

- **Sole writer?** A worktree is fine for per-branch interactive dev.
- **True isolation from concurrent writers?** Use a **separate `git clone`** (its
  own `.git`). This machine runs multiple background sessions on the same repo;
  assume the shared repo is being mutated under you.
- A `cannot lock ref 'HEAD'` / branch-moved-under-you error means a concurrent
  writer — **stop, preserve, coordinate**; do not blind-retry.

## Recovery playbook — a ref was clobbered (keeps the worktree)

Moving a ref destroys nothing — every reachable commit survives, symmetric both
ways. So recovery is non-destructive:

1. `git reflog` → find your real tip.
2. `cp` uncommitted files **outside git** (e.g. `/tmp`), and `git branch`/`git tag`
   to pin **both** your tip and the clobbering lineage.
3. **Guard against a foreign-index reset:** check `git ls-files | wc -l` against
   the expected repo size *before* staging. If it collapsed (e.g. 227 → 24), a
   concurrent small-tree commit reset the **shared index** — staging+committing
   now would build from the foreign skeleton and **delete your whole repo from
   the branch tip**.
4. `git reset --mixed <your-real-tip>` → rebuilds the index to your full tree;
   the **working tree is untouched**, so your edits remain as plain
   modifications.
5. Run the gate manually, then `git commit --no-verify` (the fast write dodges
   the pre-commit window — see
   [parallel sessions share one master index](parallel-sessions-share-master-index.md)).
   Stage your **own** files by name; a concurrent agent's unrelated edits may be
   live in the shared tree.

### Fast diagnostics

- **`create mode 100644 <path>` for a file you only modified** → your commit
  parented on a concurrent session's divergent (seed/reset) tree where that file
  doesn't exist; it orphans when they reset `HEAD` back. A *mixed* reset leaves
  your edits in the working tree — re-add by name and re-commit once `HEAD` is
  back on the real tip.
- **`core.bare` flipped to `true` on a populated checkout** (every command fails
  `must be run in a work tree`): commit via an explicit override
  `git --git-dir=.git --work-tree=. add/commit` (mutates no shared config), then
  repair `git config core.bare false`. Don't re-toggle in a loop with the other
  session.
- **After any multi-commit sequence, do not assume `HEAD` linearly contains your
  earlier commits' *content*** — verify (`git show <sha>:<file> | grep`). A later
  commit on a silently-reverted tree erases earlier edits; the green gate cannot
  see this (it validates each file, not spec↔implementation consistency). A
  third-person / codex review is the backstop —
  [codex review verdict can confabulate](codex-review-verdict-can-confabulate.md).

## Related

- [parallel sessions share one master index](parallel-sessions-share-master-index.md) — the index/`git add -A` angle; these pair.
- [worktree operating gotchas](worktree-operating-gotchas.md) — env-parity + the hook-gates-the-main-root trap.
