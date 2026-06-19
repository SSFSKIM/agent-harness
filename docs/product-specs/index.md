---
status: stable
last_verified: 2026-06-14
owner: harness
---
# Product specs

- agent-harness v1 design spec: `../superpowers/specs/2026-06-12-agent-harness-v1-design.md`
  — two layers (OpenAI harness-engineering reproduction + memory loop),
  human touchpoints, build phases, success criteria.
- [Product Design 단계 + entry decision](2026-06-14-product-design-phase.md)
  — ExecPlan 앞단의 spec 단계 + 작업 시작 전 세 갈래 entry decision(throwaway /
  Product Design / ExecPlan). methodology spec.
- [Symphony 티켓 오케스트레이션 + 중앙 Director](2026-06-14-symphony-director-orchestration.md)
  — 티켓 DAG 를 조직 구조로 삼는 multi-agent 개발 능력. Director=Claude Code /
  worker=codex app-server, Symphony 사양 Python 재구현. Phase 1(approval→Director→
  resume seam) 상세 + Phase 2–5 로드맵. (parent)
- [오케스트레이터 — poll→dispatch→reconcile 루프](2026-06-14-orchestrator-dispatch-loop.md)
  — 위 로드맵 Phase 2 후반. ready 티켓을 poll 해 N개 워커에 동시 dispatch, 결과를
  board 로 reconcile 하는 thin·watched 첫 컷. 큐 동시성 안전화 포함.
- [DAG-aware 연속 오케스트레이션](2026-06-14-dag-aware-orchestration.md)
  — Phase 3a. `blocked_by` 를 존중하는 연속 re-poll(wave) 루프: ready 그리고 blocker 가
  전부 done 인 티켓만 dispatch, 완료가 의존을 unblock, 워커-생성 티켓을 집음. board-as-truth,
  cycle/stuck 검출, bounded·watched. (3b dev-stage taxonomy 는 별도.)
- [Dev-stage taxonomy](2026-06-14-dev-stage-taxonomy.md)
  — Phase 3b. 티켓 type(planning/research/design/spec/impl)을 하네스 doc 파이프라인 단계에
  매핑: type→methodology+산출 doc+typed 자식. type=Linear 라벨, prompt 라우팅(순수 함수),
  worker-driven 분해, 3a DAG 가 정렬. 하네스가 자신을 돌리는 typed 티켓 DAG(RV1).
- [Worker authority guardrail](2026-06-14-worker-authority-guardrail.md)
  — Phase 4 첫 슬라이스 + 하드 선행조건. 워커의 `linear_graphql` 를 mutation root-field
  allowlist(default-deny)로 묶는다: reads 무제한, allowlisted forward-only mutation 만 통과,
  파괴적/미지 mutation 은 Linear 로 나가기 전 로컬 거부. 서버 parser 와 정렬된 최소 GraphQL
  분류기. un-watched dispatch 전에 사람 키로 보드를 파괴하지 못하게(tracker line 49, T10).
- [Director 오케스트레이션 가시성 → 인라인 taste-vs-handle escalation](2026-06-15-director-orchestration-visibility.md)
  — Phase 4 둘째 슬라이스. escalation judge = 별도 헤드리스 프로세스가 아니라 인라인 메인
  세션(D-5). 오케스트레이터가 in-memory 로만 갖던 상태(in-flight·attempt·wave·stuck)를 atomic
  스냅샷으로 영속화하고, Director 가 read-API + 스킬로 끌어 쓴다. 요청↔오케스트레이션
  join(`context_for`)이 bare 큐 요청을 상황 그림으로 감싸 인라인 판단을 떠받친다 — 정책은 그 위
  얇은 guideline. guardrail 의 escalate-to-Director seam + 부모의 taste 정책 Open Question 해소.
