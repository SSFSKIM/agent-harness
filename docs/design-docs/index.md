---
status: stable
last_verified: 2026-06-28
owner: harness
---
# Design docs

Catalog of design documents. Add new pages here (lint D8 enforces).

- agent-harness.md — the installed harness: components, gate command
- core-beliefs.md — golden rules + agent-first operating principles
- symphony-parity-gap.md — how `director/` diverges from original Symphony (`docs/symphony-original/`): the two bets, what we match/exceed, the ranked gaps
- okf-comparison.md — Google's Open Knowledge Format (OKF v0.1) vs our docs system: the shared markdown+frontmatter substrate, what OKF advanced (type/resource/tags/spec/viz), what we advanced (enforced gate, staleness, epistemic taxonomy), ranked adoptions
- recursion-guard.md — the `HARNESS_HEADLESS` env guard that prevents infinite SessionStart recursion when a hook spawns a headless claude child (migrated from the retired `docs/memory/knowledge/`)

## Field notes (promoted from session memory)

Hard-won operating lessons — git/worktree/gate hazards, agent & review
methodology, and Director/runtime assumptions — promoted out of an agent's
private memory into the repo so they are shared and resolvable. Several are cited
by `[[slug]]` across ADRs, `RELIABILITY.md`, and product-specs; this is where
those slugs resolve.

- parallel-sessions-share-master-index.md — multiple sessions share one master tree+index; commit `--no-verify` after a manual gate, stage only your own paths
- queue-act-before-consume-ordering.md — do the durable side-effect BEFORE consuming a Director-queue item (consume-first loses it on a crash); generalized as `RELIABILITY.md` R19
- worktrees-dont-isolate-from-concurrent-agents.md — a worktree shares `.git` (refs+objects+`core.bare`) so it does NOT isolate from concurrent writers; clone for true isolation; the ref-clobber recovery playbook
- worktree-operating-gotchas.md — a fresh worktree only materializes tracked files (env-parity), the pre-commit hook gates the MAIN root, and a backgrounded commit hangs the hook
- git-mv-completion-staging-traps.md — at ExecPlan completion `git mv` stages only the OLD content and a multi-path `git add` aborts on a stale pathspec, silently dropping edits
- merge-numbered-list-collision-renumber.md — merging behind branches collides on append-only numbered-list docs (R/T-rules, tracker); union + renumber + grep the whole tree
- mid-session-agents-not-dispatchable.md — a plugin agent created mid-session is not dispatchable until next session; dogfood via general-purpose carrying the rubric
- codex-review-companion-scoping.md — `/codex:review` is working-tree scoped and rejects focus text; use `adversarial-review --base --scope branch` for a branch
- codex-review-verdict-can-confabulate.md — codex review verdicts can hallucinate evidence when shell output degrades; corroborate with a real-code reviewer
- own-context-for-synthesis-tasks.md — read both sides yourself for synthesis/comparison; delegate only breadth-sweep find/locate work
- no-headless-director-codex-owns-approval.md — no headless `claude -p`; the Director is the watched session, the worker self-approves per its approvalPolicy/sandbox
- worker-runtime-sync-is-manual-port.md — `worker-runtime/{harness,app-server}` is a one-way vendored subtree; hand-port the diff, then rebuild via `setup.sh`
- cc-codex-appserver-drop-in-verified.md — the Claude worker runtime: brokers all dynamicTools (zero Director code), `LINEAR_API_KEY` stays Director-side, classifier-only by decision
- base-rendered-from-seed-templates.md — `base/` is rendered from `harness-init/templates/` seeds (lint_base byte-equality); edit the seed, and reference-sweeps must include `templates/`
