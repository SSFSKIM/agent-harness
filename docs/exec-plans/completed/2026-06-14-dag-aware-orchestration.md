---
status: completed
last_verified: 2026-06-14
owner: harness
type: exec-plan
tags: [orchestrator, dag, dispatch, director]
description: Made the orchestrator re-poll until the ticket DAG is drained, dispatching only tickets that are ready and whose blocked_by blockers are all done, so a chained A→B→C run dispatches in dependency order and ends with stopped_reason "drained".
base_commit: 64ab600a5dceb2d0501889d7406938444991357d
review_level: standard
---
# DAG-aware 연속 오케스트레이션 (Phase 3a)

## Goal

`python -m director.orchestrator --team <t> --mock` 가 (단일 패스 대신) DAG 가 소진될
때까지 re-poll 하며, ready **그리고** 모든 blocked_by blocker 가 done 인 티켓만 dispatch
한다. **관찰 가능한 done**: FakeBoard 에 체인 A→B→C(B blocked_by A, C blocked_by B)를
넣고 `run_until_drained` 를 돌리면 A→B→C 순으로(각 blocker 가 done 된 뒤에만) dispatch
되고 `stopped_reason="drained"` 로 끝나며, A 가 done 되기 전 B 는 한 번도 dispatch 되지
않는다. 실패 blocker·사이클은 `stopped_reason="stuck"` 으로 행 안 걸리고 종료. `python3
plugin/scripts/check.py` GREEN.

## Context

- product-spec(이 plan 이 build 하는 design 소유자, 재유도 금지):
  `docs/product-specs/2026-06-14-dag-aware-orchestration.md` — R1–R7, wave 모델,
  board-as-truth, eligibility, 에러/경계, D-13..D-17.
- 선행 build(이 위에 얹음):
  `docs/exec-plans/completed/2026-06-14-orchestrator-dispatch-loop.md` +
  `director/orchestrator.py`(`run_once`/`dispatch`/`reconcile`/`MockBoard`/`resolve_states`),
  `director/board/linear.py`(`list_ready_issues`/`update_issue_state`/`comment_issue`/
  `_post`/`LinearBoard`).
- 용어: **eligible** = ready 상태 ∧ 모든 blocker 가 done-type. **wave** = 한 패스에서
  dispatch·drain 하는 eligible 셋. **board-as-truth** = 완료=done 상태→ready 에서 빠짐,
  메모리 완료장부 없음. **stuck** = eligible 0 ∧ in-flight 0 이지만 ready-but-blocked 잔존.
- Linear 관계 모델: X blocked_by Y ⟺ X.inverseRelations 에 `{type:"blocks", issue:Y}`
  (정확 wire 는 M5 라이브로 고정).

## Approach (self-generated alternatives)

연속 루프 구조:
- A: **wave(barrier).** 매 패스 poll→eligible→그 wave 를 다 drain→re-poll. tradeoff:
  빠른 티켓이 느린 형제를 기다림(throughput↓)이나 가장 단순·명백히 정확, run_once 본문
  재사용. **Chosen** (spec D-15).
- B: **streaming.** 단일 풀에 완료마다 새 eligible 주입. tradeoff: 최대 throughput 이나
  poll 과 FIRST_COMPLETED 소비를 interleave — 복잡. YAGNI(perf 후순위).

blocker 읽기:
- A: **list_ready_issues 한 쿼리에 inverseRelations 포함**(티켓당 blockers 필드). tradeoff:
  쿼리 1회·N+1 없음. **Chosen**.
- B: 별도 `blockers_of` 배치. tradeoff: round-trip 추가. 불필요.

eligibility 진실원:
- A: **board-as-truth**(완료→done 상태→ready 제외). tradeoff: 매 패스 poll 비용이나
  메모리 장부 불필요, 외부/워커 변경 공짜 반영. **Chosen** (D-16).
- B: 메모리 DAG + 완료 추적. tradeoff: 외부 변경과 drift, 더 많은 상태. 불필요.