- [Multi-turn 티켓 실행 — Director-driven continuation + worker-proposed status](2026-06-15-multi-turn-ticket-execution.md)
  — Phase 4. orchestrator 의 "한 턴 → `completed→Done` 코드 매핑"이 틀렸음을 교정: 티켓 하나는
  여러 턴에 걸치고, 턴 종료 ≠ 티켓 완료. 워커가 structured outcome(continuing/done/blocked+children/
  needs_human) 제안 → Director 가 집행·검수(watched) 또는 워커 신뢰·auto-continue(un-watched).
  코드는 done-ness 판단 0. multi-turn continuation feasibility live 검증(2턴/1thread 맥락 유지).
  Phase 2 reconcile 재설계, reporting/PR-merge 보다 선행.
- [워커 self-QA + 직렬화된 PR-merge](2026-06-16-worker-qa-and-serialized-pr-merge.md)
  — Phase 4 꼬리. 워커가 self-QA(spec-compliance + code-quality + task-specific 테스트)를 *절차*로
  끝내고 PR+자기명세를 만든다(하드 게이트 아님 — minimal blocking gates; done 은 LLM 판단 유지).
  done+QA 된 PR 은 *직렬화된 merge queue* 에 들어가 단일 PR-merger 가 하나씩 rebase→얇은 통합 체크
  →squash-merge(`land`); 충돌/위험/taste 만 Director 경유(단일 인간 surface)로 escalate. 동시
  머지 thrash 를 단일 소비자로 제거. merger 는 `drive`+decider 재사용(새 turn 머신 0). multi-turn
  의 미뤄둔 "done-is-really-done" + visibility 의 "terminal sanity-check" 을 닫음. Playwright-in-
  sandbox 실행 가능성은 ExecPlan PoC.
- [Lights-out Director — Core Principle 레이어 · park 계약 · board comment · issueUpdate ceiling](2026-06-17-lights-out-director.md)
  — [ADR 0002](../memory/adr/0002-graduated-autonomy.md) slice 2, [ADR 0003](../memory/adr/0003-lights-out-director.md)
  reframe 위에 빌드. mode bit 을 (Director 有無)×(human 有無) 두 축으로 분리 — "autonomous"
  가 *human 부재*(Director-only, daemon 이 큐 응답)로 재바인딩되고 pure-code `autonomous_decide`
  는 no-agent(`--mock`/CI) niche 로 후퇴(새 orchestrator flag 0 — 누가 응답하느냐로 실현).
  신규 `docs/PRINCIPLES.md`(인간의 decision-taste 외부화 — Director 가 fork 에서 인간 판단을
  *시뮬레이션*; Claude 가 관찰된 패턴으로 seed) + `DIRECTOR.md` lights-out 절차(hard-blocker→park /
  mechanical→decide+log / taste→PRINCIPLES 참조→infer-or-park; 판별자 = taste-vs-mechanical, hard
  floor = 가드레일 아키텍처) + §2 outward-facing 조항 수정. park = 기존 `escalate` 경로 재사용
  (구분 가능한 comment + In Progress 유지 + async 인간 surface), audit = disposition 에 principle
  citation. 2b: 워커가 **단일** canonical 진행 comment 유지(`WORKER_PROTOCOL` 확장). 2c:
  `issueUpdate` 를 worker allowlist 에서 제거 + linear SKILL.md state-transition 지시 제거(직렬화
  orchestrator state-write 단일화). Daemonized Claude Code 런타임은 별도 트랙(범위 밖);
  no-headless 메모리 NOT superseded.
- [Director board reporting (run-level pull)](2026-06-16-director-board-reporting.md)
  — Phase 4 로드맵의 "board 리포팅". 목적 = 사람 attention pull(내구성 기록 아님): unattended
  watched 런이 종료 국면(drained/stuck/max/poll_failed)에 닿으면 `director.watch` 가 status
  스냅샷을 tail 해 `runReport` 이벤트를 emit → event-woken Director 가 `director.status` 로
  digest 를 작성해 `PushNotification` 으로 사람을 끌어들인다. terminal-only emit(중간 조기 pull
  defer), watched 전용, 코드는 리포트-가치 판단 0(DIRECTOR.md 절차). watch + doc 만 — orchestrator
  변경 0.
