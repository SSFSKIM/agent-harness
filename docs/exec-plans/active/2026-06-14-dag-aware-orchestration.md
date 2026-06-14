---
status: active
last_verified: 2026-06-14
owner: harness
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
- [ ] M5 — 라이브 blocker pin(실 Linear inverseRelations wire). (다음.)

## Surprises & discoveries

## Decision log
- 2026-06-14: wave(barrier) 모델 — 단순·정확, streaming 은 non-goal(perf).
- 2026-06-14: board-as-truth — 메모리 완료장부 없음, results 는 claim_failed 재시도 방지용.
- 2026-06-14: 진전-없음 즉시 stuck 종료(grace 없음) — thin, 사람이 새 런.
- 2026-06-14: done_types 기본 {completed}; canceled blocker 는 stuck 으로 표면화(D-17).

## Feedback (from completion gate)

## Outcomes & retrospective
