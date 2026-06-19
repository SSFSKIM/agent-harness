---
status: stable
last_verified: 2026-06-16
owner: harness
phase: symphony/06-daemon-reconciliation
type: product-spec
tags: [daemon, reconciliation, worker, orchestrator]
description: Daemon stage 1 that periodically re-reads in-flight ticket states while workers run and cooperatively cancels workers whose tickets a human moved out of In Progress, reconciling between completions without breaking the single-writer model.
---
# Active-run reconciliation + 워커 취소 (daemon stage 1)

Symphony 정합 트랙, **daemon 묶음의 1단계**. 근거:
[Symphony parity gap analysis](../design-docs/symphony-parity-gap.md) **gap #1**
(가장 큰 correctness/operability 격차). 원본 [Symphony SPEC](../symphony-original/SPEC.md)
§8.5 active-run reconciliation · §16.3 `reconcile_running_issues` · §14.4 operator
intervention · §7.2 `CanceledByReconciliation`. 부모 로드맵
[symphony-director-orchestration](2026-06-14-symphony-director-orchestration.md).

## 문제 (Problem)

워커를 dispatch 한 뒤 orchestrator 는 그 워커가 terminal 에 닿을 때까지 **트래커를
다시 안 본다.** `director/orchestrator.py` 의 `_dispatch_wave` 는
`wait(FIRST_COMPLETED)` 에 **블록**(wave-barrier)돼 있어, 워커 완료 이벤트에만 반응한다.
결과:

- 사람이 Linear 에서 티켓을 `In Progress` 밖으로(예: Cancelled/Done/다른 상태) 옮겨도
  **돌고 있는 워커를 멈출 방법이 없다.** 이건 Symphony 의 **주 운영 레버**(§14.4)인데
  우리에겐 없다 — 폭주하는/방향 틀린 워커를 사람이 트래커로 세울 수 없다.
- orchestrator 가 in-flight 티켓의 외부 상태 변화를 mid-flight 에 전혀 관측하지 못한다.

**Stall 은 별개 — 이미 대체로 처리됨(이 슬라이스 범위 밖):** `app_server.run_turn`
의 `read_timeout_s`(per-event)는 codex 가 침묵하면 `ReadTimeout` 을 던지고 → `drive`
가 실패 → `reconcile` 가 retry-once 한다. 즉 *조용한* 워커는 이미 failed→retry 경로로
회수된다. orchestrator 레벨의 `started_at` 기반 stall 은 "wall-clock 초과"라는 다른(그리고
거친) 신호라 정상적으로 긴 멀티턴 티켓을 잘못 죽인다 — 그래서 stage 1 에선 안 만든다(아래
Non-goals + D-61).

## 요구사항 (Requirements)

- **R1 — board 가 in-flight 상태를 되읽을 수 있다.** `board/linear.py` 에
  `fetch_issue_states_by_ids(ids) -> {id: {"state_id", "state_name", "state_type"}}`
  를 추가(LinearBoard 메서드 + 모듈 함수 + MockBoard). (검증: 주어진 id 들의 현재 상태를
  반환; mock 즉시·linear 쿼리 파서 단위 테스트.)
- **R2 — 워커가 도는 동안 주기적 reconciliation.** wave 루프는 워커가 하나도 완료되지
  않아도 최대 `reconcile_interval_s` 마다 깨어나 in-flight 티켓 전체의 트래커 상태를
  되읽는다. (검증: 한 티켓 상태를 mid-run 에 뒤집는 FakeBoard 에서 루프가 ~interval 안에
  관측.)
- **R3 — operator cancel.** in-flight 티켓이 더 이상 `started` 상태가 아니면(사람이
  terminal/다른 상태로 옮김) 그 워커를 **멈춘다**: `drive` 가 `cancelled` disposition 을
  반환하고, app-server 서브프로세스가 정리되며, orchestrator 는 그 티켓을 **retry 하지
  않고 board 를 다시 transition 하지 않는다**(새 상태는 사람 소유) — released/cancelled
  summary + 코멘트만 기록. (검증: mid-drive 에 티켓을 Done 으로 뒤집으면 워커가 멈추고,
  retry 0, summary status `cancelled`, set_state 호출 0.)
- **R4 — 취소는 mid-turn 에 반응한다.** 워커의 app-server read loop 가 취소 신호를 turn
  경계뿐 아니라 bounded poll 안에서 관측해, 긴 turn 도 끊는다. (검증: 긴 mock turn 이
  cancel 로 중도 종료.)