## Assumptions & open questions (self-interrogation)

- Assumption: 한 패스가 그 wave 를 전부 drain 한 뒤 re-poll(barrier) → 패스 간 in-flight
  중복 없음. 틀리면 streaming 으로 가야 하나, 그건 명시적 non-goal.
- Assumption: 실패/claim_failed 티켓은 ready 아닌 상태로 남거나 results 에 들어가 재-poll
  시 재dispatch 안 됨. claim_failed 는 ready 로 남으므로 **results dedup 필수**(이게 없으면
  claim 실패 티켓을 무한 재시도). → 매 패스 `pending = ready - results.keys()`.
- Assumption: MockBoard 가 blocker 의 현재 state_type 을 다른 이슈 상태에서 계산 가능
  (issue.blockers=[id...], list_ready_issues 가 각 blocker 의 현 state_type 부여).
- Open: 진전-없음 → 즉시 stuck 종료 vs grace 대기 → **즉시 종료+보고**(thin; 사람이 새 런).
  기록: Decision log.
- Open: done_types 기본 {completed} (canceled 는 unblock 안 함). 기록됨(D-17).
- Open: stuck 분석에서 "ready-but-blocked" 와 "ready-but-claim_failed" 구분 — 후자는
  results 에 있어 pending 에서 빠지므로 stuck 후보 아님(drained 로 종료, 요약에 claim_failed
  포함). ExecPlan M3 에서 stopped_reason 분류 확정.

## Milestones

- **M1 — board blocker 읽기 + MockBoard 관계.** `director/board/linear.py`:
  `list_ready_issues` 쿼리에 `inverseRelations`(type blocks) 추가, 정규화 결과 각 ticket 에
  `blockers: [{id, state_type}]` 부여(기존 필드 보존). `MockBoard` 가 issue 의 선택적
  `blockers:[id...]` 를 받아 list_ready_issues 에서 각 blocker 의 현 state_type 을 채움.
  **끝에 존재**: board 가 ready 티켓을 blocker+state_type 와 함께 반환. **run**: `python3
  tests/test_director_linear.py`. **acceptance**: 주입 fake http_post 로 쿼리에
  inverseRelations 가 들어가고 blockers 가 정규화됨; MockBoard 가 blocker state_type 계산.
- **M2 — eligibility + wave 추출.** `director/orchestrator.py`: `eligible_tickets(tickets,
  *, done_types=("completed",))` 순수 필터; `run_once` 의 poll 이후 본문을 `_dispatch_wave(
  board, tickets, *, ...) -> dict[tid, summary]` 로 추출; `run_once` = poll→`eligible_tickets`
  →`_dispatch_wave`→`list(values())`. **끝에 존재**: 단일 패스도 blocked 티켓 미dispatch.
  **run**: `python3 tests/test_director_orchestrator.py`. **acceptance**: `eligible_tickets`
  단위테스트(blocker done/미done/canceled); run_once 가 B(blocked_by A 미done) 미dispatch.
- **M3 — `run_until_drained` 연속 루프.** wave 루프: 매 패스 poll→`pending=ready-results`→
  `eligible`→비면 (pending 에 blocked 잔존 stuck / 아니면 drained) 종료, 아니면
  `_dispatch_wave` 후 results 병합; max_passes·max_dispatched bound. 반환
  `{summaries, passes, stopped_reason, stuck}`. **끝에 존재**: DAG end-to-end.
  **run**: `python3 tests/test_director_orchestrator.py`. **acceptance**: 체인 A→B→C(순서·
  drained), 다이아몬드 A→{B,C}→D, 실패-blocker→stuck=[B], 사이클 A↔B→stuck(행 없음),
  워커-생성(첫 패스 후 주입 티켓 dispatch), bound 초과→stopped_reason.
