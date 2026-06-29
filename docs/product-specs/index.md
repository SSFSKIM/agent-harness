---
status: stable
last_verified: 2026-06-21
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
  — [ADR 0002](../adr/0002-graduated-autonomy.md) slice 2, [ADR 0003](../adr/0003-lights-out-director.md)
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
  — [ADR 0002](../adr/0002-graduated-autonomy.md) 의 선행 슬라이스, Symphony 정합 gap #5.
  원본 [`WORKFLOW.md`](../symphony-original/WORKFLOW.md) 의 stage-agnostic 운영 규율을 **수확**
  (파일 포팅 아님): 공유 `WORKER_PROTOCOL` preamble(단일 살아있는 source-of-truth + no-scope-creep→
  typed child)을 `TERMINAL_CONTRACT` 와 같은 first-turn seam(`drive`)에 주입 → 모든 dispatch 경로;
  impl 템플릿 enrichment(reproduction-first · acceptance 미러링 · temp-proof revert · **PR feedback
  sweep** pre-handoff+on-arrival). 척추 = `WORKFLOW.md` 줄별 keep/adapt/reject triage(보드-쓰기 소유·
  직렬 merger·`report_outcome`·5 typed stage 에 대고). 워커-프롬프트 only — `decider.py`(slice 2)·
  보드 소유·merger 불변. graduated-autonomy 의 *worker-autonomy enabler*.
- [Director operator console — actionable dashboard + park notifications](2026-06-18-director-operator-console.md)
  — the human-reachability complement to lights-out ([ADR 0003](../adr/0003-lights-out-director.md)).
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
  drop/overwrite either side's work. gap #5 worker-protocol track ([ADR 0002](../adr/0002-graduated-autonomy.md)/[0003](../adr/0003-lights-out-director.md)):
  the PR-feedback-sweep shipped as prose (slice-1 `_IMPL_TEMPLATE` R7) but nothing *verifies* it,
  and the merger's only GREEN is the local integration gate. Spine (D1): code owns the irreversible
  merge — the land worker *prepares* (rebase/fix-CI/resolve-threads), then merger CODE runs a
  preservation tripwire (R1: merge-delta vs PR-delta; dropped hunk → escalate, heuristic→judgment)
  + a hygiene gate (R3: CI green + unresolved-threads==0, tri-state green→land/failing→escalate/
  pending→defer; threads-knob configurable) and only then squash-merges. Sweep result becomes
  structured `report_outcome` evidence the merger audits (R4, claim-vs-verified misfire log).
  Additive; merger stays board-free; `check.py`-on-rebased-main stays the independent second net.
- [Knowledge Format evolution — OKF 기반 키 + versioned 포맷 spec (Phase 1)](2026-06-18-knowledge-format-evolution.md)
  — [`okf-comparison.md`](../design-docs/okf-comparison.md) 가 고른 채택안을 집행: optional
  frontmatter 키 `type`(머신리더블 concept-kind, 디렉토리와 직교) + `tags`(flow 인라인 리스트,
  cross-cutting facet) + `resource`(페이지↔코드 자산 바인딩, Phase-2 drift 감지 선행) 추가 —
  모두 optional, 린트 permissive 유지(D3 불변). 평면 `read_frontmatter` 를 리스트 인식하도록
  additive 업그레이드(스칼라 byte-불변, OKF 블록폼 read-tolerant). 포맷을 implicit-in-lint →
  explicit `docs/KNOWLEDGE_FORMAT.md`(KF v1.0, conformance↔D-rule 매핑)으로 굳힘. memory
  concept-page 대표 backfill. 쿼리/navigation tool 은 Phase 2(별도 spec). 보호/포팅 wiring 은
  NG-4 로 연기.
