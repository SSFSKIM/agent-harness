---
status: stable
last_verified: 2026-06-28
owner: harness
type: knowledge
tags: [git, execplan, commit-gate, operating-gotcha]
description: At the ExecPlan completion gate, `git mv` of a worktree-edited plan stages only the OLD content (bare rename), and a multi-path `git add` that lists the vanished old path aborts the whole staging — so the completion commit silently drops your edits.
---
# git mv completion staging traps

A field note promoted from session memory. Two compounding git traps fire at the
recurring ExecPlan completion step (`git mv docs/exec-plans/active/<plan>
completed/`). Both fail *silently-ish*: the commit "succeeds", the push goes
through, and the repo looks done while the actual content edits are still in the
worktree. They recurred several times **despite** being noted, because the trap
fires at the *moment of staging* — so the rule must be mechanical, not "remember
harder".

## Trap 1 — `git mv` of a worktree-modified file stages only the OLD content

If you Edit the plan (status→completed, Feedback, Outcomes) and then `git mv`
*without* a `git add` in between, the index holds the rename of the **pre-edit**
content; your edits sit as an unstaged worktree-`M` on the new path. `git status`
shows `RM old -> new`. Committing yields `rename (100%)` / `0 insertions` — a
**bare rename that drops your edits**.

## Trap 2 — a multi-path `git add` aborts entirely on one stale pathspec

`git add` treats a nonexistent pathspec as a hard error (exit 128) and aborts the
**whole** invocation. Listing the now-vanished `active/<plan>` path (or any file
removed earlier with `git rm`) alongside valid paths means **none** get staged —
your valid edits to the tracker, logs, etc. stay uncommitted too. A `2>/dev/null`
hides the error so the abort looks like success.

## The mechanical rule

> **After `git rm` or `git mv`, that path is ALREADY staged. NEVER list it again
> in a later `git add`. Stage ONLY paths that still exist on disk.**

At completion: stage the moved file's content at its **new** path
(`git add docs/exec-plans/completed/<plan>`), never the old path; either `git add`
your plan edits before `git mv`, or just stage the `completed/` path after.

**Always verify before trusting the commit:** `git show --stat <sha>` (file count
matches expectation) and a rename line that is **not** `(100%)` when you expected
content changes, then `git status` clean. Related:
[parallel sessions share one master index](parallel-sessions-share-master-index.md)
(stage only your own paths).
