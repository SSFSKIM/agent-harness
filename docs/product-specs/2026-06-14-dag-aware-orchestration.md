---
status: stable
last_verified: 2026-06-14
owner: harness
---
# DAG-aware 연속 오케스트레이션 (Phase 3a)

부모 spec: [Symphony 티켓 오케스트레이션 + 중앙 Director](2026-06-14-symphony-director-orchestration.md)
(Phase 3 = 티켓 DAG + dev-stage taxonomy). 선행: [오케스트레이터 — poll→dispatch→reconcile
루프](2026-06-14-orchestrator-dispatch-loop.md) (thin·watched 단일 패스). 이 spec 은
Phase 3 의 **3a — DAG 메커닉**만 책임진다(사람 결정, 2026-06-14: 3a 먼저). **3b —
dev-stage taxonomy**(티켓 type→하네스 doc 워크플로)는 별도 spec.

핵심 깨달음: `blocked_by` 를 존중하려면 오케스트레이터가 **연속(re-poll)** 이어야 한다.
B 가 A 에 의해 blocked 이면, 단일 poll 시점엔 B 가 ineligible 이고, A 가 끝난 **뒤** poll
해야 B 가 dispatch 가능해진다 — 단일 패스로는 영영 못 잡는다. 그래서 3a 는 직전 단계에서
미룬 "연속 루프"를 (여전히 watched 로) 되살린다. board 상태를 진실의 원천으로 삼아(완료
티켓은 reconcile 로 done 상태가 돼 ready 에서 빠지고, 그 의존 티켓은 blocker 가 done 이라
eligible 해짐) 메모리 내 완료 장부 없이 DAG 가 풀린다.

## 문제 (Problem)

- 오케스트레이터는 단일 패스다: 한 번 poll→ready 전부 dispatch→reconcile→종료. `blocked_by`
  를 못 지킨다 — 막힌 티켓을 (잘못) 즉시 dispatch 하거나, 필터하면 blocker 가 끝난 뒤
  다시 와서 집을 길이 없다.
- 오케스트레이터는 `blocked_by` 관계를 **전혀 안 본다**: ready 상태면 무조건 dispatch.
  직전 단계의 surprises 로그가 "ready 진입은 사람이 관리"를 유일한 안전판으로 적었다 —
  실제 의존성이 있으면 사람이 막힌 티켓을 손으로 ready 에서 빼야 해, DAG 의 의미가 없다.
- 워커가 만든 자식 티켓(작업 분해)을 집을 수 없다 — 단일 패스가 이미 poll 을 끝냈다.

관찰 가능한 부재: "A→B→C 체인을 넣으면 A 먼저, A 끝나면 B, B 끝나면 C 순으로 자동
dispatch 되고, 막힌 동안 B/C 는 절대 안 뜬다"를 돌리는 루프가 없다.

## 요구사항 (Requirements)

- **R1 — blocker 읽기.** board 어댑터가 각 ready 티켓의 `blocked_by` blocker 들과 그 blocker
  의 상태(type)를 읽는다. (검증: B 가 A 에 blocked 일 때 B 가 blocker=[{A, A의 state type}]
  로 보고됨.)
- **R2 — DAG eligibility.** 티켓은 ready 상태 **그리고** 모든 blocker 가 done-type(기본
  `completed`)일 때만 dispatch 대상이다. 막힌 티켓은 dispatch 안 함. (검증: B blocked_by A
  에서, A 가 done 아니면 B 는 절대 dispatch 안 되고, A 가 completed 되면 B 가 eligible.)
- **R3 — 연속 re-poll 루프.** 오케스트레이터가 DAG 가 소진될 때까지 re-poll: 매 패스가
  새로 eligible 해진 티켓을 dispatch; eligible 도 in-flight 도 없으면 종료. (검증: A→B→C 가
  패스를 거쳐 A→B→C 순서로 dispatch 되고 종료.)
- **R4 — 워커-생성 티켓.** 런 도중 ready 상태로 생긴 티켓(워커가 `linear_graphql` 로 생성,
  또는 외부 추가)이 이후 poll 에서 eligible 해지면 dispatch 된다. (검증: 첫 패스 후 새 ready
  티켓을 넣으면 다음 패스가 집어 dispatch.)
- **R5 — watched + bounded.** 루프는 watched(Director 가 공유 큐로 approval 응답; 자율
  정책 없음). 안전 bound(최대 패스 수·최대 dispatch 티켓 수)로 병적 DAG(사이클·폭주
  워커-생성)가 무한루프 대신 로그 남기고 종료. (검증: bound 초과 시 stopped_reason 과 함께
  종료.)
- **R6 — 동시성/불변식 보존.** 연속 루프가 직전 단계의 bounded-concurrency dispatch +
  단일 큐 락 + board-는-main-스레드만 불변식을 유지. wave 모델이라 패스 간 in-flight 중복
  없음. (검증: 한 패스가 그 wave 를 다 drain 한 뒤 re-poll — 같은 티켓이 두 번 dispatch
  안 됨.)
