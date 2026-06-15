"""Autonomous worker posture — let Codex self-govern instead of stalling for a
human approver (ExecPlan: worker-autonomy-config).

Un-watched autonomy is not a new subsystem: `director/orchestrator.py`'s
`run_until_drained` loop is already the driver, and the worker's only reason to
stall was the conservative `untrusted` approval policy. This preset flips that —
Codex auto-runs in-sandbox work and routes genuine escalations through its OWN
reviewer agent (`approvals_reviewer=auto_review`, fail-closed on critical risk),
so neither a human nor the Director is the per-action approver. See SECURITY.md
T11 for the risk basis (notably: with full network on, in-sandbox network is NOT
auto_review-gated — that exposure rests on sandbox FS containment + T10).

Two delivery channels — precedence matters (a thread/start param overrides a
process `-c` config for that thread):
  - approval_policy + sandbox        -> thread/start params (director/worker/app_server.py)
  - approvals_reviewer + network     -> `-c` overrides on the codex launch command

Key names verified against codex-cli 0.139.0 via `codex app-server --strict-config`.
"""
from __future__ import annotations

# thread/start params for an un-watched worker.
APPROVAL_POLICY = "on-request"   # auto-run in-sandbox; review escalations (not `never`)
SANDBOX = "workspace-write"      # FS-contained; .git/.codex forced read-only by Codex

# `-c` config overrides appended to the `codex app-server` launch command.
CONFIG_OVERRIDES = (
    "approvals_reviewer=auto_review",                # Codex's native fail-closed reviewer
    "sandbox_workspace_write.network_access=true",   # full outbound (human-accepted, T11)
)


def codex_command(base: str) -> str:
    """Append the autonomous `-c` overrides to a codex launch command string.

    `base` is the worker command (e.g. "codex app-server"); returns it with the
    overrides so the launched app-server self-governs. Only the real codex path is
    wrapped — the mock app-server takes no `-c`."""
    extra = " ".join(f"-c {ov}" for ov in CONFIG_OVERRIDES)
    return f"{base} {extra}"