- [Knowledge navigation tool — live query over the Phase-1 format (Phase 2)](2026-06-18-knowledge-navigation-tool.md)
  — Phase 1 포맷의 *consumer*. `plugin/scripts/nav.py`(library+CLI) + `docs-nav` 스킬이
  `type`/`tags`/`description`/`resource` + D5 링크 그래프를 **live**(매 호출 frontmatter 에서
  재계산, 영속 artifact 0)로 쿼리: `catalog`(type/tag/status 필터, `--json`, 바디 안 읽음),
  `links`/`backlinks`, `stale`(D4 재사용), `orphans`, `drift`(resource 의 git last-commit vs
  `last_verified`, advisory). `LINK`/staleness 를 `harness_lib` 로 추출해 lint·nav 단일 정의
  (core-belief 5). 커밋 catalog/생성 index.md/graph view(viz.html) 모두 NON-GOAL — index.md 는
  curation 유지(NG-2 reframe), agent-소비 우선. 게이트 비차단(read-only, on-demand).
  포팅: 도구·스킬이 `plugin/` 에 있어 자동 동행 + AGENTS.md/템플릿 포인터(belief 13).
- [Derived hierarchy — inferred typed graph + `nav.py tree`](2026-06-19-nav-derived-hierarchy.md)
  — Phase 2 nav 의 후속(typed-link Step 1). 새 frontmatter 키 없이 `(src.type,
  dst.type, 링크방향)` 에서 관계종류를 **추론**(`implements`/`refines`/`supersedes`/
  `grounded-in`; 미매칭은 untyped `links` 로 graceful)하는 `relations()` + 디렉토리를
  안 보고 frontmatter+링크만으로 **유도 계층(derived hierarchy)** 을 그리는 `nav.py
  tree`(forward=의존, `--reverse`=의존받음, cycle-safe). 한 트리에 ≥2 디렉토리 페이지가
  관계로 묶여 "구조 = 메타데이터의 projection(디렉토리 아님)" 을 눈으로 증명. read-only·
  live·게이트 비차단. 선언적 typed 키(KF v1.1)·viz.html·파일 재배치는 NON-GOAL. draft.
- [Charter & derived progress map — 의도 레이어](2026-06-19-charter-and-progress-map.md)
  — 긴 세션에서 묻히는 초기 빅픽처/기획 의도를 잡는 메타-docs 레이어. **author 하는 건
  하나** — 최상위 `docs/CHARTER.md`(`type: charter`, Orient 스텝 1에 편입). 원안 5 섹션은
  `2026-06-27-charter-restructure` 가 4 섹션으로 reframe — Mission 이 north-star 고도 +
  workstream 필터 흡수, 고정 assumption 섹션이 generative axiom 섹션으로, 정적 doneness
  섹션 삭제. **나머지는 전부 derive**: 메서드론이 약속만 하고 미구현이던 derived
  roadmap 을 실제로 — 구조화된 optional `phase` 키(KF v1.1) + `nav.py roadmap` 가
  initiative→phase→status 를 typed 그래프에서 projection(디렉토리 무관, 영속 0, plan 은
  `implements` 로 phase 상속), pivot 은 supersedes/refines 엣지로 인라인 표시(손으로 쓰는
  logs.md 아님). 포팅: 키/타입은 KNOWLEDGE_FORMAT 으로 byte-전파, charter 는 FILL
  템플릿 seed. 선언적 typed 키·viz.html·파일 재배치·enforcement 는 NON-GOAL.
  `2026-06-19-nav-derived-hierarchy.md` 의 후속(그 typed 그래프 위에 projection). draft.
- [Map depth — declared pivots + follow-up drill-down](2026-06-19-map-depth-pivots-followups.md)
  — charter-rooted `map` 위에 두 깊이 레이어. **③ pivot**: KF에 선언적 `supersedes` 키(KF
  v1.2, 첫 declared edge — 진짜 pivot인 supersession만) → roadmap/map에 `[superseded-by]`
  inline(희소·load-bearing). **② follow-up**: `nav.py followups`가 tech-debt-tracker 행을
  source 노드별로 묶는 drill-down + map에는 `[N follow-ups]` **카운트 배지**만(다량·맥락적이라
  inline 안 함 — volatility 원칙, pivot-flood 회피). charter-and-progress-map 후속. draft.
