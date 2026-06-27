---
status: stable
last_verified: 2026-06-28
owner: harness
type: knowledge
tags: [codex, review, tooling, operating-gotcha]
description: /codex:review runs the built-in reviewer scoped to the working tree and rejects focus text; to review a committed branch against a base, use the companion's adversarial-review --base <ref> --scope branch, run from the worktree where the branch is HEAD.
---
# Codex review companion scoping

A field note promoted from session memory. The Codex companion
(`codex-companion.mjs`) has two review subcommands that behave very differently —
picking the wrong one wastes a run:

- **`review [focus text]`** → the **built-in** reviewer. It (a) **rejects any focus
  text** (errors and points you at `adversarial-review`), and (b) defaults its
  **target to the WORKING TREE** ("current changes" = staged + unstaged +
  untracked). On a clean worktree it reviews nothing of substance — it will flag
  stray untracked artifacts and never look at the branch diff. So `/codex:review`
  is the **wrong tool** for "review my branch against master".
- **`adversarial-review [--base <ref>] [--scope auto|working-tree|branch] [focus
  text]`** → accepts focus text **and** base/scope flags. To review committed
  branch history against a base:
  `adversarial-review --base master --scope branch "…instructions…"`.

## How to apply

- **Run it from the worktree where the branch is checked out** (HEAD must be the
  branch). If the primary checkout sits on `master`, `master...HEAD` is empty —
  `cd` into the branch's worktree first.
- Launch large reviews backgrounded; the full verbatim output lands in the task
  output file on completion.
- The adversarial reviewer is genuinely sharp (it has caught real change-detection
  and decode-error defects here), but **verify its claims against the code** —
  some are documented tradeoffs, and its evidence can be fabricated when its shell
  output degrades:
  [codex review verdict can confabulate](codex-review-verdict-can-confabulate.md).
