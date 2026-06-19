---
status: stable
last_verified: 2026-06-17
owner: harness
phase: symphony/06-daemon-backoff
type: product-spec
tags: [daemon, backoff, retry, orchestrator]
description: Daemon stage 3 that completes the retry model with a single exponential backoff for failed-worker re-dispatch, idle polling, and claim-failure re-admission, while keeping the batch path's immediate retry unchanged.
---
# Daemon exponential backoff (daemon stage 3 — 마지막)

Symphony 정합 트랙, **daemon 묶음의 3단계(마지막)**. 근거:
[Symphony parity gap analysis](../design-docs/symphony-parity-gap.md) **gap #3**
(retry model 완성). 원본 [Symphony SPEC](../symphony-original/SPEC.md) §8.4 exponential
retry backoff. 직전 슬라이스
[continuous daemon loop (stage 2)](2026-06-17-continuous-daemon-loop.md) +
[active-run reconciliation (stage 1)](2026-06-16-active-run-reconciliation.md) 위에 바로
올라탄다 — stage 2 가 남긴 **세 개의 backoff seam**(D-70 `_idle_wait_s`, D-73 `claim_failed`
liveness, poll-failure 재시도)을 여기서 회수한다. 이걸로 daemon 트랙(gap #1/#2/#3)이 닫힌다
(gap #4 config 완료; gap #5 agent-protocol 은 별도 트랙). 부모 로드맵
[symphony-director-orchestration](2026-06-14-symphony-director-orchestration.md).

## 문제 (Problem)

daemon(`run_forever`)은 실패·idle·장애에 대해 **즉시/고정 간격**으로만 반응한다 — Symphony 의
지수 backoff(§8.4)가 없다:

- **retry 즉시(§8.4 미충족).** `reconcile` 가 `{retry: True}` 를 반환하면 `_RunState.reap`
  가 **즉시** 재-dispatch 한다. 일시적 실패(rate-limit, flaky network)면 즉시 재시도가 같은
  벽에 부딪힌다. Symphony 는 `min(base·2^(attempt-1), cap)` 만큼 기다린 뒤 재시도한다.
- **idle 고정 폴(`_idle_wait_s` seam, D-70).** board 가 비어도 `poll_interval_s`(기본 10s)
  마다 영원히 폴 — 한가한 board 에 대한 트래커 API 부하가 무한.
- **poll 실패 무backoff.** board 가 죽어 `list_ready_issues` 가 계속 raise 해도 매
  `poll_interval_s` 마다 재시도(로그만 transition 1회로 throttle).
- **claim 실패 = 영구 배제(D-73 liveness gap).** claim write 가 한 번 raise/False 면 그 티켓은
  데몬 **수명 동안** 재-claim 에서 제외 — 일시적 board hiccup 이 영구 strand 가 된다.

이 슬라이스는 단일 `_backoff_s(n, base, cap)` 헬퍼로 **daemon 의 retry·idle·claim 을 지수
backoff** 시킨다. **batch 경로(`_dispatch_wave`/`run_once`/`run_until_drained`)는 즉시 retry
그대로**(batch/CI 는 빨리 drain 해야 하고, 기존 테스트 GREEN 이 보존의 증거).

## 요구사항 (Requirements)

- **R1 — `_backoff_s` 헬퍼.** 순수 함수 `_backoff_s(n, *, base, cap) = min(base·2^(n-1),
  cap)`(n≥1; n=1 → base). (검증: 단위 테스트로 n=1·2·3·큰 n 의 값/cap 확인.)
- **R2 — RETRY backoff(A, §8.4).** daemon 에서 budget 내 `failed` 워커는 **즉시**가 아니라
  `_backoff_s(retry#, backoff_base_s, backoff_cap_s)` 뒤에 재-dispatch 된다. reap 경로는 그
  시간 동안 **메인 스레드를 블록하지 않는다**(R13) — 재시도는 pending-retry holding map 에
  스케줄되고, tick 이 due 일 때(now ≥ retry_at) submit 한다. (검증: 실패 워커의 재-submit 이
  ~`backoff_base_s` 만큼 지연되고 그 사이 tick 은 계속 돈다.)
- **R3 — pending-retry slot 회계.** pending-retry 티켓은 claim 된(board `In Progress`) 예약
  상태이므로 concurrency 에 **포함**된다: `free = concurrency − len(futures) −
  len(pending_retry)`. 데몬은 claim/In-Progress 를 `concurrency` 초과로 늘리지 않는다.
  (검증: concurrency=1, 실패→pending-retry 동안 새 티켓 claim 0; 재시도 resolve 후 다음 claim.)
- **R4 — IDLE backoff(B).** 연속 idle 폴은 idle 대기를 `min(poll_interval_s·2^idle_streak,
  backoff_cap_s)` 로 키운다; 일이 잡히면(futures 비지 않음) streak 0 으로 리셋. (검증: 빈 board
  에서 idle 대기가 tick 마다 커지다 cap; 일 등장 시 리셋.)
- **R5 — POLL-FAILURE 는 idle backoff 로 흡수(C).** board 가 죽어 폴이 계속 raise 하고 도는
  워커도 없으면, 그 tick 은 idle(futures 빈) 경로로 떨어져 **R4 의 idle backoff 로 자연히
  완화**된다(매 `poll_interval_s` 폴 안 함); board 회복 시 streak 리셋. 별도 poll-failure curve
  없음(로그는 기존 transition-1회 throttle 유지). (검증: 계속 raise 하는 board → idle 대기 증가,
  회복 후 정상 claim.)
- **R6 — claim RE-ADMISSION backoff(D).** claim 실패는 영구 배제가 아니라
  `_backoff_s(claim#, backoff_base_s, backoff_cap_s)` 뒤 **재-admit**(재-claim 허용)된다;
  배제 구조는 bounded(성공 claim 시 해당 tid 제거). (검증: 일시적으로 실패하던 claim 이 backoff
  뒤 재시도되어 성공; 성공한 tid 는 backoff map 에서 사라짐.)
- **R7 — BATCH 불변.** `_dispatch_wave`/`run_once`/`run_until_drained` 의 retry 는 **즉시**
  그대로 — `_RunState.reap` 의 기본 동작 무변경. (검증: 기존 orchestrator 테스트 전부 GREEN;
  retry 타이밍 관측 동작 불변.)
- **R8 — config knob.** `backoff_base_s`(기본 10.0, Symphony §8.4) + `backoff_cap_s`(기본
  300.0)를 declarative-config 로 외부화: `config.DEFAULTS` + `DirectorConfig` + `_pos_num` +
  `resolve_settings` + CLI `--backoff-base`/`--backoff-cap`(우선순위 CLI>config>기본,
  `poll_interval_s` 와 동형). (검증: override 가 backoff 를 바꾼다; CLI 가 config 를 이김.)
- **R9 — graceful shutdown 상호작용.** draining 중에는 **새 retry submit 0 · 새 claim 0**
  (due-retry 단계와 top-up 모두 `not draining` 가드); pending-retry 는 abandon(board `In
  Progress` 로 남아 board-as-truth 가 다음 run 에 회수). 데몬은 도는 워커가 drain 되면 그대로
  종료(R6/stage2 불변). (검증: drain 중 실패→pending-retry 가 submit 되지 않고 데몬이 종료.)

## 설계 (Design)

### 핵심 통찰 — C 는 B 에 흡수, A 만 무겁다

네 seam 처럼 보이지만 **poll-failure(C)는 idle(B)에 흡수**된다: 실패한 폴은 일을 못 잡아
`futures` 가 비고 → idle 경로 → idle_streak 이 커지며 자연히 backoff(R5). poll-failure 전용
curve 불요(로그 throttle 는 이미 있음). 남는 실질 작업은 **A(retry)·B(idle)·D(claim)** + 공유
헬퍼. **A 가 유일하게 무겁다** — 메인 스레드를 블록하지 않으려면 "지연 submit" 을 위한 scheduled-
retry(holding map + slot 회계)가 필요하고, 이는 `_RunState.reap`(batch 와 공유)을 **건드리지
않고** daemon 쪽에 layering 해야 한다(batch 즉시 retry 보존).

### 구성요소 / 파일

- **`director/orchestrator.py`**
  - **`_backoff_s(n, *, base, cap)`** — 순수 `min(base·2^(n-1), cap)`(R1). retry·idle·claim
    이 공유. `_idle_wait_s(poll_interval_s, idle_streak, cap)` 를 이걸로 재구현(seam 채움,
    D-70): `_backoff_s(idle_streak+1, base=poll_interval_s, cap=cap)`.
  - **`_RunState.reap(done, on_retry=None)`** — retry 분기를 `(on_retry or self.submit)(ticket)`
    로 바꾼다(attempts bump + status.retrying 후). `on_retry=None`(batch) → **즉시 submit**
    (무변경, R7). daemon 은 `on_retry=schedule_retry` 를 넘겨 **지연**. 이것이 batch 를 안
    건드리고 retry backoff 를 layering 하는 단일 지점(D-75).
  - **`run_forever`** tick 에 추가(전부 daemon-local 상태, 메인 스레드):
    - `pending_retry: {tid: (ticket, retry_at)}` + `schedule_retry(ticket)`(on_retry 훅):
      `delay = _backoff_s(state.attempts[tid]-1, base=backoff_base_s, cap=backoff_cap_s)`
      (attempts 는 reap 에서 이미 bump → 첫 retry=attempts2 → `_backoff_s(1)=base`),
      `pending_retry[tid]=(ticket, now+delay)`. 티켓은 `state.in_flight` 에 그대로 남는다
      (예약; futures 엔 없음).
    - tick 시작에 `now = time.monotonic()` 1회 계산(due-retry·claim-readmit·reconcile cadence 공유).
    - **DUE-RETRY 단계**(`not draining`): `now ≥ retry_at` 인 pending 을 `state.submit` →
      futures 로 이동(in_flight 유지). (D-81: draining 중엔 submit 안 함 → abandon.)
    - **slot 회계**(R3/D-76): `free = concurrency − len(state.futures) − len(pending_retry)`.
    - **claim RE-ADMISSION**(D): `claim_retry_at: {tid: when}` + `claim_fails: {tid: count}`.
      top-up 전에 `now ≥ claim_retry_at[tid]` 인 tid 를 `state.claim_failed` 에서 discard(재-admit).
      `claim_and_submit` 가 False 면(이 tick 실패) `claim_fails[tid]++`,
      `claim_retry_at[tid]=now+_backoff_s(claim_fails[tid], base, cap)`. claim 성공 시 두 맵에서
      pop(bounded — 현재 실패 중인 tid 만; D-79).
    - **IDLE backoff**(B): `idle_streak` local. WAIT 의 idle 경로 =
      `shutdown_event.wait(_idle_wait_s(poll_interval_s, idle_streak, backoff_cap_s))` 후
      `idle_streak += 1`; busy 경로(futures 있음)에서 `idle_streak = 0`.
    - `backoff_base_s`/`backoff_cap_s` 인자 추가(기본 `config.DEFAULTS`).
  - `resolve_settings` + `main()`: `backoff_base_s`/`backoff_cap_s` 해석 + `run_forever` 로 전달;
    CLI `--backoff-base`/`--backoff-cap`.
- **`director/config.py`** — `backoff_base_s`(10.0) + `backoff_cap_s`(300.0) 를 `DEFAULTS` +
  `DirectorConfig` 필드 + `_build`(`_pos_num`)에 추가(`poll_interval_s` 와 동형).
- **`docs/DIRECTOR.md`** — §12 daemon 절에 backoff 한 단락(retry/idle/claim 이 지수 backoff;
  knob).
- **`docs/design-docs/symphony-parity-gap.md`** — gap #3 에 stage 3 cross-link + daemon 트랙
  CLOSED 표기.

### 에러 / 경계

- **메인 스레드 블록 금지(R13).** retry 대기는 `time.sleep` 가 아니라 pending_retry 의
  retry_at 타임스탬프 — tick 이 due 를 검사해 submit. 모든 backoff 상태는 daemon-local,
  메인 스레드에서만 mutate(stage 1/2 와 동일).
- **pending-retry 와 active-run reconciliation.** pending-retry 티켓엔 도는 워커(cancel_event)가
  없다 — reconcile_in_flight 는 futures 만 본다. 사람이 pending-retry 티켓을 옮겨도 즉시 취소되진
  않지만, retry 가 submit 되면 다음 reconcile 가 잡는다(짧은 창; 허용). board-as-truth 가
  궁극 정합.
- **claim 영구 실패.** bad-config 같은 영구 실패면 backoff 가 cap 에서 머물며 `cap` 마다 재시도
  (영구 배제보다 나음; status 로 surface). 일시적 실패는 backoff 뒤 회복.
- **idle vs busy 경계에서 retry/claim 재-admit.** DUE-RETRY·claim-readmit 은 `not draining`
  이고 free 슬롯이 있을 때만 의미; 슬롯이 꽉 차면 pending 은 다음 tick 까지 대기(과-commit 없음).

## 비목표 (Non-goals)

- **batch 경로의 retry backoff.** `_dispatch_wave`/`run_until_drained`/`run_once` 는 즉시 retry
  유지(R7). retry backoff 는 daemon 전용(D-74).
- **Symphony "정상 종료 후 ~1s continuation 재-check"(§8.4 후반).** 우리 active-run
  reconciliation(stage 1)이 `reconcile_interval_s` 마다 in-flight 상태를 되읽어 사람의 mid-flight
  이동을 잡으므로 그 정신은 이미 충족 — 완료-직전 per-completion 재-check 는 backoff 가 아닌 별도
  reconcile-hardening. NON-GOAL(D-80).
- **poll-failure 전용 backoff curve(C).** idle backoff(B)로 흡수(R5/D-77).
- **jitter / full-jitter randomized backoff.** 결정적 `min(base·2^(n-1), cap)` 만(YAGNI;
  Symphony 도 deterministic). thundering-herd 는 단일-데몬 모델에 무관.
- **per-use 별도 base/cap knob.** 공유 `backoff_base_s`/`backoff_cap_s` 2개만(idle 의 base 는
  `poll_interval_s` 재사용); 5개 knob 은 YAGNI(D-78).

## 수용 기준 (Acceptance)

- **R1** `_backoff_s(1)=base`, `_backoff_s(2)=2·base`, `_backoff_s(3)=4·base`, 큰 n → cap.
- **R2** daemon 에서 1회 실패하는 워커(budget 내)의 재-submit 이 ~`backoff_base_s` 지연되고,
  대기 중 tick 은 계속 돈다(메인 블록 0). (injected event + 짧은 base 로 검증.)
- **R3** concurrency=1: 티켓 A 가 실패→pending-retry 인 동안 다른 ready 티켓이 claim 되지 않음
  (free=0); A 재시도 resolve 후 다음 claim.
- **R4** 빈 board: idle 대기가 `poll_interval`→`2·`→`4·`… cap 으로 증가(`polls` cadence 관측);
  일 등장 시 `poll_interval` 로 리셋.
- **R5** 계속 raise 하는 board(도는 워커 없음): idle backoff 로 폴 빈도가 줄고(매 poll_interval
  아님), board 회복 시 정상 claim.
- **R6** 처음 N회 claim 이 False/raise 인 board: 티켓이 backoff 뒤 재-claim 되어 결국 성공;
  성공 후 `claim_retry_at`/`claim_fails` 에서 제거.
- **R7** 기존 `run_once`/`run_until_drained`/`_dispatch_wave`/`ActiveRunReconcile`/`DaemonLoop`
  테스트 전부 GREEN(batch 즉시 retry 불변).
- **R8** `director.backoff_base_s`/`backoff_cap_s` config override + CLI `--backoff-base`/
  `--backoff-cap` 가 동작; CLI>config>기본.
- **R9** drain 중 실패→pending-retry 가 submit 되지 않고(새 claim 0), 도는 워커 drain 후 데몬 종료.
- `python3 plugin/scripts/check.py` GREEN.

## Decision Log

- **D-74 ONE 슬라이스(A retry + B idle + D claim), daemon 전용, batch 즉시-retry 불변.** 근거:
  셋 다 `run_forever` 안 + 단일 `_backoff_s` 공유 → 한 subsystem(독립 제품 아님). batch backoff 는
  regression 위험 + batch 는 빨리 drain 해야 하므로 제외(기존 테스트 GREEN = 보존 증거).
- **D-75 retry backoff = `_RunState.reap(on_retry=…)` 훅 + daemon scheduled-retry, blocking
  sleep 아님.** 근거: reap 은 batch 공유 — 훅 기본(None)은 즉시 submit(batch 무변경), daemon 만
  지연 스케줄. `time.sleep` 은 메인 스레드를 막아 R13/tick 을 깨뜨리므로 retry_at 타임스탬프 +
  tick due-검사.
- **D-76 pending-retry 는 concurrency 에 포함**(`free = concurrency − futures − pending_retry`).
  근거: claim 된(In Progress) 예약 슬롯 — 빼지 않으면 board 가 concurrency 초과로 부풀고 over-commit.
- **D-77 poll-failure backoff(C)는 idle backoff(B)로 흡수.** 근거: 실패 폴 → futures 빈 → idle
  경로 → idle_streak backoff. 전용 curve 는 중복; 로그 throttle 은 이미 존재.
- **D-78 공유 knob 2개**(`backoff_base_s` 10s = Symphony §8.4, `backoff_cap_s` 300s); idle base =
  `poll_interval_s` 재사용, retry/claim base = `backoff_base_s`, cap 공유. 근거: per-use 5개 knob 은
  YAGNI; 자연 scale 이 비슷.
- **D-79 claim re-admission = per-tid backoff map, bounded.** `claim_retry_at`/`claim_fails` 는
  현재 실패 중인 tid 만(성공 시 pop) → D-73 의 무한 성장 + transient-as-permanent 동시 해소.
- **D-80 Symphony per-completion ~1s 재-check = NON-GOAL.** active-run reconciliation 이 정신을
  충족(in-flight 주기적 재독).
- **D-81 pending-retry 는 graceful drain 에서 abandon.** draining 중 due-retry submit 안 함 →
  board `In Progress` 로 남아 board-as-truth 가 회수. 근거: shutdown 중 새 일 시작 금지.