- [Worker telemetry capture (Symphony-grade) into status.json](2026-06-16-worker-telemetry-capture.md)
  — Phase 5 observability 트랙, **renderer 의 선행**. renderer richness 는 producer state 에
  묶이므로 데이터를 먼저 풍부하게: Symphony 가 추적하는 운영 telemetry(per-ticket 토큰·
  turn_count·session_id, run-level codex_totals·seconds_running·rate_limits; SPEC §4.1.6/
  §4.1.8/§13.5)를 **턴/디스패치 경계**에서 포착해 `status.json` 에 영속. app_server 가 codex
  스트림에서 usage 추출(tolerant, 없으면 None) → drive 가 per-ticket 누적(절대총량, anti-
  double-count) → orchestrator 가 terminal 에서 기록 + run aggregate. status.py 변경은 additive
  (lock-free 단일 writer 유지; 라이브 in-flight accrual = Layer 2 defer). §13.5 회계 규칙 채택.
- [Director observability dashboard (라이브 read-only 웹 뷰)](2026-06-16-director-observability-dashboard.md)
  — Phase 5(optional)의 observability surface. visibility spec 이 미뤄둔 "라이브 dashboard /
  web observability"(line 208)를 회수: 기존 `director.status` 스냅샷 + `queue.read_pending`
  위에 stdlib `http.server` 로 127.0.0.1 read-only 웹 뷰를 얹는다. `GET /api/v1/state` =
  순수 `build_view(status_dir,queue_dir)` JSON(in-flight/stuck/recent/pending + counts),
  인라인 vanilla-JS 페이지가 ~1s 폴로 재렌더. read-only(act 는 Director 경유), 폴링(SSE 아님),
  current-run only, stdlib-only. 기존 모듈 변경 0 — 신규 `director/dashboard.py` + 테스트 +
  DIRECTOR.md 절. (공유 tracker / GitHub Issues 어댑터는 범위 밖.) **재배치(2026-06-16): worker
  telemetry capture 가 선행 — renderer 는 그 풍부해진 데이터의 consumer.**