- **M4 — CLI.** `main` 에 `--once`(단일 run_once), 기본 `run_until_drained`; `--max-passes`,
  `--done-types`(쉼표). 종료 요약에 stopped_reason/passes 출력. **run**: `python3 -m
  director.orchestrator --team T --mock --queue-dir <tmp> --workspace-root <tmp>`.
  **acceptance**: 연속 모드가 데모 보드를 drained 로 끝내고 exit 0; `--once` 는 단일 패스.
- **M5 — 라이브 blocker pin(cheap, no codex).** 실 Linear(Lingu)에 throwaway 2건 + B 를 A 에
  `blockedBy` 설정 → 내 `list_ready_issues` 가 B 의 blockers=[{A, A state_type}] 를 정확히
  읽는지 + eligibility(A 미done→B ineligible) 확인, MCP 교차검증, 정리. **끝에 존재**: Linear
  관계 wire(`inverseRelations`/`issue`/type 값) 고정. **run**: `.env` 키 + 검증 스크립트.
  **acceptance**: B 의 blocker 가 A 로 읽히고 A 를 done 으로 옮기면 B 가 eligible.

## Progress log
- [x] (2026-06-14) plan 작성 + 생성시 self-review.
- [x] (2026-06-14) M1 — board/linear.py `list_ready_issues` 쿼리에 inverseRelations +
  `_parse_blockers`(type=="blocks" 만, blocker id+state_type); MockBoard 가 issue.blockers
  를 받아 state_type 해소. test_director_linear +1(12 통과).
- [x] (2026-06-14) M2 — `eligible_tickets`(순수 필터) + `_dispatch_wave`(run_once 본문
  추출, dict 반환) + 얇은 `run_once`(poll→eligible→wave). 단일 패스도 blocked 미dispatch.
  test +7(eligibility 6 + run_once-skip-blocked).
- [x] (2026-06-14) M3 — `run_until_drained` 연속 wave 루프(pending=ready-results, eligible
  없으면 stuck/drained, bound). test +6: 체인 순서·drained, 다이아몬드 병렬, 실패-blocker
  →stuck=[B], 사이클→stuck(행 없음), 워커-생성 픽업, max_passes bound.
- [x] (2026-06-14) M4 — CLI `--once`/`--max-passes`/`--done-types`, 기본 연속.
  test +2(--once 단일 패스 B 막힘, 연속 체인 A→B 둘 다 Done). 164 테스트 GREEN.
- [x] (2026-06-14) M5 — 라이브 blocker pin. 실 Linear(Lingu)에 throwaway LIN-7(A)·
  LIN-8(B blocked_by A) 생성 → 내 `list_ready_issues` 가 B.blockers=[{A uuid, "unstarted"}]
  를 정확히 파싱(inverseRelations type=="blocks" wire 확인), A=Todo 동안 `eligible_tickets`
  가 A 만 eligible·B 미eligible → 내 `update_issue_state`(A→Done) 후 재읽기에서 B.blocker
  가 "completed" 로 바뀌고 B eligible. 첫 시도에 wire 정확(라이브 버그 0). LIN-7·8 정리(Canceled).

## Surprises & discoveries
- (2026-06-14) M5 라이브: Linear `inverseRelations` + IssueRelationType `"blocks"` 추정이
  첫 시도에 맞음(B.inverseRelations 의 `issue` 가 blocker A). schema-first 누적 효과 —
  Phase 1·2·orchestrator 에 이어 라이브 wire 버그 0.

## Decision log
- 2026-06-14: wave(barrier) 모델 — 단순·정확, streaming 은 non-goal(perf).
- 2026-06-14: board-as-truth — 메모리 완료장부 없음, results 는 claim_failed 재시도 방지용.
- 2026-06-14: 진전-없음 즉시 stuck 종료(grace 없음) — thin, 사람이 새 런.
- 2026-06-14: done_types 기본 {completed}; canceled blocker 는 stuck 으로 표면화(D-17).

## Feedback (from completion gate)

