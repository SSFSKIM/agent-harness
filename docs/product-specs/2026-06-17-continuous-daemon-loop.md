---
status: stable
last_verified: 2026-06-17
owner: harness
phase: symphony/06-daemon-loop
type: product-spec
tags: [daemon, orchestrator, poll-loop, autonomy]
description: Daemon stage 2 that folds the orchestrator's two barriers into a single continuous tick loop, adding a run_forever mode that keeps polling forever even when the board is empty, with bounded top-up, reaping, reconciliation, and graceful shutdown.
---
# 연속 daemon 루프 (daemon stage 2)

Symphony 정합 트랙, **daemon 묶음의 2단계**. 근거:
[Symphony parity gap analysis](../design-docs/symphony-parity-gap.md) **gap #2**
(the identity gap — "우린 batch drainer 지 daemon 이 아니다"). 원본
[Symphony SPEC](../symphony-original/SPEC.md) §6.2 main loop · §8.1 always-on poll
loop · §14.4 operator intervention. 직전 슬라이스
[active-run reconciliation (stage 1)](2026-06-16-active-run-reconciliation.md)
위에 바로 올라탄다 — 그 슬라이스가 깔아둔 running-map·cancel·reconcile 조각을 **그대로**
재사용한다(아래 "설계 dividend"). 부모 로드맵
[symphony-director-orchestration](2026-06-14-symphony-director-orchestration.md).

## 문제 (Problem)

`director/orchestrator.py` 는 **두 겹의 barrier** 로 짜여 있다:

- **wave barrier** — `_dispatch_wave`(:346) 가 `while futures:` 로 claim 한 한 묶음을
  **전부 terminal 에 닿을 때까지** drain 한 뒤에야 반환한다. 그 사이 새 ready 티켓을 집지
  않고, 비어버린 동시성 슬롯을 새 일로 **채우지 않는다**(빨리 끝난 워커의 슬롯이 가장 느린
  워커가 끝날 때까지 논다).
- **pass barrier** — `run_until_drained`(:425) 는 wave 사이에서만 re-poll 하고, board 가
  비면 `stopped_reason="drained"` 로 **종료한다**.

그래서 우리는 batch drainer 다 — "ready 한 묶음을 받아 끝까지 돌리고 종료". Symphony 는
**daemon** 이다: `polling.interval_ms` 로 영원히 폴링하며, background 워커의 running-map 을
유지한 채 **계속 tick** 한다(그래서 mid-flight reconcile/kill 도 가능했다, stage 1). 나중에
생성된 티켓을 무한히 집고, 사람이 board 만 큐레이션하면 알아서 도는 "long-running automation
service" — 그게 Symphony 의 정체성인데 우리에겐 없다.

이 슬라이스는 두 barrier 를 **하나의 연속 tick 루프**로 접어, **영속 running-map** 위에서
도는 세 번째 모드 `run_forever`(daemon)를 추가한다. batch 경로(`--once`/기본 drain)는
**보존**한다.

## 요구사항 (Requirements)

- **R1 — 연속 daemon 모드.** 신규 `run_forever` 는 board 가 비어도 **종료하지 않고**
  shutdown 신호까지 영원히 폴링한다(always-on identity). (검증: 빈 board 에서 여러 tick 뒤에도
  반환 안 함; 주입된 `shutdown_event` 를 set 해야 반환.)
- **R2 — slot-free top-up.** 동시성 슬롯이 비는 **즉시** 다음 eligible 티켓을 claim 한다 —
  wave 전체가 drain 되길 기다리지 않는다. (검증: concurrency=2, board 가 A·B·C 제공, A·B
  dispatch 후 A 가 끝나면 **B 가 terminal 되기 전에** C 가 dispatch.)
- **R3 — bounded claim.** 한 tick 에 claim 하는 수는 free slot 수(`concurrency -
  len(futures)`) 이하 — board 의 `In Progress` 수가 실제 running 워커 수와 일치(flood-claim
  아님). (검증: concurrency=2, ready 5개 → 동시에 claim 2개·`In Progress` 2개, 나머지는
  슬롯이 빌 때 claim.)
