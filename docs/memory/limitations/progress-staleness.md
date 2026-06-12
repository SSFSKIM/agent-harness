---
status: stable
last_verified: 2026-06-12
owner: harness
---
# Progress staleness when work bypasses hooked sessions

Work performed by external orchestrators (no SessionEnd/PreCompact hooks
firing) leaves `progress/current.md` stale unless the committing agent
updates it explicitly. Observed 2026-06-12: the completion-gate commit
updated the ExecPlan but not progress/current.md, so a fresh session's
feeder pack reported a one-commit-stale "next step" (§7 criterion 2 caveat).

Rule of thumb: any commit that changes project state must either run inside
a hooked session (imprint covers it) or update progress/current.md in the
same commit.