- **R7 — cycle/deadlock 검출.** eligible==0 인데 in-flight==0 이고 ready-but-blocked 티켓이
  남으면(사이클이거나 blocker 가 실패해 done 못 됨), 루프는 spin 하지 않고 종료하며 막힌
  티켓을 보고한다. (검증: A↔B 상호 block → 진전 없음 감지·종료, 행 안 걸림.)

## 설계 (Design)

### wave 모델 (왜 이게 thin 한 정답인가)

연속 루프를 **wave** 로 구현: 반복 [poll → eligible 계산 → 그 eligible 셋을 dispatch 하고
**그 wave 가 다 끝날 때까지** drain → re-poll]. wave N+1 은 wave N 이 전부 끝난 뒤 시작
(barrier). 체인·다이아몬드 등 모든 DAG 를 정확히 푼다(예: A→{B,C}→D 는 wave1={A},
wave2={B,C} 병렬, wave3={D}). barrier 때문에 최대 throughput 은 아니다(빠른 B 가 느린 C 를
기다림) — streaming dispatch 는 non-goal(perf, 후순위). board 상태가 진실이라 메모리 완료
장부가 불필요: 완료 티켓은 done 상태→ready 에서 빠지고, 그 의존 티켓은 blocker done→
eligible. 실패한 blocker 는 done 이 아니라 의존 티켓이 계속 막혀, 끝내 eligible==0 ·
in-flight==0 · blocked 잔존 → R7 종료(stuck 보고).

### 구성요소 / 파일

- **수정 `director/board/linear.py`** — `list_ready_issues` 쿼리에 blocker 포함. Linear
  관계 모델: X 가 Y 에 blocked ⟺ X.inverseRelations 에 `{type:"blocks", issue:Y}`. 쿼리에
  `inverseRelations(...) { nodes { type issue { id state { type } } } }` 를 추가하고,
  정규화 결과 각 ticket 에 `blockers: [{id, state_type}]` 필드를 단다(기존 필드 보존 —
  M1 테스트 호환). (정확한 Linear 관계 필드명은 라이브 pin 으로 고정 — 아래 Acceptance.)
- **수정 `director/orchestrator.py`**:
  - `eligible_tickets(ready, *, done_types=("completed",)) -> list` — ready 중 모든 blocker
    가 done_types 인 것만. 순수 함수.
  - `_dispatch_wave(board, tickets, *, command, states, ...) -> list[summary]` — 주어진
    eligible 리스트를 claim→ThreadPoolExecutor(N)→reconcile→retry-once 로 dispatch·drain
    (현 `run_once` 의 poll 이후 본문을 추출; in_flight/claim/booleans 그대로).
  - `run_once(board, ...)` — poll → `eligible_tickets` → `_dispatch_wave`. (이제 단일 패스도
    막힌 티켓을 dispatch 안 함.)
  - `run_until_drained(board, ..., *, done_types=("completed",), max_passes=50,
    max_dispatched=200) -> {"summaries", "passes", "stopped_reason", "stuck"}` — wave 루프.
    매 패스: poll→eligible(이번 패스 처음 보는 것만; 이미 처리된 id 는 results 로 제외)→
    비면 (ready 가 전부 blocked 면 stuck, 아예 없으면 drained) 종료, 아니면 `_dispatch_wave`.
    bound 초과 시 stopped_reason 로 종료.
  - CLI: `--once`(단일 패스 = 기존 run_once), 기본은 `run_until_drained`. `--max-passes`,
    `--done-types`(쉼표구분, 기본 completed). `MockBoard` 에 blocker 지원 + 패스 사이
    티켓을 추가하는 테스트 훅(워커-생성 시뮬).
- **수정 tests/test_director_orchestrator.py** — DAG 케이스(아래 Acceptance).

### 종료 / 진실 (board-as-truth)

메모리 완료 장부 없음. 매 패스 `list_ready_issues` 가 현재 ready(=미완) 티켓만 반환하므로:
완료→done 상태→다음 poll 에서 사라짐; 그 의존 티켓→blocker done→eligible. `results` dict 는
이번 런에서 이미 terminal 처리한 id 를 기억(재-poll 시 같은 티켓 재dispatch 방지 — 단,
실패해 ready 로 남는 티켓은 results 에 terminal 로 들어가 재시도 안 함; 재실행은 사람이
새 런으로). 진전 없는 패스(eligible 0·in-flight 0) → stuck 분석: ready 중 blocked 잔존이면
`stopped_reason="stuck"` + 그 티켓 목록, 없으면 `"drained"`.

### 에러 / 경계

- **blocker 읽기 실패**(관계 쿼리 에러): 그 티켓을 보수적으로 ineligible 처리 + 로그(막힌
  것으로 간주 — 잘못 dispatch 보다 안전). 다른 티켓 진행.
