---
status: stable
last_verified: 2026-06-21
owner: harness
type: knowledge
tags: [hooks, recursion-guard, headless, subprocess]
resource: plugin/scripts/harness_lib.py
description: The HARNESS_HEADLESS env guard prevents infinite SessionStart recursion when hooks spawn headless claude children.
---
# Recursion guard — HARNESS_HEADLESS

## Problem
Hook scripts (SessionStart, PreCompact, etc.) run inside a claude process. If a hook spawns
another claude child, that child would also fire SessionStart, creating unbounded recursion.

## Mechanism
- `harness_lib.is_headless()` — returns `True` if `HARNESS_HEADLESS == "1"` (exact string
  match via `os.environ.get(...) == "1"`; any other value, including `"true"` or `"yes"`, does
  NOT trip the guard).
- Every hook entry script calls `is_headless()` first and exits early if true.
- `harness_lib.headless_env()` — builds an env dict with `HARNESS_HEADLESS=1`; must be
  passed to every `subprocess` call that spawns a claude child.

## Invariant
Any harness-spawned claude child process **must** receive the env returned by `headless_env()`.
Omitting it means the child runs hooks, causing recursion or doubled side-effects.

## Source
`plugin/scripts/harness_lib.py` — `is_headless()` and `headless_env()`. The
surviving consumer is the `Stop`-hook `tidy_stop.py` (the feeder/imprint hooks
that originally drove this guard were retired with the memory loop).