- **R5 — reconciliation 은 fail-soft.** `fetch_issue_states_by_ids` 오류는 모든 워커를
  계속 돌리고 다음 패스에 재시도(절대 wave 를 가라앉히지 않음); reconciliation 은 wave
  루프로 예외를 던지지 않는다(§16.3 "state refresh 실패 → 워커 유지"; RELIABILITY R12 의
  instrumentation-totality grain). (검증: board fetch 가 raise → 워커 유지, wave 완료.)
- **R6 — 단일 writer 불변식 유지.** reconciliation 은 wave 루프(메인) 스레드에서 돈다 —
  `StatusWriter` 는 메인-스레드 lock-free 단일 writer(RELIABILITY R13) 그대로. 유일한
  cross-thread 객체는 워커별 cancel `threading.Event`(thread-safe); cancelled 결과는 기존
  `status.terminal` 경로로 기록(새 writer 진입점 없음). (검증: 메인 스레드 밖 StatusWriter
  호출 0; 게이트 GREEN.)
- **R7 — cadence 는 설정 가능.** `director.reconcile_interval_s`(기본 15.0)를 직전
  declarative-config 계층으로 외부화 + CLI `--reconcile-interval`. (검증: config override
  가 cadence 를 바꾼다; 우선순위 CLI > config > 기본.)

## 설계 (Design)

**핵심 통찰 — refactor 는 작다.** `_dispatch_wave` 의 `futures` dict + `in_flight` set 이
**이미 running-map** 이다. 빠진 건 "루프가 완료 이벤트 사이에도 깨어나 reconcile 하는 것"
뿐 — `wait(...)` 에 `timeout` 을 주고 monotonic cadence 로 reconcile 패스를 끼우면 된다.
별도 reconciler 스레드 없음 → reconcile 가 메인 스레드에서 돌아 R13 이 공짜로 성립.

**구성요소/파일.**

- `director/board/linear.py` — `fetch_issue_states_by_ids(ids, …)` + `LinearBoard`
  메서드 + MockBoard. GraphQL: `issues(filter:{ id:{ in:$ids } }){ nodes{ id state{ id
  name type } } }`(기존 `_post`/error 처리 재사용). 반환 `{id: {state_id, state_name,
  state_type}}`. 빈 `ids` → API 호출 없이 `{}`(§17.3 "empty fetch → no call").
- `director/worker/app_server.py` — `AppServerClient(cancel_event=None)`. `_read_msg`
  의 `select` 를 짧은 슬라이스로 폴링하며 매 슬라이스 `cancel_event.is_set()` 확인 →
  set 이면 신설 `class TurnCancelled(Exception)` 을 raise(mid-turn 인터럽트, R4).
  `TurnCancelled` 은 `AppServerError` 의 서브클래스가 **아니다** — `drive` 가 실패와
  구분해 잡아야 하므로(취소→retry 안 함 / 실패→retry-once).
- `director/run.py` `drive` — `cancel_event` 인자 추가; 각 turn 반복 진입에서
  `cancel_event.is_set()` 확인 + turn 루프 전체를 `try/except TurnCancelled` 로 감싸
  `{"kind":"cancelled","reason":"reconciliation","turns",…,telemetry}` 반환. `with
  client` 가 서브프로세스를 teardown(stop()). decider(watched turnReview 대기) 중에는
  cancel 이 즉시 안 먹고 decider 반환(≤ `turn_review_timeout`) 후 잡힘 — 알려진 latency
  bound(파킹된 워커는 compute 를 안 태우므로 허용; D-61 인접).
- `director/orchestrator.py`
  - `dispatch(ticket, …, cancel_event=…)` 가 `cancel_event` 를 `run.drive` 로 통과.
  - `_dispatch_wave`: 워커별 `cancel_events: {tid: Event}`(submit 에서 생성); `wait(...,
    timeout=reconcile_interval_s, return_when=FIRST_COMPLETED)`; `time.monotonic()`
    기반 cadence 로 `_reconcile_in_flight` 호출(완료 폭주에도 ~interval 보장).
  - `_reconcile_in_flight(board, futures, states)`(메인 스레드): in-flight tid 들을
    `board.fetch_issue_states_by_ids` 로 되읽어, `state_id != states["started"]` 인
    티켓의 `cancel_events[tid].set()`. fetch 예외는 잡아 로그+스킵(R5).
  - `reconcile(...)` 에 `kind == "cancelled"` 분기 추가: `set_state` 없음(사람이 이미
    옮김), 코멘트("🛑 외부에서 In Progress 밖으로 이동 — 워커 중지"), summary `status:
    "cancelled", final_state` = 관측된 외부 상태; retry 없음. cancelled 워커의 future 는
    이후 wake 에 완료로 잡혀 `status.terminal` 로 기록(기존 경로, R6).
  - `resolve_settings` + `config.DEFAULTS` 에 `reconcile_interval_s`(R7).