- [Format governance — enforced navigation keys (KF v2.0)](2026-06-20-format-governance-enforced-keys.md)
  — OKF의 permissive-on-optional 철학을 우리 거버넌스 레이어로 **flip**. load-bearing 키를
  optional→checked rule로 graded escalation: `type`+`description` blanket-required,
  `phase`는 product-spec에 required(plan은 implements로 상속 → exec-plan 강제 안 함, 44개
  중복 백필 회피), `resource`/`supersedes`/`phase`는 validate-if-present(해소/문법). type
  *값*은 free 유지(presence만). KF v2.0(breaking — 새 required 키). 마이그레이션 = description
  2개. 근거: OKF는 범용 교환 포맷이라 permissive, 우리는 단일 actor의 강제된 working memory. draft.
- [Harness packaging — portable strict-base template + two-agent profile model](2026-06-21-harness-packaging-portable-template.md)
  — **parent** spec for shipping the whole repo system as a strict, self-describing,
  implantable base ("strict base + add whatever each repo needs"). Six slices in
  dependency order: ① retire the dead memory-loop subsystem (feeder/imprint/dream/
  dreamer/tidy_stop + `docs/memory/`) → native CC memory + surfaced `docs/adr/` +
  tech-debt-absorbs-openq/limitations + on-demand `logs.md`; ② mature the
  `harness-init` seed templates into self-describing authoring guides (+ author the
  missing PRINCIPLES template, `references/` seed, ARCHITECTURE→`architecture-setup`
  redirect, exec-plans/index templates); ③ relocate `DIRECTOR.md` `docs/`→`.claude/`
  + retire the launcher skill; ④ consolidate the two scattered agent profiles
  (Director = `.claude/`+`.harness.json:director`; worker = `config.py DEFAULTS`
  reconciled + override surface + workspace_skills, qa retired) into one settable
  source each — no `agents/*` dirs; ⑤ clean + version-bump + re-describe the plugin
  manifests; ⑥ capstone: a checked-in, legacy-stripped, drift-checked base artifact +
  `SETUP.md`. Director stays centralized; no generator, no wizard, no README. draft.
- [Per-ticket session-event stream (live drill-down + derived telemetry)](2026-06-24-per-ticket-session-event-stream.md)
  — Phase 5 observability 트랙의 다음 consumer-richness 슬라이스. 워커 turn-stream firehose
  (`AppServerClient.on_event` — 오늘은 token usage 만 빼가고 나머지 play-by-play 는 버려짐)를
  runtime-agnostic 하게 normalize 해 **티켓별 append-only JSONL**(`.claude/harness/director-events/
  <id>.jsonl`)로 영속 → 대시보드가 `GET /api/v1/ticket/{id}/events`(history + 파생 telemetry
  timeseries) + `/stream`(라이브 SSE)로 서빙하고, in-flight/recent 행을 펼치면 그 티켓의 이벤트
  타임라인이 라이브로 흐르는 drill-down UI. 핵심 설계: 티켓별 파일은 그 티켓의 pool 스레드만
  쓰므로(retry 는 직렬) **single-writer → main-thread marshal 불필요**(토큰 누적 경로와 대비);
  telemetry 는 별도 producer 가 아니라 이벤트 로그에서 **파생**(DRY). codex/claude 워커가 같은
  vocabulary 를 emit 하므로 runtime 분기 0. id 는 `[A-Za-z0-9._-]+` 로 sanitize(traversal 0).
  Additive — `status.py`/`history.py`/queue/decider/merger/guardrail/worker-protocol 불변.
  Non-goals: full tool I/O 캡처·이벤트 로그 GC/rotation·신규 write 라우트·cross-ticket 집계.
  observability-dashboard/-polish 후속. draft.
