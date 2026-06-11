---
status: stable
last_verified: 2026-06-12
owner: imprint-job
---
# Recursion guard — HARNESS_HEADLESS

## Problem
Hook scripts (SessionStart, PreCompact, etc.) run inside a claude process. If a hook spawns
another claude child, that child would also fire SessionStart, creating unbounded recursion.

## Mechanism
- `harness_lib.is_headless()` — returns `True` if `HARNESS_HEADLESS` env var is set.
- Every hook entry script calls `is_headless()` first and exits early if true.
- `harness_lib.headless_env()` — builds an env dict with `HARNESS_HEADLESS=1`; must be
  passed to every `subprocess` call that spawns a claude child.

## Invariant
Any harness-spawned claude child process **must** receive the env returned by `headless_env()`.
Omitting it means the child runs hooks, causing recursion or doubled side-effects.

## Source
`plugin/scripts/harness_lib.py` — `is_headless()` and `headless_env()`.
Confirmed in session `archive/sessions/2026-06-12-e2e-test-session-end.md`.