- **R4 — daemon-scoped dedup.** 도는 티켓(running-map 안)은 다음 폴에서 재-claim 되지 않고,
  **claim 에 실패한 티켓**(board write raise/False)은 데몬 수명 동안 재시도에서 제외 + status
  로 surface(매 tick board write 스팸 방지). done/escalate/stuck 티켓은 board-as-truth 로
  자연히 `ready` 를 떠나 재폴되지 않는다. (검증: claim-실패 티켓이 다음 폴에서 재-claim 안 됨,
  status 에 기록; 도는 티켓 재-claim 0.)
- **R5 — stuck = status 신호(종료 아님).** ready 인데 전부 blocked(실패한 blocker / 사이클)
  이고 도는 워커도 없으면, 데몬은 `status.stuck(...)` 로 기록하고 idle heartbeat 를 남기되
  **루프를 계속**한다(사람이 unblock 하면 다음 폴이 집음). (검증: 실패 blocker 로 막힌 ready
  티켓 → `status.stuck` 기록, 데몬 종료 안 함, 계속 폴링.)
- **R6 — graceful shutdown.** SIGTERM/SIGINT(혹은 주입된 `shutdown_event`)면 데몬은 claim 을
  멈추고 in-flight 워커를 정상 reap(terminal reconcile)될 때까지 drain 한 뒤 최종 status 를
  flush 하고 종료한다. **2차 신호**면 모든 in-flight 의 `cancel_event` 를 set 해(stage 1
  cooperative cancel 재사용) 빠르게 멈춘다. signal handler 는 Event 만 flip(메인 스레드). (검증:
  신호 시 claim 중지·in-flight drain 후 반환; 2차 신호 → in-flight `cancelled` 로 종료.)
- **R7 — idle cadence + backoff seam.** idle(도는 워커 없음) 시 데몬은 `poll_interval_s`
  마다 폴하며 **busy-spin 하지 않고**, idle 대기는 shutdown 으로 **즉시** 깨어난다. "다음 idle
  대기 길이" 는 **단일 계산 지점**(`_idle_wait_s`, 오늘은 상수 `poll_interval_s` 반환)으로 고립
  — gap #3 exponential backoff 가 이 함수 하나만 갈아끼우면 된다(seam 만 설계, backoff 는 안
  만듦). (검증: idle 중 CPU busy-loop 없음; shutdown-during-idle 즉시 반환; `_idle_wait_s`
  단일 지점 존재.)
- **R8 — poll fail-soft.** top-up 폴이 raise 하면 데몬은 그 tick 의 top-up 만 스킵하고 살아남아
  다음 tick 에 회복한다(배치의 `poll_failed`-exit 와 대비; 또 다른 backoff seam). (검증:
  `list_ready_issues` 가 1회 raise → 데몬 계속, 다음 폴에 정상 claim.)
- **R9 — live heartbeat status.** `status.json` 에 daemon 의 `mode`(daemon|batch)·
  `phase`(active|idle|draining|stopped)·`last_poll_at`·`polls` 를 **additive** 로 추가한다.
  모든 status write 는 메인 tick 스레드에서만 일어난다 — `StatusWriter` 는 lock-free 단일
  writer(RELIABILITY R13) 그대로(워커는 풀에서 돌며 status 를 만지지 않음). 기존 reader
  (`dashboard.build_view`/`context_for`)는 안 깨짐. (검증: 메인 밖 StatusWriter 호출 0;
  새 필드 존재; 기존 status 테스트 GREEN.)
- **R10 — 배치 경로 보존.** `run_once`(`--once`)·`run_until_drained`(기본, drain-then-exit)
  의 관측 동작과 반환 스키마(`summaries`/`passes`/`stopped_reason`/`stuck`)는 **그대로** —
  기존 orchestrator 테스트가 회귀 그물. (검증: 기존 `tests/test_director_orchestrator.py`
  전부 GREEN; `--once`·기본 모드 동작 불변.)