- **canceled blocker**: 기본 done_types=`completed` 이라 canceled blocker 는 **unblock 안
  함**(사람이 일부러 취소 → 의존 티켓 전제 불명, 사람이 판단하도록 stuck 으로 표면화).
  done_types 설정으로 변경 가능.
- **무한/폭주**: max_passes·max_dispatched bound. 초과 시 종료+reason.
- **사이클**: A↔B → 둘 다 영영 eligible 안 됨 → 진전 없는 패스 → stuck 종료(R7).
- **watched 응답**: 직전 단계와 동일 — 루프는 responder 를 소유하지 않고 공유 큐만 공유.
  긴 연속 런 동안 background `auto_respond`(테스트) 또는 별도 세션(실사용)이 답한다.

## 비목표 (Non-goals) — YAGNI

- **dev-stage taxonomy**(티켓 type→doc 워크플로) — Phase 3b.
- **streaming/max-throughput dispatch** — wave barrier 수용. 후순위 perf.
- **자율 / taste-vs-handle 정책, `linear_graphql` 가드레일** — Phase 4(여전히 watched).
- **webhook/long-poll 로 외부 변경 즉시 반영** — 루프는 re-poll. 효율화는 후순위.
- **실패 티켓 자동 재실행/복구** — 실패는 watched 로 사람에게 표면화(stuck). 크로스-프로세스
  오케스트레이터·orphan 복구는 Phase 4.
- **워커가 자식 티켓을 "언제" 만드는가**(분해 정책) — 워커 prompt/skill 의 몫, 주로 3b.
  3a 는 만들어진 티켓을 **집기만** 한다.

## 수용 기준 (Acceptance)

- **mock(deterministic, hard gate)**, FakeBoard 가 blocker 관계를 모델:
  - 체인 A→B→C: `run_until_drained` 가 A→B→C 순으로 dispatch, `stopped_reason="drained"`;
    A done 전 B 미dispatch, B done 전 C 미dispatch.
  - 다이아몬드 A→{B,C}→D: wave1 A, wave2 B·C 병렬, wave3 D.
  - 실패 blocker: A 실패 → B(blocked_by A) 영영 미dispatch → `stopped_reason="stuck"`,
    stuck=[B].
  - 사이클 A↔B → stuck 종료, 행 안 걸림.
  - 워커-생성: 첫 패스 후 새 ready 티켓 주입 → 다음 패스가 dispatch.
  - bound: max_passes 초과 → 종료+reason.
  - `run_once`(단일 패스)도 blocked 티켓 미dispatch.
- **라이브 pin(cheap, 권장)**: 실 Linear 에 throwaway 티켓 2건 + `blockedBy` 설정 →
  내 `list_ready_issues` 가 blocker+state_type 를 정확히 읽고 eligibility 가 맞는지 확인
  (MCP 교차검증), 그 뒤 정리. codex 불필요(M5a 패턴). Linear 관계 wire(`inverseRelations`
  필드명 등)를 여기서 고정.
- `python3 plugin/scripts/check.py` GREEN.

## Decision Log (부모 D-1..D-7, 오케스트레이터 D-8..D-12 이어서)

- **D-13 3a 먼저(DAG 메커닉), 3b(taxonomy) 다음.** (사람 결정, 2026-06-14.) 3b 의 typed
  티켓이 흐를 DAG 가 선행 필요 + 3a 가 "사람이 ready 큐레이션" crutch 를 retire.
- **D-14 DAG ⟹ 연속 루프.** blocked_by 존중은 re-poll 을 구조적으로 요구(완료가 의존을
  unblock). 직전 단계에서 미룬 연속 루프를 3a 가 (watched 로) 되살림.
- **D-15 wave 모델.** 패스마다 eligible wave 를 dispatch·drain 후 re-poll. barrier 로 정확,
  streaming(throughput)은 후순위. 가장 작은 정확한 DAG 실행.
- **D-16 board-as-truth.** 메모리 완료 장부 없이 board 상태가 eligibility 를 정의. 완료는
  done 상태로 ready 에서 빠짐. 워커-생성/외부변경이 공짜로 합쳐짐.
- **D-17 done_types 기본 = {completed}.** canceled blocker 는 unblock 안 하고 stuck 으로
  표면화(watched). 설정으로 변경 가능.

## 열린 질문 (Open Questions) — ExecPlan 이 확정

- Linear 관계 wire 정확형(`inverseRelations` vs `relations`, `issue` vs `relatedIssue`,
  type enum 값 `"blocks"`) — 라이브 pin 으로 고정.
- `list_ready_issues` 에 blocker 를 넣어 한 쿼리로 할지 vs 별도 `blockers_of` 배치 — 한
  쿼리 선호(round-trip 1), N+1 우려 시 ExecPlan 이 재단.
- 진전-없음 즉시 stuck 종료 vs 짧은 grace(사람이 blocker 를 done 으로 옮길 시간) — thin 은
  즉시 종료+보고(사람이 새 런). ExecPlan 확정.