- [Active-run reconciliation + 워커 취소 (daemon stage 1)](2026-06-16-active-run-reconciliation.md)
  — Symphony 정합 daemon 묶음 1단계(gap #1, SPEC §8.5/§16.3/§14.4). 워커가 도는 동안
  orchestrator 가 in-flight 티켓 상태를 주기적으로 되읽어(신규 board `fetch_issue_states_by_ids`),
  사람이 `In Progress` 밖으로 옮긴 티켓의 워커를 **취소**(cooperative `cancel_event` — app-server
  read loop mid-turn + turn 사이; `TurnCancelled`; retry/board-write 없음). 핵심: `_dispatch_wave`
  의 `futures` dict 가 이미 running-map → `wait(timeout=)` + monotonic cadence 로 wave-barrier 가
  완료 사이에도 reconcile(메인 스레드 → R13 단일-writer 보존). stall-reap 은 `read_timeout_s` 가
  실질 충족 → 연기(D-61). 연속 daemon 루프(#2)·backoff(#3)는 별도 후속. `reconcile_interval_s`
  config knob.
- [Director 선언적 설정 계약 (`.harness.json` `director` 블록)](2026-06-16-director-declarative-config.md)
  — Symphony 정합 트랙(SPEC §5–6/§6.2, `WORKFLOW.md` 대응). 코드+CLI 플래그에 흩어진
  오케스트레이션 정책(team·states·concurrency·posture·paths·merger knob)을 `worker_policy`
  와 **같은 `.harness.json`** 의 `director` 블록(stdlib json, YAML 아님)으로 외부화 →
  "설정 하나 떨구면 어느 repo 에서나 도는" 하네스. methodology(템플릿/계약)는 코드 유지(D-56);
  precedence CLI>config>default(D-58); `$VAR` indirection; load-once(daemon reload 아님 — D-55,
  episodic 모델); 부재 fail-open / malformed fail-loud(D-57, 첫 워커 spawn 전). 신규
  `director/config.py`(pure, explicit `root=`) + `python3 -m director.config` effective-config
  surface. gap analysis 가 고른 다음 수.
- [연속 daemon 루프 (daemon stage 2)](2026-06-17-continuous-daemon-loop.md)
  — Symphony 정합 daemon 묶음 2단계(gap #2 the identity gap, SPEC §6.2/§8.1). orchestrator
  의 두 barrier(`_dispatch_wave` wave-barrier + `run_until_drained` pass-barrier→drained-exit)
  를 **하나의 연속 tick 루프**로 접어, board 가 비어도 종료 않고 영원히 폴링하는 세 번째 모드
  `run_forever`(daemon, `--daemon`)를 추가. 매 tick: free-slot bounded top-up(claim ≤ 빈 슬롯,
  flood 아님) → wait(완료/`poll_interval_s`) → reap → stage 1 `_reconcile_in_flight`(무변경) →
  idle/heartbeat. stuck 은 종료 아닌 status 신호; graceful shutdown(1차 drain·2차 cancel-all,
  stage 1 cancel_event 재사용); poll/claim 실패 fail-soft. backoff(#3)는 `_idle_wait_s` seam 만.
  배치 경로(`--once`/기본 drain)·stage 1 조각 전부 보존(설계 dividend). `poll_interval_s` knob.
- [Daemon exponential backoff (daemon stage 3 — 마지막)](2026-06-17-daemon-exponential-backoff.md)
  — Symphony 정합 daemon 묶음 3단계(gap #3 retry model 완성, SPEC §8.4). daemon(`run_forever`)의
  retry·idle·claim 을 단일 `_backoff_s(n,base,cap)=min(base·2^(n-1),cap)` 로 지수 backoff:
  (A) 실패 워커는 즉시가 아니라 backoff 뒤 재-dispatch — 메인 블록 없이 pending-retry holding map
  + tick due-검사(slot 회계 `free=concurrency−futures−pending_retry`); (B) idle 폴은
  `poll_interval·2^streak`(cap)로 키우고 일 등장 시 리셋 — poll-failure(C)는 idle 경로로 흡수;
  (D) claim 실패는 영구 배제(D-73) 대신 per-tid backoff 재-admission(bounded). batch 경로는 즉시
  retry **불변**(reap `on_retry=` 훅의 기본; regression net). knob `backoff_base_s`(10s)/
  `backoff_cap_s`(300s). Symphony per-completion 재-check 은 NON-GOAL(active-run reconciliation 이
  충족). 이 슬라이스로 **daemon 트랙(gap #1/#2/#3) CLOSED**.
- [Worker operating-protocol depth (graduated-autonomy slice 1)](2026-06-17-worker-operating-protocol.md)
  — [ADR 0002](../memory/adr/0002-graduated-autonomy.md) 의 선행 슬라이스, Symphony 정합 gap #5.
  원본 [`WORKFLOW.md`](../symphony-original/WORKFLOW.md) 의 stage-agnostic 운영 규율을 **수확**
  (파일 포팅 아님): 공유 `WORKER_PROTOCOL` preamble(단일 살아있는 source-of-truth + no-scope-creep→
  typed child)을 `TERMINAL_CONTRACT` 와 같은 first-turn seam(`drive`)에 주입 → 모든 dispatch 경로;
  impl 템플릿 enrichment(reproduction-first · acceptance 미러링 · temp-proof revert · **PR feedback
  sweep** pre-handoff+on-arrival). 척추 = `WORKFLOW.md` 줄별 keep/adapt/reject triage(보드-쓰기 소유·
  직렬 merger·`report_outcome`·5 typed stage 에 대고). 워커-프롬프트 only — `decider.py`(slice 2)·
  보드 소유·merger 불변. graduated-autonomy 의 *worker-autonomy enabler*.
- [Director operator console — actionable dashboard + park notifications](2026-06-18-director-operator-console.md)
  — the human-reachability complement to lights-out ([ADR 0003](../memory/adr/0003-lights-out-director.md)).
  Turns the read-only dashboard ([observability-dashboard](2026-06-16-director-observability-dashboard.md)
  D-2 deferred slice) into an **actionable** surface + adds the missing "reach an
  absent human" channel. `POST /api/v1/answer` resolves a pending queue request via
  the canonical `director_min` writers (`answer`/`answer_turn`/`answer_merge_review`/
  `requeue_merge`) per kind (turnReview/commandApproval/fileChange/userInput/
  elicitation/mergeReview; `mergeRequest` read-only) → the blocked worker's
  `wait_for_answer` unblocks. Write-surface fencing = `127.0.0.1` + per-server CSRF
  token + Origin/Host check (the deferred "write fencing" concern); act-durably +
  refuse-double-answer (R6, [[queue-act-before-consume-ordering]]). New
  `director/notify.py` tails the queue (reusing `watch.new_pending` dedup) and POSTs
  a **webhook** ($DIRECTOR_WEBHOOK_URL/`--webhook`, secret kept in `.env`) once per
  new human-bound pending request — the lights-out "you're needed" ping. Additive:
  `dashboard.py` + `notify.py` + tests + DIRECTOR.md; orchestrator/queue/status
  unchanged. Non-goals: orchestrator poll-trigger, non-webhook channels, SSE,
  pause/cancel (active-run reconciliation already owns operator-stop).
- [Symphony adapter & workspace parity](2026-06-18-symphony-adapter-workspace-parity.md)
  — the leftover "lesser/adapter-level gaps" from
  [symphony-parity-gap](../design-docs/symphony-parity-gap.md) (lines 130–135), after the
  daemon/config/protocol tracks closed. **R1** Linear candidate-fetch pagination
  (`_READY_ISSUES`/`list_ready_issues` `first`/`after`+`pageInfo`, page 50, order-preserving,
  `linear_missing_end_cursor` raise) + new paginated `fetch_issues_by_states` op (§11.1 #2,
  empty-guard). **R2** workspace safety in `run.py` (§9.5): sanitize key to `[A-Za-z0-9._-]`,
  root-containment (resolve+`is_relative_to`, raise), one shared `workspace_path` helper
  (dispatch/merge-enqueue/cleanup agree — ARCH invariant 8), pre-launch cwd assert. **R3**
  daemon startup recovery in `run_forever` (§8.6/§14.3/§8.5B): startup terminal-workspace
  cleanup *excluding pending-merge paths* (the serialized merger still needs a `done` PR
  branch) + orphaned-`started` re-attach (→`ready` so the first poll re-dispatches) +
  mid-flight-cancelled-to-terminal reconcile cleanup (normal `done`/`blocked` never clean,
  §9.1). Build = slices 1–3. **R4 workspace lifecycle hooks DEFERRED** (the repo-population
  bridge — only load-bearing once workers run on a real repo). Additive; daemon/reconcile
  core + decider/queue/merger unchanged.
- [Workspace lifecycle hooks (R4 — repo-population bridge)](2026-06-19-workspace-lifecycle-hooks.md)
  — the deferred R4 of the parity track, promoted to built after a spike proved a
  `workspace-write`-sandbox codex worker (with `GH_TOKEN` in `worker_env` + git's gh
  credential helper) can clone→edit→push→open a real PR in one turn. Adds Symphony §9.4
  workspace lifecycle hooks: `.harness.json` `director.workspace.hooks`
  {`after_create`/`before_run`/`after_run`/`before_remove`} + `hook_timeout_s`, each run
  `sh -lc` with cwd=workspace, **Director-side** (trusted host config — keychain reach for
  private clone), with Symphony's fatal/ignored failure semantics. Repo population is the
  host's `after_create` clone, not harness logic (§9.3 VCS-agnostic). Live-validated on a
  throwaway GitHub repo: ticket → worker PR → merger land. New SECURITY T15 (hook privilege).
  Additive — config.py + run.py + orchestrator.py cleanup sites; parity slices 1–3 unchanged.
- [Deferred observability polish](2026-06-18-observability-polish.md)
  — the deferred non-goals / Layer-2 follow-ups the read-dashboard
  ([observability-dashboard](2026-06-16-director-observability-dashboard.md)) and telemetry
  slice ([worker-telemetry-capture](2026-06-16-worker-telemetry-capture.md)) named, now the
  surface is actionable ([operator-console](2026-06-18-director-operator-console.md)).
  **v1 (R1–R6):** *Layer-2 in-flight token accrual* — `codex_totals` becomes a LIVE sum
  (ended + in-flight) at `snapshot()` mirroring `seconds_running`; per-event usage marshals
  worker-pool→main-thread via a `queue.Queue` drained per tick (R13/R16), no double-count at
  `terminal()`; `app_server` unchanged (reuse `on_event`+`extract_usage`). *SSE* —
  `GET /api/v1/stream` server-pushes `build_view` on change with a poll fallback (fail-soft,
  R14). *Rate-limit representation* — tolerant `fmtRateLimits` (no raw `JSON.stringify`).
  **Phase B (R7–R8):** *cross-run history* — new append-only `director/history.py`
  (`append_run`/`read_history`, written at run completion) + `GET /api/v1/history` + a panel.
  **Deferred:** multi-run aggregate view (no producer fan-out scenario yet). Additive;
  `/api/v1/state` stays a superset.
- [Merge-gated DAG eligibility](2026-06-19-merge-gated-eligibility.md)
  — a child's `blocked_by` edge clears only when the parent's PR has actually LANDED on main,
  not merely when the worker reported `done` (today `reconcile` sets the board `done` while the
  PR is still queued in the serialized merger → a child can clone a stale `main`). Direction A:
  a PR-bearing `done` parks the board in an optional `merging` state; the ORCHESTRATOR finalizes
  `merging`→`done` once it observes the merge landed (`fetch_issues_by_states` + the
  `merge|<tid>|aN` answer) — so the existing `done_types` eligibility gate, orphan-recovery, and
  active-run reconciliation stay pure board reads. No-PR tickets reach `done` immediately;
  abandon keeps the parent `merging` (children stay blocked, human owns the escape). Opt-in via
  configuring `merging`; merger stays board-free; R19 act-before-consume preserved.
- [Merge-preservation hardening](2026-06-19-merge-preservation-hardening.md)
  — the merger gains a preservation-first land precondition so a squash-merge cannot silently
  drop/overwrite either side's work. gap #5 worker-protocol track ([ADR 0002](../memory/adr/0002-graduated-autonomy.md)/[0003](../memory/adr/0003-lights-out-director.md)):
  the PR-feedback-sweep shipped as prose (slice-1 `_IMPL_TEMPLATE` R7) but nothing *verifies* it,
  and the merger's only GREEN is the local integration gate. Spine (D1): code owns the irreversible
  merge — the land worker *prepares* (rebase/fix-CI/resolve-threads), then merger CODE runs a
  preservation tripwire (R1: merge-delta vs PR-delta; dropped hunk → escalate, heuristic→judgment)
  + a hygiene gate (R3: CI green + unresolved-threads==0, tri-state green→land/failing→escalate/
  pending→defer; threads-knob configurable) and only then squash-merges. Sweep result becomes
  structured `report_outcome` evidence the merger audits (R4, claim-vs-verified misfire log).
  Additive; merger stays board-free; `check.py`-on-rebased-main stays the independent second net.
