---
status: stable
last_verified: 2026-06-28
owner: review-reliability
type: knowledge
tags: [git, concurrency, operating-gotcha, commit-gate]
description: Multiple agent sessions share one master working tree + index, so a sweeping `git add -A` in one absorbs another's staged files; commit `--no-verify` after a manual check.py gate and stage only your own paths.
---
# Parallel sessions share one master index

A field note promoted from session memory. This repo is routinely worked by
**several agent sessions against the same main checkout on `master` at once**
(plus worktrees and sibling clones). They share **one index and one object
store**. That sharing is the source of a recurring class of commit hazards the
green gate cannot see — record it so a session does not re-learn it the hard way.

## What goes wrong

- **`git add -A` absorption.** A concurrent session's sweeping
  `git add -A` / `git commit -a` will **stage and commit *your* already-staged
  files into *their* commit**. Your code lands intact and GREEN, but under the
  wrong message and authorship.
- **Transient tree-build corruption during the gate window.** A partial-commit
  `git commit -- <pathspec>` reads `HEAD`'s tree while the pre-commit gate holds
  a long window (tens of seconds — it runs the full suite). A concurrent
  committer moving `HEAD` mid-build makes blobs momentarily non-durable →
  `invalid object … / error building tree` on a file **you never touched**. The
  corruption is **transient and self-clears** once the other commit lands.

## How to apply

1. **Stage only your own paths, by name.** Never `git add -A` in a shared tree.
2. **Dodge the race window:** run `python3 plugin/scripts/check.py` (or the
   `harness-lint` skill) manually for GREEN, then commit with **`--no-verify`** —
   the commit becomes near-instant, closing the window in which a concurrent
   `HEAD` move can corrupt your tree build. This is the sanctioned commit pattern
   for this repo, not a shortcut.
3. **On a tree-build error, diagnose before retrying** — it is *not* a blind
   retry. Check `git cat-file -t <badobj>` (gone?) and `git ls-files -s -- <path>`
   (back to `HEAD`'s blob?); once it has self-cleared, a `--no-verify` re-commit
   of your still-staged paths lands instantly.
4. **Never rewrite shared `master` history** (rebase/amend/reset) while a
   concurrent committer is active — it races and can destroy their work or yours.
   Prefer leaving correct-but-mis-messaged code in place.
5. **Verify after:** `git log -- <my file>` — your code may be correct but bundled
   into someone else's commit.
6. **zsh does not word-split unquoted `$VAR`** — pass git pathspecs as explicit
   args, not via a variable.

## Related

- [worktrees don't isolate from concurrent agents](worktrees-dont-isolate-from-concurrent-agents.md) — the same contention from the shared-`.git` angle, with the ref-clobber recovery playbook.
- [worktree operating gotchas](worktree-operating-gotchas.md) — the gate/hook traps that compound this.
- [git mv completion staging traps](git-mv-completion-staging-traps.md) — "stage only your own paths" applied at the ExecPlan completion gate.
- [queue: act before consume](queue-act-before-consume-ordering.md) — the other "the green gate won't catch this" hazard; [RELIABILITY.md](../RELIABILITY.md) R19 generalizes it.
