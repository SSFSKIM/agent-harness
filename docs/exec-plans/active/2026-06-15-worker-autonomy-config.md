---
status: active
last_verified: 2026-06-15
owner: harness
base_commit: 11360eb
review_level: targeted
---
# Worker autonomy config preset — un-watched via Codex's own gate

## Goal
A worker can run a ticket end-to-end with **no human approver present**, because
Codex self-governs via its own sandbox + approval-review, instead of stopping on
every command for a human. Observable done: with `--autonomous`, the worker is
launched/started with `approval_policy=on-request`, `sandbox=workspace-write`,
`approvals_reviewer=auto_review`, and `sandbox_workspace_write.network_access=true`
(full outbound) — so Codex auto-runs in-sandbox work and routes only genuine
escalations through its own reviewer; without the flag, behavior is **unchanged**
(today's conservative `untrusted`). The orchestrator's existing
`run_until_drained` loop is then a genuinely un-watched driver — no new loop, no
headless Director. SECURITY.md gains T11 (the autonomous worker posture).
`python3 plugin/scripts/check.py` GREEN.

## Context
- **Why this is the whole slice (not a subsystem):** the autonomous *behavior* is
  already built. `director/orchestrator.py:run_until_drained` is a full
  poll→dispatch→reconcile→re-poll loop; it was "watched" only because workers ran
  `untrusted` and kept stopping for a human. The guardrail (T10) bounds the one
  host-key write surface; the visibility slice gives a human/oversight the run
  picture; the seam's `timeout→decline` (`director/worker/approval.py`) is the
  backstop for the rare genuine question. So un-watched autonomy = let the worker
  self-govern. This config preset is that unlock.
- **Codex owns approval, not the Director.** `director/worker/app_server.py`
  `thread_start(approval_policy="untrusted", sandbox="workspace-write")` /
  `run_turn(approval_policy="untrusted")` — these are sent on every thread/turn but
  `run.py`/`orchestrator.py` never override them, so every worker runs the most
  conservative posture. Codex's `approvals_reviewer="auto_review"` is its native
  reviewer agent (checks exfiltration/credential-probing/destructive actions,
  **fails closed** on critical) for escalations under an interactive policy
  (`on-request`). That is the gate — a Director approving worker actions would
  reimplement it worse. (Grounding: the Codex "Agent approvals & security" doc.)
- **Verified against codex 0.139.0 (this session):** `codex app-server` takes
  `-c key=value` TOML overrides (dotted paths). `codex app-server --strict-config
  -c approvals_reviewer=auto_review -c approval_policy=on-request -c
  sandbox_mode=workspace-write -c sandbox_workspace_write.network_access=true`
  exits cleanly (all keys recognized); a bogus key errors `unknown configuration
  field`. The Elixir Symphony reference launches codex with `-c` overrides +
  `approval_policy` config (so this is the established pattern). SPEC §5 confirms
  `approval_policy`/`thread_sandbox` are pass-through, version-defined Codex values.
- **Delivery split (precedence matters):** `approval_policy`/`sandbox` are sent as
  thread/start params today (`app_server.py`) — a thread param overrides process
  config, so those must be set on the thread call (not just `-c`).
  `approvals_reviewer` and `sandbox_workspace_write.network_access` have no
  thread/start param → delivered as `-c` overrides on the `codex app-server`
  launch command.
- Parent spec: `docs/product-specs/2026-06-14-symphony-director-orchestration.md`
  (Phase 4 "loop/scheduled oversee"). Guardrail: `...worker-authority-guardrail.md`
  (T10, the deterministic complement to auto_review for the host-key Linear writes).
- **Risk basis (honest):** with `network_access=true`, in-sandbox network is **not**
  reviewed by auto_review (it reviews only *blocked/escalated* actions). Full
  outbound therefore rests on sandbox **filesystem** containment + T10 (Linear) +
  trust in the model, not on auto_review catching network exfil. Human-accepted
  for local dev / throwaway tickets (this session); recorded in T11.

## Approach (self-generated alternatives)
- A: **`--autonomous` preset that sets approval_policy/sandbox via thread params +
  appends the two `-c` overrides to the codex launch command** (default off =
  unchanged). — minimal, secure-by-default-off, both delivery channels handled,
  matches the Elixir reference's `-c` pattern.
- B: `approval_policy=never` + workspace-write (the Elixir reference's posture). —
  simplest/most autonomous, but `never` disables auto_review entirely (no review of
  escalations). The human chose to **trust auto_review**, which requires the
  interactive `on-request` policy. Rejected.
- C: ship a `~/.codex/config.toml` profile instead of `-c`/thread params. — global,
  out-of-repo, not per-run, leaks host config; the harness should set per-worker
  posture explicitly. Rejected.
- **Chosen: A** — on-request + auto_review keeps Codex's review on escalations
  (more conservative than the reference's `never`), full network per the human, and
  default-off keeps watched runs byte-identical.

## Assumptions & open questions (self-interrogation)
- Assumption: a thread/start `approvalPolicy` param overrides a `-c approval_policy`
  process override for that thread → set approval_policy/sandbox on the thread call,
  not via `-c`. If wrong (config wins), the `-c` path is harmless (same value).
  Verify in M2's live thread.
- Assumption: `auto_review` runs non-interactively in the app-server (no TTY prompt)
  under `on-request`. The doc says auto_review *replaces* surfacing-to-user for
  eligible approvals → headless-safe. Verify in M2 live thread; if it ever blocks,
  the seam timeout is the backstop.
- Open: should `--autonomous` be the orchestrator's default (it IS the un-watched
  tool) or opt-in? → **opt-in** (default off) this slice — secure-by-default, and
  watched single-worker `run.py` stays conservative. Flipping the orchestrator
  default is a one-line follow-up once trusted. (Decision log.)
- Open (escalate only taste): none — the posture (on-request + auto_review + full
  network) is human-decided. No fork remains.

## Milestones

- **M1 — autonomy preset + threaded config.** New `director/worker/autonomy.py`:
  preset constants (`APPROVAL_POLICY="on-request"`, `SANDBOX="workspace-write"`) +
  `codex_command(base: str) -> str` that appends `-c approvals_reviewer=auto_review
  -c sandbox_workspace_write.network_access=true`. `director/run.py:run_ticket`
  gains `approval_policy`/`sandbox` params, passed into BOTH `c.thread_start(...)`
  and `c.run_turn(...)`. `run.py` + `orchestrator.py` gain `--autonomous`: when set,
  approval_policy/sandbox = preset AND the codex command is wrapped by
  `autonomy.codex_command(...)`; when unset, untrusted/workspace-write + bare
  command (unchanged). At the end exists: `tests/test_director_autonomy.py` +
  seam/run wiring tests — `--autonomous` → thread_start/run_turn receive
  `on-request` and the launched command carries both `-c` overrides; default →
  `untrusted` and no overrides (behavior-neutral). run:
  `python3 -m pytest tests/test_director_autonomy.py -q` then
  `python3 plugin/scripts/check.py`. expect: PASS; off-run worker params identical
  to pre-change.

- **M2 — SECURITY T11 + live verification + docs + gate.** `docs/SECURITY.md` gains
  **T11 — Autonomous worker posture**: un-watched workers run `on-request +
  auto_review + workspace-write + full network`; safety rests on Codex's sandbox
  (FS containment; `.git`/`.codex` forced read-only) + auto_review (fail-closed on
  escalations) + T10 (host-key Linear writes); **caveat: in-sandbox network is not
  auto_review-gated** → full-outbound exfil risk accepted for local/throwaway use.
  Add T11 to the live-surface list. Record the corrected direction in the parent
  symphony spec Decision log (D-38: un-watched = Codex approval config, Director is
  not the approver, headless Director rejected). Note in the `director-oversight`
  skill that un-watched relies on Codex self-governing (the status surface is for
  monitoring, not request-approval). **Live wire-pin:** launch a real `codex
  app-server` with the autonomous `-c` overrides and drive one `--mock`-free thread
  (or, if auth/cost blocks a full turn, at minimum `--strict-config` acceptance +
  a thread/start handshake) to confirm the preset is accepted and runs headlessly.
  run: `python3 plugin/scripts/check.py` + the live check. expect: GREEN; T11
  present; live app-server accepts the preset and does not block on a TTY prompt.
  Completion gate: review-security (live exec surface — autonomy posture).

## Progress log
- [x] (2026-06-15) plan created; base_commit 11360eb; review_level targeted
      (review-security). Verified codex 0.139.0 `-c` key names via `--strict-config`
      (4 keys accepted, bogus key rejected) before drafting.
- [ ] M1 — autonomy preset + threaded config
- [ ] M2 — SECURITY T11 + live verification + docs + gate

## Surprises & discoveries
- The whole prior "autonomous-oversee" spec (reverted, 835cdbd) was mis-founded:
  it rebuilt Codex's `auto_review` as a headless Director. The real lever is one
  config preset. Codex owns per-action approval; the Director never did.

## Decision log
- 2026-06-15: un-watched autonomy = tune Codex's approval config (on-request +
  auto_review + workspace-write + full network), NOT a headless Director or a
  Director-as-approver. Codex's auto_review is the native, better-grounded gate.
- 2026-06-15: `--autonomous` opt-in, default off (secure-by-default; watched runs
  unchanged). Flipping the orchestrator default is a later one-liner.
- 2026-06-15: approval_policy/sandbox via thread/start params (precedence over
  `-c`); approvals_reviewer/network_access via `-c` launch overrides (no thread
  param). Verified key names against codex 0.139.0.
- 2026-06-15: full outbound network accepted (human); risk basis = sandbox FS
  containment + T10 + monitoring, explicitly NOT auto_review (which doesn't gate
  in-sandbox network). Recorded in T11.

## Feedback (from completion gate)

## Outcomes & retrospective
