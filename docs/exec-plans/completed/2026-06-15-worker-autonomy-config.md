---
status: completed
last_verified: 2026-06-15
owner: harness
type: exec-plan
tags: [worker, autonomy, security, director]
description: A preset that lets a worker run a ticket end-to-end with no human approver by configuring Codex's own sandbox and approval-reviewer for un-watched autonomy.
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
- Parent spec: [`docs/product-specs/2026-06-14-symphony-director-orchestration.md`](docs/product-specs/2026-06-14-symphony-director-orchestration.md)
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
- [x] (2026-06-15) M1 done. `director/worker/autonomy.py` (preset + `codex_command`);
      `run_ticket` threads `approval_policy`/`sandbox` into thread_start + run_turn; run.py
      + orchestrator.py `--autonomous` (default off = untrusted, watched unchanged) selects
      the preset + wraps the codex command with `-c` overrides. `tests/test_director_autonomy.py`
      (8). check.py GREEN (244). Commit e07f173.
- [x] (2026-06-15) M2 done. SECURITY.md **T11** (autonomous worker posture + accepted
      in-sandbox-network residual) + live-surface list. Parent symphony spec **D-38** (un-watched
      = Codex config, headless Director rejected) + roadmap. director-oversight skill: un-watched
      note (not an approval path). **Live wire-pin (real codex 0.139.0):** `director.run --autonomous`
      on a trivial stub → `status: completed`, worker AUTO-RAN `echo hi > hello.txt` in-sandbox,
      and **zero seam requests** (no approval escalated) — proves the preset is accepted, runs
      headlessly, and a worker self-governs with no Director round-trip.

## Surprises & discoveries
- The whole prior "autonomous-oversee" spec (reverted, 835cdbd) was mis-founded:
  it rebuilt Codex's `auto_review` as a headless Director. The real lever is one
  config preset. Codex owns per-action approval; the Director never did.
- Live-pin proved the thesis empirically: an autonomous worker completed a ticket
  with **zero** seam traffic — the in-sandbox command auto-approved. So the
  "throughput dies when the human leaves" problem was 100% the `untrusted` default,
  not a missing Director. Loosening one config knob is the entire fix.

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
review_level=targeted → review-security (Claude reviewer w/ SECURITY.md grounding; codex
companion still unreliable in-band). Verdict: **CHANGES REQUESTED**, P1.1.

- **P1.1 (review-security) — LIVE-CONFIRMED, doc-fixed + tracked.** `--autonomous` +
  `network_access=true` exfiltrates host secrets, bypassing T10. The reviewer flagged the
  read-above-workspace claim as impl-dependent; I **probed it live** (codex 0.139.0): a worker
  read a sentinel via `../../../` AND by absolute path into the repo from a workspace *outside*
  it → `workspace-write` reads are filesystem-wide. So `.env`/`LINEAR_API_KEY` is readable
  regardless of workspace location; full outbound then exfiltrates it. → SECURITY.md T11 rewritten
  to state this confirmed residual + that **workspace relocation does NOT mitigate** (reads fs-wide);
  effective fix = `network_proxy` allowlist / container / secret-scrub. tech-debt-tracker (Major).
  **Resolved: the human INFORMED-accepted full outbound (2026-06-15)** after seeing the live-probe
  evidence (re-asked with the confirmed exfil path on the table). Risk documented (T11) + mitigation
  tracked (Major). Per the reviewer's own bar ("document OR mitigate"), documenting an accepted
  residual satisfies P1.1.
- **P2.1 — fixed.** T11 generalized to "`.env` and process-env credentials," not just the Linear key.
- **P2.2 — fixed.** `run_ticket` comment clarifies `sandbox` is thread-level (set at thread/start,
  not run_turn) — the param is intentionally not forwarded to the turn.
- **Confirmed SATISFIED by the reviewer (no change needed):** default-off behavior-neutrality
  (watched path untrusted, byte-identical), no command-injection (hardcoded `-c` constants +
  operator `--codex`; no ticket/worker data in the command), T10 not weakened for the GraphQL tool
  path (host-side executor, outside the sandbox).

## Outcomes & retrospective
**달성.** un-watched 자율이 `--autonomous`(default off) opt-in 으로 출하. 워커가 Codex 자체
게이트로 self-govern(`on-request` + `auto_review` + `workspace-write` + full network) —
`director/worker/autonomy.py` preset 을 thread/start params + `-c` launch overrides 로 전달.
off 면 watched(`untrusted`) 경로 byte-identical. **실 codex 0.139.0 live-pin: 자율 워커가
in-sandbox 명령을 auto-run 하고 seam traffic 0 으로 turn 완료** — "사람 떠나면 throughput 0"
문제는 100% `untrusted` 기본값의 산물이었음(헤드리스 Director 불필요). SECURITY T11, 부모 D-38.
gate GREEN(244), 적대적 review-security 후 SATISFIED(P1.1 = informed-accepted residual).

**핵심 통찰.** ① Codex 가 per-action approval 을 자체 소유 → Director 는 승인자가 아님(헤드리스
Director 는 auto_review 의 열등한 재구현이었음). ② review-security 가 내가 놓친 P1 을 잡았고,
그 claim 을 **live-probe 로 검증**하니 더 심각: `workspace-write` 는 *쓰기*만 가둘 뿐 *읽기*는
filesystem-wide(워커가 repo 밖 workspace 에서 절대경로로 repo 파일을 읽음) → `.env` 키가 어디서든
읽혀 full network 로 exfil, **T10 우회**. workspace 재배치로는 못 막음(읽기가 fs-wide). 사람이
증거를 보고 full outbound 를 informed-accept.

**남은 것.** ① `network_proxy` 도메인 allowlist(또는 container/secret-scrub)로 exfil 닫기
(tracker, Major). ② `--autonomous` 를 orchestrator 기본값으로 승격(신뢰 후 one-liner). ③ board
reporting → PR-merge(Phase 4 후속). worker context map(D-36) 여전히 연기.