- review_level standard. codex auth 불가(로그아웃) → CLAUDE.md 폴백으로 Claude 리뷰어
  2 lens. **reliability lens: SATISFIED**(무한루프·busy-spin 없음 전 경로 trace, stuck/cycle
  정확, wave barrier `pool.shutdown(wait=True)` finally·누수 없음, results-dedup, board-는-
  main-스레드 불변식 모두 확인). **arch lens: NEEDS-WORK** → 수정:
  - **P1-E** — stuck 보고가 진단 없음(특히 blocker state_type=None 이면 왜 막혔는지 불명).
    **수정**: stuck 이 각 pending 티켓을 unmet blockers `[{id, state_type}]` 와 함께 보고
    (None/실패/사이클 blocker 가 보임). spec 에러-경계 진단 요구 충족.
  - **P2-B** — `dispatched_count += len(wave)` 가 claim_failed 를 dispatch 로 셈 →
    max_dispatched 조기 발동. **수정**: status != claim_failed 만 카운트.
  - **reliability P2** — 루프 내 bare `list_ready_issues` 가 일시적 poll 에러에 전체
    런을 크래시. **수정**: catch → `stopped_reason="poll_failed"` + `error` 필드, 크래시
    없이 종료.
  - **P2-F** — max_dispatched CLI 미노출. **수정**: `--max-dispatched` 추가·전달.
- 수정 커밋 996a923 + 테스트 2건(poll-failure, max_dispatched bound) + stuck 테스트 2건
  shape 갱신. 확인 리뷰(Claude): 4건 전부 CLOSED, regression 없음, 종료 보장 유지.
  **Verdict: SATISFIED.**
- tracker 기록(accepted tradeoff): inverseRelations no-filter over-fetch(P2-E), poll
  broad-except(의도적). linear_graphql 권한 경계(P4)는 기존 line 49 유지.

## Outcomes & retrospective

- **무엇이 생겼나.** 오케스트레이터가 DAG-aware·연속이 됐다: `eligible_tickets`(blocked_by
  필터), `_dispatch_wave`(wave 추출), `run_until_drained`(re-poll wave 루프 — board-as-truth,
  stuck/cycle 검출, poll-failure·max_passes·max_dispatched bound), board `inverseRelations`
  blocker 읽기, CLI `--once`/`--max-passes`/`--max-dispatched`/`--done-types`. 166 테스트
  GREEN(+18). A→B→C 를 넣으면 blocker 가 풀릴 때마다 자동으로 다음을 dispatch 하고,
  사이클/실패는 행 안 걸리고 stuck 으로 보고한다 — "사람이 ready 큐레이션" crutch 가 사라졌다.
- **라이브.** M5 로 Linear `inverseRelations` wire + eligibility 전이를 실 Linear 에서 핀
  (LIN-7/8), MCP 교차검증, 첫 시도 정확(라이브 버그 0 — schema-first 누적).
- **핵심 배움 1 — DAG 는 연속 루프를 강제한다.** blocked_by 존중 = re-poll 필요(완료가
  의존을 unblock). 직전 단계에서 "watched 라" 미룬 연속 루프가 여기서 필연으로 돌아왔다.
- **핵심 배움 2 — board-as-truth 가 설계를 접는다.** 메모리 완료장부 없이 board 상태가
  eligibility 를 정의 → 워커-생성/외부변경/실패가 전부 같은 메커니즘으로 처리. 종료도
  공짜(완료=ready 이탈, 실패=non-done→의존 stuck).
- **핵심 배움 3 — 진단은 기능이다.** 리뷰가 "stuck 인데 왜 막혔는지 없음"을 짚었다.
  watched 시스템에서 "왜"가 없으면 사람이 개입을 못 한다 → stuck 이 unmet blockers 를
  보고하도록. 관찰가능성도 요구사항이다.
- **남은 것.** Phase 3b(dev-stage taxonomy — typed 티켓이 이 DAG 를 흐름, `eligible_tickets`
  순수 함수에 type 라우팅 한 겹); Phase 4(자율 Director + linear_graphql 가드레일);
  streaming dispatch(throughput, non-goal); inverseRelations over-fetch(tracker).