- [Project dependency-graph view (whole-board DAG + live session overlay)](2026-06-26-project-dependency-graph-view.md)
  — Phase 5 observability 트랙의 다음 슬라이스: run-스코프 평면 리스트를 넘어 **프로젝트 전체**를
  dependency 모양으로 보는 렌즈. 오케스트레이터가 **보드 전체**(모든 state의 티켓 + `blockers`
  DAG)를 poll cadence로 `board.json`(`.claude/harness/director-board/`)에 atomic 영속 →
  대시보드가 **layered DAG**로 렌더(layer = wave → 같은 layer=병렬, 다음 layer=직렬; 스케줄러의
  자기 모델을 그대로 그림). 노드 lifecycle/telemetry는 `status.json` live 오버레이로 칠하고, 노드
  클릭 → 기존 per-ticket SSE 오버레이를 그래프 노드에 재-anchor(in-flight=라이브, terminal=기록
  재생). 순수 `build_board_view`가 topological layer(cycle/orphan-safe)를 부여(invariant 4),
  렌더/pan/zoom/collapse는 **단일 vendored offline 그래프 라이브러리**(Cytoscape+dagre+expand-collapse,
  `director/assets/`, 고정 라우트·CDN 0)가 담당 — Python stdlib-only invariant은 불변, JS-asset
  grain 완화는 **ADR 0006**로 범위 좁혀 기록. 기존 flat 리스트/operator console은 collapsible
  side rail로 이동(그래프=지도, rail=결정 inbox). Additive — `board_snapshot.py` 신규 + orchestrator
  poll-tick 1지점 + 신규 read 라우트; worker/decider/merger/status/ticket_events 불변. Non-goals:
  그래프에서 보드 편집·multi-team·board history/time-travel·신규 write 라우트·2번째 라이브러리.
  observability-dashboard/-polish/per-ticket-stream 후속. draft.
- [Project-graph view — design re-skin (drop the graph lib, keep the backend)](2026-06-27-project-graph-view-reskin.md)
  — `2026-06-26-project-dependency-graph-view` 의 **프론트 재디자인** 후속(백엔드는 그대로 유지).
  더 높은 fidelity의 디자인 언어를 채택: 캔버스 mini-label → **HTML 노드-카드**(identifier+state
  뱃지+2줄 제목+token bar), **wave N 라벨**, 헤더 **done/total** 진행 바 + active/blocked/failed
  카운트(이전 spec의 정성적 AC3 갭 해소), **state-aware SVG bezier 엣지**, telemetry strip + 타입별
  이벤트의 **리치 세션 오버레이**. 핵심 결정: **수제 렌더로 전환하며 vendored 그래프 라이브러리
  (Cytoscape+dagre ≈670KB)를 제거** — 서버가 이미 `layer`/`edges`를 계산하므로 클라는 위치만 계산
  (invariant 4), ADR 0006 완화는 *좁아짐/은퇴*. React/Vite 스택은 채택 안 함(invariant 1·ADR 0006);
  `board.json` producer·라우트·SSE·answer 콘솔·history 백엔드는 **전부 재사용**(behaviorally 불변).
  Non-goals: 프레임워크/빌드 스텝·백엔드 변경·context-fraction 바·아이콘/폰트 의존성·픽셀 클론. draft.
