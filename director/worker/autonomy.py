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

Per-action self-governance AND full network are now **shared by both modes**. The
two modes therefore differ on exactly ONE axis:
  - **turn-end decider** — watched = inline Director (queue); un-watched
    (`--autonomous`) = code decider (director.decider). Not this module's concern.

Network is the credential-exfil vector (SECURITY.md T11) and is ON for both modes by
human decision (2026-06-15): the exfil residual is **deferred to a one-shot mitigation**
(egress via a `network_proxy` allowlist, or removing secrets from disk behind a secret
manager), addressed holistically rather than per-mode. Until then, both postures are
safe only where reachable credentials are throwaway.

Two delivery channels — precedence matters (a thread/start param overrides a
process `-c` config for that thread):
  - approval_policy + sandbox        -> thread/start params (director/worker/app_server.py)
  - approvals_reviewer + network     -> `-c` overrides on the codex launch command

Key names verified against codex-cli 0.139.0 via `codex app-server --strict-config`.
"""
from __future__ import annotations

from director import config

# thread/start params — the DEFAULT per-action posture. The VALUES are owned by
# `config.DEFAULTS["worker"]` (single source of truth, declarative-config slice);
# these names stay so direct callers/tests keep working, and a host may override
# them in `.harness.json` `director.worker`. `on-request` = auto-run in-sandbox,
# review escalations (not `never`). `workspace-write` = FS writes contained to the
# workspace. NOTE: `.git` IS writable here — live-probed (codex-cli 0.139.0): an
# in-sandbox worker's `git commit` lands. The older ".git read-only under
# workspace-write" assumption does NOT hold for this posture (threat model).
APPROVAL_POLICY = config.DEFAULTS["worker"]["approval_policy"]   # "on-request"
SANDBOX = config.DEFAULTS["worker"]["sandbox"]                   # "workspace-write"

# `-c` config override STRINGS for the `codex app-server` launch command (mechanism,
# not a knob — whether each is applied is the config's `auto_review`/`network` bool).
AUTO_REVIEW = "approvals_reviewer=auto_review"            # Codex's fail-closed reviewer
NETWORK = "sandbox_workspace_write.network_access=true"   # full outbound (exfil deferred, T11)


def codex_command(base: str, *, auto_review: bool = True, network: bool = True) -> str:
    """Append the self-governance `-c` overrides to a codex launch command string.

    `auto_review` (the per-action baseline) and `network` (full outbound) are applied
    per the resolved worker posture; the defaults (both on) preserve the historical
    behavior, and a host that sets `director.worker.network=false`/`auto_review=false`
    in `.harness.json` *tightens* the worker (the fail-safe direction — the override is
    omitted, not negated). The network exfil residual is deferred to a one-shot
    mitigation (T11). Only the real codex path is wrapped — the mock takes no `-c`."""
    overrides = []
    if auto_review:
        overrides.append(AUTO_REVIEW)
    if network:
        overrides.append(NETWORK)
    extra = " ".join(f"-c {ov}" for ov in overrides)
    return f"{base} {extra}".rstrip()