- **R11 — `poll_interval_s` config knob.** 직전 declarative-config 계층으로 외부화:
  `config.DEFAULTS` + `DirectorConfig` + `resolve_settings` + CLI `--poll-interval`. 우선순위
  CLI > config > 기본(stage 1 `reconcile_interval_s` 와 동일 패턴). (검증: config override 가
  daemon cadence 를 바꾼다; CLI 가 config 를 이긴다.)

## 설계 (Design)

### 핵심 통찰 — daemon 은 "barrier 없는 _dispatch_wave" 가 아니다

barrier 만 걷어내면 될 것 같지만 **claim 규율이 다르다**. `_dispatch_wave` 는 eligible 전체를
앞에서 한꺼번에 claim(flood; pool 이 `concurrency` 로 실행만 제한)한다. daemon 은 **free slot
만큼만** claim(bounded top-up)해야 한다 — 그래야 (1) board 의 `In Progress` 가 실제 running 과
일치하고, (2) 매 폴마다 우선순위를 다시 반영할 수 있다(Symphony running-map 모델). 그래서
daemon 은 *별도 루프*고, batch 경로와는 **공유 primitive** 를 통해 hard logic 만 공유한다.

### 구성요소 / 파일

- **`director/orchestrator.py`**
  - **공유 primitive 추출(no-dup).** claim-before-act + submit(+cancel_event 등록) 과
    "완료된 future 하나 reap → reconcile → retry-or-terminal" 을 **하나의 구현**으로 묶어
    `_dispatch_wave` 와 `run_forever` 가 **같이 호출**한다(reconcile/retry/telemetry/
    `cancelled_states` 같은 까다로운 로직을 두 군데로 복제하지 않는다). 상태(running-map:
    `futures`/`in_flight`/`cancel_events`/`cancelled_states`/`attempts`/`results`)는 작은
    holder(예: `_RunState` dataclass 또는 현행 closure 캡처)에 담는다 — 정확한 mechanics 는
    ExecPlan 이 고른다. `_dispatch_wave` 는 이 primitive 를 쓰도록 리팩터하되 **관측 contract
    불변**(R10 회귀 그물).
  - **`run_forever(board, command, *, team, states, …, poll_interval_s, reconcile_interval_s,
    shutdown_event=None, install_signals=True, max_ticks=None, status=None, **wave_kwargs)`**
    — 신규 daemon 루프. 한 tick:
    1. **TOP UP** — `free = concurrency - len(futures)`; `free>0` 이면 `list_ready_issues`
       폴(try/except → 실패 시 그 tick top-up 스킵, R8) → `eligible_tickets` → running-map·
       claim-failed set 에 없는 것에서 앞 `free` 개를 claim+submit(공유 primitive).
    2. **WAIT** — `futures` 가 있으면 `wait(list(futures), timeout=poll_interval_s,
       return_when=FIRST_COMPLETED)`(완료에 즉시 반응); 없으면(idle) `shutdown_event.wait(
       _idle_wait_s())`(진짜로 잠들고 shutdown 으로 즉시 깸 — `wait([], timeout=)` 는 즉시
       반환해 **busy-spin** 이므로 쓰면 안 됨, R7).
    3. **REAP** — 완료된 future 들을 공유 reap primitive 로 reconcile(retry → 재submit /
       terminal → `status.terminal`). stage 1 의 `for fut in done:` 본문을 그대로 올린다.
    4. **RECONCILE-IN-FLIGHT** — stage 1 `_reconcile_in_flight` 를 monotonic
       `reconcile_interval_s` cadence 로 호출(서명·본문 **무변경**, dividend).
    5. **HEARTBEAT/STOP** — phase(active|idle|draining) + `last_poll_at`/`polls` 갱신; idle
       이고 ready-but-blocked 만 남으면 `status.stuck`. `shutdown_event` 가 서 있으면
       claim 중지 → in-flight drain(reap 만 계속) → 비면 `status.finished("shutdown")` 후
       반환. **빈 board 로는 절대 종료 안 함**(R1).
  - **graceful shutdown(R6).** `install_signals=True` 면 SIGTERM/SIGINT 핸들러 설치 — 1차
    신호: `shutdown_event.set()`(claim 중지·drain). 2차 신호: 모든 `cancel_events[*].set()`
    (in-flight 협조적 취소, stage 1 재사용). 핸들러는 **Event flip 만**(메인 스레드 사이에서
    실행 → 새 스레드 0, R13 안전). 테스트는 `shutdown_event` 를 주입 + `install_signals=False`
    + `max_ticks`(테스트 안전 상한, prod=None)로 구동.
  - **`resolve_settings` + `config.DEFAULTS`** 에 `poll_interval_s`(R11); `main()` 에
    `--daemon`(→`run_forever`) + `--poll-interval` 추가. 기본 모드는 그대로
    `run_until_drained`(R10).