- [Charter restructure — 4 sections, generative axioms, a Mission that steers](2026-06-27-charter-restructure.md)
  — `2026-06-19-charter-and-progress-map` 의 **구조** 후속(의도 레이어 존재는 유지). CHARTER 를
  5 섹션 → **4**: (1) **Mission** 을 north-star 고도로 올려 — 가장 야심찬 end-state + 관측가능한
  "이럴 때 동작한다" 한 절(삭제된 doneness 의 접힌 잔여) + "어떤 workstream 이 옳은가" 필터 문장 —
  세 役을 한 문단에 흡수(별도 North Star 섹션 **안 둠**: north star 는 프로젝트 *위* 팀/비즈니스
  레벨이라 단일 repo charter 에선 Mission 과 일치). (2) **Locked assumptions → Core Axioms**:
  방어적("안 따진다") → 생성적("여기서 derive"); reversal test(*뒤집어도 같은 프로젝트인가?* 아니오→
  axiom) + lock-as-few 규칙, 기존 3 axiom 유지. (3) **"What done looks like" 삭제**(정적 스냅샷은
  rot — live doneness 는 `nav.py roadmap`, 방향성 doneness 는 Mission). Core Axioms 를 Design
  philosophy **앞**에(bedrock→building). 헤딩을 파싱하는 소비자 0 → content 변경, 구조 break 0.
  3 copy(self-host/template/base seed) 동일 전파 + prose reference 갱신. follow-up 4종(direction-GC
  workstream scout / Mission-distance roadmap view / axiom-violation lint / 실제 2번째 host)은 캡처만.
- [Workstream scout — 시스템 첫 divergent 에이전트](2026-06-27-workstream-scout.md)
  — charter reframe 의 operationalization(Mission=filter, axioms=screen 를 *쓰는* 에이전트).
  지금까지 모든 페르소나는 convergent(리뷰·게이트·gardener — 품질을 지키고 *아니오*); 이건 첫
  **divergent** 에이전트(가능성을 열고 *what if*). 형태: `scout` 스킬(오케스트레이터 — 풀 프로젝트
  맥락 보유, garden→doc-gardener 패턴의 fan-out 확장)이 stance 강제된 N개 generator
  (`workstream-scout` 페르소나 — moonshot/competitor-killer/first-principles-reframe/narrowest-wedge,
  **outward 웹 리서치**)를 펼치고, 비전마다 **독립** `vision-judge`(Mission+Core Axioms 루브릭)가
  Tier1(실행가능 initiative)/Tier2(foundational challenge — Mission·axiom 진화 필요)/drop 으로
  **라우팅**(keystone: axiom-screen = filter 아닌 **router** — axiom 깨는 명작은 죽이지도 enact
  하지도 않고 인간에게 escalate), 스킬이 own-context 로 종합해 2-tier `type: horizon` 제안 doc
  (`docs/horizons/`)을 씀. **propose, never enact**. on-demand v1(주기·완료트리거·auto-enact·
  Workflow-tool 의존·worker 벤더링은 Non-goal). phase methodology/02-workstream-scout.
- [Ideation Partner — the cabinet's first new role](2026-06-28-ideation-partner-cabinet.md)
  — adds the **front-of-pipeline** owner the system lacks (scout is one-shot, product-design
  avoids dialogue, the Director is operational): the **Partner**, a persistent human-surface
  ideation agent on the built-in daemon (`claude agents`). Mode 1 = on-demand dialogue that
  crystallizes a raw intuition into a **pre-spec brief** (optionally `scout`/`deep-research`)
  and drops it as one board ticket it **marks `agent-ready`** — loose-coupled, the orchestrator
  claims it; Mode 2 = a self-scheduled (`CronCreate durable`) proactive pass that produces
  `agent-ready` briefs and surfaces next initiatives (`PushNotification`) for awareness/veto.
  Stops at the brief (no spec/decompose/code/merge); board write = `issueCreate` + the
  agent-governed `agent-ready` label (orchestrator owns lifecycle **state**); the Partner is
  autonomous, human-at-edges (ADR 0011), parking only uncovered high-stakes taste. Reframes the
  center from a single Director into a **named-role cabinet** (ADR 0010 supersedes DIRECTOR.md
  §14 "exactly two"). Substrate = the Daemonized-Claude runtime ADR 0003 named as a separate
  track, now shipped + verified live (v2.1.195). Doc-only config v1; declarative `partner` block
  / second role are Non-goals. phase methodology/03-ideation-partner. draft.
