"""Worker posture — let Codex self-govern per-action instead of stalling for a
human approver (ExecPlan: worker-autonomy-config; refined for watched parity).

**Per-action self-governance is the SHARED baseline for BOTH watched and
un-watched runs.** The worker's only reason to stall was the conservative
`untrusted` policy that escalated every routine command to the Director — pointless
toil. Both modes now run `on-request` + `approvals_reviewer=auto_review`: Codex
auto-runs in-sandbox work and routes genuine escalations through its OWN reviewer
agent (fail-closed on critical risk), so neither a human nor the Director is the
per-action approver in either mode. The Director's job is the TURN END (taste), not
rubber-stamping `cat`/`ls`.

The two modes therefore differ on exactly TWO axes, both folded into `--autonomous`:
  1. **network** — un-watched gets full outbound (`network_access=true`); watched does
     NOT. Network is the exfil vector (SECURITY.md T11), so watched — which keeps a
     human in the loop at turn ends — stays network-off and carries no exfil exposure.
  2. **turn-end decider** — watched = inline Director (queue); un-watched = code
     decider (director.decider). Not this module's concern.

Two delivery channels — precedence matters (a thread/start param overrides a
process `-c` config for that thread):
  - approval_policy + sandbox        -> thread/start params (director/worker/app_server.py)
  - approvals_reviewer + network     -> `-c` overrides on the codex launch command

Key names verified against codex-cli 0.139.0 via `codex app-server --strict-config`.
"""
from __future__ import annotations

# thread/start params — the shared per-action posture for BOTH modes.
APPROVAL_POLICY = "on-request"   # auto-run in-sandbox; review escalations (not `never`)
SANDBOX = "workspace-write"      # FS-contained; .git/.codex forced read-only by Codex

# `-c` config overrides on the `codex app-server` launch command.
AUTO_REVIEW = "approvals_reviewer=auto_review"            # shared: Codex's fail-closed reviewer
NETWORK = "sandbox_workspace_write.network_access=true"   # un-watched ONLY (exfil vector, T11)


def codex_command(base: str, *, network: bool = False) -> str:
    """Append the self-governance `-c` overrides to a codex launch command string.

    `auto_review` is ALWAYS added — it is the shared per-action baseline that keeps the
    Director out of routine approvals in both watched and un-watched runs. `network`
    (full outbound) is added ONLY for un-watched (`--autonomous`): it is the exfil
    vector (T11), so a watched run never gets it. Only the real codex path is wrapped —
    the mock app-server takes no `-c`."""
    overrides = [AUTO_REVIEW]
    if network:
        overrides.append(NETWORK)
    extra = " ".join(f"-c {ov}" for ov in overrides)
    return f"{base} {extra}"