- **`director/config.py`** — `poll_interval_s`(기본 10.0, `_pos_num`) 를 `DEFAULTS` +
  `DirectorConfig` 필드 + validator 에 추가(stage 1 `reconcile_interval_s` 와 동형).
- **`director/status.py`** — **additive** 한 heartbeat: `run` 에 `mode`/`phase`/
  `last_poll_at`/`polls` 필드 + 이를 갱신하는 가벼운 메서드(예: `polled(phase, *,
  stuck_count=…)` 또는 `heartbeat(...)`). lock-free 단일 writer·atomic flush 그대로; 기존
  필드/메서드 무변경(R9). dashboard 렌더링 폴리시는 비목표(스냅샷은 이미 `run`+`stuck` 를
  렌더하므로 신호는 그대로 노출됨).
- **`docs/DIRECTOR.md`** — daemon 운영 절(시작 `--daemon`, 멈춤 = SIGTERM/2차 SIGINT, idle/
  stuck heartbeat 읽는 법) 추가.
- **`docs/design-docs/symphony-parity-gap.md`** — gap #2 에 stage 2 cross-link(stage 1 이
  gap #1 에 단 것과 동형).

### 설계 dividend — stage 1 에서 **무변경**으로 올라타는 것

stage 1 을 "running-map 친화적"으로 짠 보상이 여기서 회수된다. 다음은 **서명·본문 그대로**
재사용(diff 로 무변경 검증 가능):

- `_reconcile_in_flight` — 이미 `futures.values()` + 명시 인자만 받는 free fn(wave-local
  상태 없음). 그대로 호출.
- `cancel_event` 배관 전부 — 워커별 `threading.Event` → `run.drive` → `app_server`
  short-poll → `TurnCancelled`; 그리고 `reconcile` 의 `kind=="cancelled"` 분기(:189). daemon
  의 operator-stop 과 2차-신호 cancel-all 이 **동일 메커니즘**으로 동작.
- claim-before-act + submit, reap-one(reconcile→retry/terminal) 본문 — 공유 primitive 로
  올려 daemon 이 batch 와 같은 코드를 부른다.

즉 *새* 코드는 사실상 루프 토폴로지(연속 tick + bounded top-up), idle/heartbeat, graceful
shutdown, `poll_interval_s` knob 뿐이다.

### 에러 / 경계

- **`wait([], timeout=)` 함정.** 빈 future 집합 wait 는 **즉시 반환** → idle 일 때 반드시
  `shutdown_event.wait(...)` 로 잠들어야 busy-spin 을 피한다(R7, D-67).
- **poll 실패.** `list_ready_issues` raise → 그 tick top-up 스킵·`status.last_error`/phase
  기록·생존(R8). 배치는 `poll_failed` 로 종료하지만 daemon 은 살아남는다(반복 실패 → backoff
  가 다룰 영역, seam 만).