- `director/config.py` — `reconcile_interval_s`(기본 15.0, `_pos_num`) 추가.

**에러/경계.**
- 경합(완료 vs 취소 동시): future 가 먼저 완료 → terminal 기록, cancel set 은 무해(워커
  이미 끝남); cancel 먼저지만 워커가 그 turn 을 terminal 로 끝내면 terminal 기록 — future
  결과가 최종 승자(한 번만 pop). 이중 처리 없음.
- `fetch_issue_states_by_ids` 가 일부 id 누락(삭제된 티켓 등) → **보수적으로 유지**(미확인
  상태로 취소하지 않음); 확인된 non-started 상태만 취소.
- `TurnCancelled` 이 `drive` 에서 안 잡히고 새면 `dispatch` 의 generic except 가 failed 로
  → retry(오답). 그래서 `drive` 가 turn 루프 전체를 감싸 **반드시** cancelled 로 변환.

## 비목표 (Non-goals)

- **연속 forever-tick daemon 루프(gap #2) — stage 2.** 이 슬라이스는 **wave 안에서**
  reconcile 한다; `run_until_drained` 는 여전히 drained 에 종료. cancel_event /
  fetch_issue_states_by_ids / cancelled-disposition / running-map 은 stage 2 가 wave-
  barrier 를 걷어낼 때 그대로 올라탄다(깨끗한 layering).
- **Exponential backoff(gap #3) — stage 3.**
- **orchestrator 레벨 inactivity-stall_timeout.** `read_timeout_s`(per-event)가 이미
  조용한 워커를 failed→retry 로 회수; 제대로 된 inactivity-stall 은 last-event 타임스탬프
  plumbing(현재 status.py 는 `started_at` 만 추적)이 필요 → 별도 follow-on. `started_at`
  기반 wall-clock stall 은 정상적으로 긴 티켓을 죽이므로 채택하지 않음(D-61).
- **terminal 워크스페이스 cleanup / startup sweep(§8.6)** — 별도.
- board write-back 으로 cancel 을 표기(set_state) — 안 함(사람이 새 상태 소유, D-62).

## 수용 기준 (Acceptance)

- `fetch_issue_states_by_ids` 가 동작(MockBoard 즉시; LinearBoard 쿼리/정규화 단위 테스트;
  빈 ids → 호출 0).
- FakeBoard 가 티켓 A 의 상태를 A 의 워커 mid-drive 중 Done 으로 뒤집으면: 워커가
  ~`reconcile_interval_s` 안에 멈추고, `drive` 가 `cancelled` 반환, orchestrator 가 status
  `cancelled` 기록, **retry 0 · set_state 0**, 코멘트 1건(R2/R3).
- 긴 mock turn 이 cancel 로 mid-turn 중단(R4).
- reconciliation 중 board fetch 가 raise → 워커 유지, wave 정상 완료(R5).
- reconcile 패스가 메인 스레드에서만 StatusWriter 를 만진다(R6); `python3
  plugin/scripts/check.py` GREEN.
- `director.reconcile_interval_s` config override 가 cadence 를 바꾼다(R7).

## Decision Log

- **D-59 취소 = cooperative `cancel_event`(app-server read loop mid-turn + turn 사이),
  orchestrator 의 hard 서브프로세스 kill 아님.** 근거: 서브프로세스 lifecycle 을 drive 의
  `with client` 안에 둬 깨끗이 teardown(orchestrator 가 워커 내부로 손 안 뻗음); mid-turn
  반응성은 짧은 select 폴로. `TurnCancelled` 은 `AppServerError` 비-서브클래스 — drive 가
  취소(→retry 안 함)와 실패(→retry-once)를 구분.
- **D-60 reconcile 는 wave-loop 스레드에서 `wait(timeout=…)` + monotonic cadence,
  별도 스레드 아님.** 근거: `futures` dict 가 이미 running-map; 기존 barrier 에 timeout 만
  더하는 게 최소 변경이고, 메인 스레드 유지로 StatusWriter 단일-writer 불변식(R13)을 marshal
  없이 보존.
- **D-61 stall-reap 연기.** `read_timeout_s`(per-event inactivity)가 이미 조용한 워커를
  failed→retry 로 회수; `started_at` 기반 wall-clock stall 은 정상적으로 긴 멀티턴 티켓을
  잘못 죽이고, 제대로 된 inactivity-stall 은 last-event plumbing 필요 → follow-on. 사람의
  "+stall-reap" 요청은 read_timeout_s 로 실질 충족됨(범위 좁힘, 명시적으로 surface).
- **D-62 cancelled 워커는 board 를 re-transition 하지 않는다** — 사람이 새 상태를 소유하므로
  코멘트 + released summary 만(Symphony "terminate without cleanup").