- **claim 실패.** board write raise/False → 해당 티켓을 claim-failed set 에 넣어 데몬 수명
  동안 제외(매 폴 스팸 방지) + status surface(R4). "backoff 후 재-claim" 은 gap #3 로 연기.
- **완료 vs 취소 경합** — stage 1 과 동일: future 결과가 최종 승자, 한 번만 pop, 이중 처리
  없음(cancel_event set 은 이미 끝난 워커엔 무해).
- **drain 무한 대기.** 1차 신호 후 in-flight 가 오래 걸리면 drain 이 길어질 수 있음 → 2차
  신호가 cancel-all 로 강제 단축(R6). grace-timer 는 안 만든다(YAGNI; 2차 신호로 충분).
- **board-as-truth 재집음.** done 워커는 `Done` 으로, escalate/stuck/cancelled 는 `started`/
  사람-소유 상태로 가 `ready` 를 떠나므로 재폴되지 않음 — daemon dedup 가 추적할 건 running-map
  + claim-failed 뿐(R4).

## 비목표 (Non-goals)

- **Exponential backoff(gap #3) — stage 3.** idle/poll-fail/claim-fail 의 대기·재시도를
  지수 backoff 로. 이 슬라이스는 **seam 만** 판다(`_idle_wait_s` 단일 지점 = 오늘 상수). 절대
  여기서 backoff 를 만들지 않는다.
- **배치 경로 삭제/대체.** `run_once`·`run_until_drained` 는 CI/배치용으로 유지(R10). daemon
  은 *추가* 모드.
- **daemon 을 기본 모드로 승격.** 지금은 opt-in(`--daemon`); 기본은 drain-exit 유지(기존
  invocation/테스트 보존). 기본 승격은 사소한 별도 결정(D-72, 의도적 연기).
- **dashboard 렌더링 폴리시.** status.json 에 heartbeat 신호만 싣는다; "daemon idle/active"
  전용 UI 위젯은 별도(스냅샷은 이미 `run`+`stuck` 노출).
- **orchestrator-level inactivity stall-reap / 워크스페이스 cleanup / crash-recovery** —
  stage 1 에서와 동일하게 범위 밖.
- **poll·reconcile cadence 통합.** `poll_interval_s`(top-up)와 `reconcile_interval_s`
  (active-run, stage 1)는 별도 knob 유지(Symphony 도 폴/리컨실 분리); daemon 은 둘 다 매
  tick 자기 cadence 로 돈다.

## 수용 기준 (Acceptance)

- **R1** 빈 board 에서 `run_forever` 가 여러 tick 후에도 반환 안 함; `shutdown_event` set 시
  반환.
- **R2** concurrency=2, FakeBoard 가 A·B·C 제공 → A·B dispatch, A 완료 시 **B terminal 전에**
  C dispatch(top-up).
- **R3** concurrency=2, ready 5개 → 동시 `In Progress`(claim) 2개, 나머지는 슬롯이 비며 claim.
- **R4** claim-실패(board write False/raise) 티켓이 다음 폴에서 재-claim 0 + status 기록;
  도는 티켓 재-claim 0.
- **R5** 실패 blocker 로 막힌 ready 티켓 → `status.stuck` 기록, 데몬 **종료 안 함**, 계속 폴.
- **R6** drive 중 `shutdown_event` set → claim 중지 + in-flight reap 후 반환; 2차 신호
  경로(모든 cancel_event set) → in-flight `cancelled` 로 종료.
- **R7** idle 시 busy-spin 없음(`shutdown_event.wait` 사용); shutdown-during-idle 즉시 반환;
  `_idle_wait_s` 단일 지점 존재(오늘 상수).
- **R8** `list_ready_issues` 1회 raise → 데몬 생존, 다음 폴에 정상 claim.
- **R9** daemon 의 `status.json` 에 `mode`/`phase`/`last_poll_at`/`polls` 존재; 메인 밖
  StatusWriter 호출 0; 기존 status/dashboard 테스트 GREEN.
- **R10** 기존 `run_once`/`run_until_drained` 테스트 전부 GREEN(관측 동작 불변).
- **R11** `director.poll_interval_s` config override 가 cadence 변경; CLI `--poll-interval`
  가 config 를 이김.
- `python3 plugin/scripts/check.py` GREEN.

## Decision Log

- **D-63 공유 primitive, daemon 은 batch 의 hard logic 을 재사용.** claim-before-act+submit
  과 reap-one(reconcile/retry/telemetry/`cancelled_states`)을 단일 구현으로 묶어
  `_dispatch_wave`·`run_forever` 가 공유. 근거: 가장 까다로운 로직을 두 군데 복제하면 divergence
  버그. 배치 경로 관측 contract 는 불변(기존 테스트 = 회귀 그물). holder mechanics(`_RunState`
  vs closure)는 ExecPlan 선택.
- **D-64 daemon claim = bounded top-up(≤ free slots), batch flood-claim 아님.** 근거: board
  `In Progress` 가 실제 running 과 일치(정직) + 매 폴 우선순위 재반영(Symphony running-map).
  batch 는 flood-claim 그대로(관측 동작 보존).
- **D-65 daemon-scoped dedup = running-map + claim-failed set.** 근거: 성공 claim 은 `started`
  로 가 즉시 `ready` 를 떠남(board-as-truth) → 데몬이 추적할 잔여는 도는 티켓과 claim-실패
  티켓뿐. claim-실패는 데몬 수명 제외 + surface; "backoff 후 재-claim" 은 gap #3.
- **D-66 stuck = status 신호, 종료 아님.** 근거: daemon 은 종료 불가지만 사람은 "남은 게 전부
  blocked" 를 봐야 함 → 기존 `status.stuck` + idle heartbeat 재사용. 사람이 unblock 하면 다음
  폴이 집음.
- **D-67 idle 대기는 `shutdown_event.wait(timeout)`, busy 대기는 `wait(futures, timeout,
  FIRST_COMPLETED)`.** 근거: `wait([], timeout=)` 즉시 반환 → busy-spin. Event 대기는 진짜로
  자고 shutdown 으로 즉시 깸(shutdown 지연 최소화). reconcile 는 stage 1 monotonic cadence
  그대로.
- **D-68 graceful shutdown = 1차 신호 drain, 2차 신호 cancel-all.** 근거: 진행 중 작업을
  죽이지 않고(1차 drain) 빠른 강제 종료 옵션 제공(2차 = 모든 cancel_event set, stage 1 재사용).
  signal handler 는 Event flip 만(메인 스레드, R13 안전). grace-timer 불요(2차 신호로 충분,
  YAGNI). 테스트는 `shutdown_event` 주입 + `install_signals=False` + `max_ticks`.
- **D-69 daemon poll 실패는 fail-soft(생존), batch 는 `poll_failed`-exit.** 근거: daemon 정체성
  = 끊기지 않음; 일시적 board 오류로 죽으면 안 됨. 반복 실패 backoff 는 gap #3(seam).
- **D-70 backoff seam = `_idle_wait_s` 단일 지점.** 오늘은 상수 `poll_interval_s` 반환; gap #3
  이 이 함수 하나만 지수 backoff 로 교체. seam 설계만, backoff 는 안 만듦.
- **D-71 status heartbeat 는 additive.** `run.mode/phase/last_poll_at/polls` 추가, 기존 필드/
  메서드/reader 무변경. lock-free 단일 writer·atomic flush 유지(메인 tick 스레드, R13).
- **D-72 새 모드는 `--daemon`(opt-in); 기본은 `run_until_drained`(drain-exit).** 근거: 기본
  승격은 모든 기존 invocation/테스트를 바꾸는 별도 product 결정 → 의도적 연기(쉽게 뒤집힘).
  `--once` 도 보존.
