---
status: stable
last_verified: 2026-06-14
owner: harness
phase: symphony/02-orchestrator-dispatch
type: product-spec
tags: [orchestrator, dispatch, reconcile, worker]
description: A thin watched first cut of the orchestrator that polls ready tickets, dispatches several workers concurrently, and reconciles results back to the board with queue-concurrency safety.
---
# 오케스트레이터 — poll→dispatch→reconcile 루프 (thin, watched)

부모 spec: [Symphony 티켓 오케스트레이션 + 중앙 Director](2026-06-14-symphony-director-orchestration.md).
그 로드맵의 **Phase 2 후반(orchestrator)** 을 이 spec 이 책임진다. Phase 1(seam) 과
Phase 2 전반(worker tooling) 은 워커 **하나** 안의 기계를 다 지었다 — 핸드셰이크,
approval-resume seam, Linear read/write. 빠진 것은 작업을 **찾아서** 워커를 **여러 개
띄우는 루프**다. 오늘 `director/run.py::run_ticket` 은 사람이 한 번에 하나씩 손으로
부르는 일회성 호출이다. 이 spec 은 그것을 **시스템**으로 바꾸는 keystone 이다.

범위는 사람이 고른 **thin·watched 첫 컷**(2026-06-14 결정, D-8): 한 번의
poll→dispatch→reconcile 패스, bounded concurrency, 실패 시 단순 재-dispatch.
Director(=main 세션) 는 루프 동안 큐를 지키며 approval 에 답한다. 티켓 DAG 는
Phase 3, backoff/crash-recovery/lease 와 `linear_graphql` 권한 경계 가드레일은
Phase 4 로 미룬다.

## 문제 (Problem)

- 워커를 띄우는 유일한 길은 `run_ticket()` 한 번 = 티켓 하나다. 사람이 매번 ticket
  JSON 을 만들거나 `--linear <id>` 로 한 건을 지정해 손으로 실행해야 한다. board 에
  "할 일"이 쌓여 있어도 아무도 그것을 집어 워커에 배치하지 않는다.
- 두 개 이상의 워커를 동시에 돌릴 안전한 경로가 없다: `director/queue` 의
  `append_request` 는 read-before-append dedupe 가 **락이 없어**(tech-debt tracker
  line 47) 동시 append 시 라인이 깨지거나 dedupe 가 race 한다. Phase 1 은 단일 워커라
  안 물렸지만, 동시 dispatch 는 이걸 바로 깨운다.
- 워커가 끝나도 그 결과(turn completed/failed)가 board 로 **reconcile** 되지 않는다.
  사람이 board 에서 진행 상황을 볼 수 없다 — "watched" 가 성립하려면 상태가 board 에
  올라와야 한다.

관찰 가능한 부재: "Linear 의 Todo 티켓들을 한 번에 N개씩 워커에 붙이고, 끝난 것을
Done 으로 옮기고, 그 사이 approval 은 Director 가 답한다"를 돌리는 단일 명령이 없다.

## 요구사항 (Requirements)

각 항목은 사람이 독립적으로 검증할 수 있다.

- **R1 — poll.** 오케스트레이터가 board 어댑터로 한 팀의 "ready" 상태(설정 가능,
  기본 Linear "Todo") 티켓 목록을 읽어 ticket dict 리스트로 정규화한다. (검증: ready
  티켓 2건이 있는 board 에서 poll 이 정확히 그 2건을 id/identifier/state 와 함께 반환.)
- **R2 — claim(mark-before-act).** dispatch 직전 각 티켓을 "started" 상태(기본
  "In Progress")로 전이한 **뒤** 워커를 띄운다. 단일 패스 내 중복 dispatch 는 in-flight
  셋이 막고, started 전이는 (a) board 가시성(watched — 사람이 진행을 봄), (b) 크래시 시
  티켓이 started 로 남아 유실 아님(mark-before-act, RELIABILITY R9), (c) 훗날 연속 루프가
  re-poll 해도 ready 필터에서 빠짐을 보장한다. (검증: dispatch 후 board 에서 그 티켓이
  started 상태이고, 같은 패스 안에서 중복 spawn 이 일어나지 않음.)
- **R3 — bounded concurrent dispatch.** ready 티켓들을 동시성 상한 N(설정, 기본 3)으로
  워커에 배치한다. `run_ticket` 은 블로킹이므로 티켓당 한 스레드에서 실행한다.
  N 을 넘는 ready 티켓은 풀에서 N개씩 파도로 처리된다. (검증: ready 5건 + N=2 일 때
  동시에 최대 2개 워커만 살아있고 5건 모두 소진됨.)
- **R4 — 동시성 안전 큐.** N개의 동시 워커(+그 seam)가 공유 큐에 request 를 append 해도
  라인이 깨지지 않고 dedupe 가 정확하다. `append_request` 의 read-dedupe+write 를
  프로세스 내 락으로 직렬화한다(tech-debt line 47 해소). (검증: 동시에 K개의 서로 다른
  request 를 append 하면 정확히 K줄이 손상 없이 생기고, 같은 request_id 중복 전달은
  여전히 1줄.)
- **R5 — reconcile.** 워커가 끝나면 결과를 board 에 반영한다: `completed` →
  "done" 상태(기본 "Done") + 결과 코멘트, `failed`/`cancelled`/timeout → 단순 재-dispatch
  1회, 그래도 실패면 실패 코멘트(+설정 시 failed 상태, 기본은 started 상태 유지하여
  Director 가 보고 판단). (검증: 성공 티켓이 Done + 코멘트로, 실패 티켓이 1회 재시도 후
  실패 코멘트로 끝남.)
- **R6 — watched Director 디커플링.** 오케스트레이터는 responder 를 소유하지 않는다.
  공유 큐 base 만 공유하고, approval 응답은 main 세션의 `director_min`(또는 테스트의
  `auto_respond` 스레드)이 쓴다. (검증: 오케스트레이터 코드 어디에도 자동-답변 정책이
  없고, 큐를 지키는 외부 responder 없이는 approval 티켓이 R7 timeout-decline 으로만
  진행됨.)
- **R7 — 단일 명령.** `python -m director.orchestrator` 가 R1–R6 을 한 번의 패스로
  엮어 실행하고, 종료 시 처리한 티켓별 {ticket, status, final_state} 요약을 출력한다.
  `--mock` 으로 가짜 app-server 를 써 네트워크/실 codex 없이 end-to-end 가 돈다.
  (검증: mock + 2 ready 티켓에서 둘 다 Done 으로 reconcile 되고 요약이 출력됨.)

## 설계 (Design)

### 배치 / 파일

Phase 1·2 와 같은 top-level `director/` 패키지(host app-code, ARCHITECTURE invariant 7).

- **신규 `director/orchestrator.py`** — poll→dispatch→reconcile 루프.
  - `run_once(board, command, *, team, states, concurrency=3, queue_base, workspace_root, retry_budget=1, tool_executor=None, tools=None, install_skills=False) -> list[dict]`
    — 단일 패스 엔진. poll → 각 ready 티켓 claim → `ThreadPoolExecutor(max_workers=N)`
    에 dispatch → future 가 끝나는 대로 reconcile(필요 시 재제출) → 모두 소진되면
    티켓별 결과 요약 리스트 반환.
  - `dispatch(ticket, *, command, ...) -> dict` — `run_ticket` 한 번 감싸기(이미 격리
    workspace·seam·tool 라우팅을 제공). 워커 스레드가 이걸 호출.
  - `reconcile(board, ticket, result, attempts, states, retry_budget) -> dict`
    — 결과→상태 전이/코멘트, 재시도 여부 판정. 순수에 가깝게(board·인자만) 유지해
    fixture 테스트 가능(DESIGN explicit-params).
  - `main(argv=None) -> int` — CLI: `--team`, `--ready-state/--started-state/--done-state/
    --failed-state`, `--concurrency`, `--mock`, `--codex`, `--queue-dir`, `--tools`,
    `--install-skills`, `--workspace-root`. exit 0 = 모든 티켓 terminal 처리.
- **수정 `director/board/linear.py`** — Director 자신의 board **쓰기** 권한(워커의
  `linear_graphql` 와 별개; reconcile 는 워커가 죽어도 Director 가 해야 하므로 Director
  쪽 권한이 필요). 모두 기존 `urllib_post` + raw `Authorization` 키 재사용:
  - `workflow_states(team_id, *, api_key, endpoint, http_post) -> dict[str, dict]`
    — `team(id){states{nodes{id name type}}}` 로 한 번 읽어 `{name: {id, type}}` 맵.
    오케스트레이터가 시작 시 1회 호출해 상태명→id 를 해소.
  - `list_ready_issues(team_id, ready_state_id, *, ...) -> list[dict]`
    — `issues(filter:{team:{id:{eq}}, state:{id:{eq}}})` → `normalize_issue` 리스트
    (+ 현재 state id 포함).
  - `update_issue_state(issue_id, state_id, *, ...) -> bool` — `issueUpdate(id,
    input:{stateId}){success}`.
  - `comment_issue(issue_id, body, *, ...) -> bool` — `commentCreate(input:{issueId,
    body}){success}`.
- **수정 `director/queue/__init__.py`** — `append_request` 동시성 안전화: 모듈 레벨
  `threading.Lock` 으로 read-dedupe+append 를 직렬화(단일 프로세스 = 오케스트레이터 +
  워커 스레드 + seam 전부 한 프로세스이므로 락으로 충분). write 는 append 모드 단일
  `write(line+"\n")` 유지(+기존 fsync). 멀티-프로세스(여러 오케스트레이터) O_APPEND/flock
  강화는 범위 밖 — Phase 4 unwatched 에서.
- **신규 `tests/test_director_orchestrator.py`** + `tests/test_director_linear.py`·
  `tests/test_director_queue.py` 보강(동시 append). 모두 `tests/` flat, `unittest discover`.

### 상태 모델 / 설정 (states)

오케스트레이터는 네 논리 상태를 쓴다 — **ready**(poll 대상), **started**(claim 후),
**done**(성공), **failed**(옵션; 미설정 시 started 유지+코멘트). 각각 board 의 실제
workflow 상태명에 매핑되며 기본값은 Linear 표준 팀 상태("Todo"/"In Progress"/"Done").
`workflow_states` 로 이름→id 해소; 설정에 없는 이름은 startup 에서 명확한 에러로 차단
(워커를 띄우기 전에 실패). DAG/`blocked_by` 는 보지 않는다 — "ready" 진입은 사람/Director
가 큐레이션한다(watched 라 안전; DAG 자동 해소는 Phase 3).

### 핵심 behavior — `run_once`

1. `states = resolve(board.workflow_states(team), config)` — 이름→id, 1회.
2. `ready = board.list_ready_issues(team, states.ready)` (R1).
3. `pool = ThreadPoolExecutor(max_workers=N)`; `in_flight: set[id]`; `attempts: dict[id,int]`.
4. 각 ready 티켓 t: `claim(t)` = `board.update_issue_state(t, states.started)` (R2) →
   `attempts[t]=1` → `submit(dispatch, t)`. (claim 실패 시 skip + 로그; 워커 안 띄움.)
5. future 완료마다 `reconcile`:
   - `completed` → `update_issue_state(t, states.done)` + `comment_issue(t, "✅ … turn <id>")`.
   - 실패 & `attempts[t] < 1+retry_budget` → `attempts[t]+=1` → `update_issue_state(t,
     started)`(이미 started) → `submit(dispatch, t)` 재제출.
   - 실패 & 예산 소진 → `comment_issue(t, "❌ … <status> after N")` (+failed_state 설정 시 전이).
6. 모든 future 소진 → 티켓별 `{ticket, status, final_state, attempts}` 리스트 반환(R7).

### 동시성 / 격리

- **워커 격리**: `run_ticket`→`_workspace_for` 가 `workspace_root/<ticket_id>` 로 티켓당
  디렉터리를 이미 준다. 동시 워커는 서로 다른 id → 충돌 없음. (workspace 안에 repo
  체크아웃을 provisioning 하는 것은 이 spec 범위 밖 — non-goal, Phase 3+.)
- **공유 자원은 큐 하나**: 각 워커 스레드의 seam 이 같은 `director.queue` base 에 append.
  R4 락이 이걸 안전하게 만든다. `wait_for_answer` 는 락 밖에서 블로킹하므로 데드락 없음.
- **approval 팬아웃**: `director_min`/`auto_respond` 는 `read_pending`(request_id 별)으로
  모든 워커의 미답 request 를 한 번에 본다 — 다중 워커에서 그대로 동작(추가 작업 없음).

### 에러 / 경계

- **claim 실패**(board 쓰기 에러/네트워크): 그 티켓 skip + 로그, 워커 안 띄움. 다른
  티켓 진행. (티켓을 started 로 못 옮겼으면 dispatch 안 함 — 유령 워커 방지.)
- **워커 예외/서브프로세스 비정상 종료**: `dispatch` 가 예외를 잡아 `{status:"failed",
  error}` 로 변환 → reconcile 의 실패 경로(재시도/코멘트). 풀 전체를 죽이지 않음.
- **reconcile board 쓰기 실패**: 로그 + 결과에 `reconcile_error` 기록(티켓은 started 로
  남아 Director 가 board 에서 인지). 루프는 계속.
- **answer timeout**: seam 의 R7(decline) 그대로 — 오케스트레이터는 관여 안 함.
- **mock 경로**: `--mock` 은 가짜 app-server + in-memory/fake board 로 R1–R7 을 네트워크
  없이 증명. fake board 는 `list_ready_issues`/`update_issue_state`/`comment_issue` 를
  딕셔너리로 구현(테스트 픽스처).

## 비목표 (Non-goals) — YAGNI

- **티켓 DAG / `blocked_by` 해소** — Phase 3. 이 컷은 평평한 상태 필터만; "ready" 진입은
  사람/Director 가 큐레이션.
- **연속 루프 / 스케줄링** — 단일 패스만. 재-poll 무한 루프, scheduled oversee 는 Phase 4.
- **backoff·lease·crash-recovery** — 재시도는 단순 1회 재-dispatch 뿐. 지수 backoff,
  orphan("In Progress" 인데 죽은 워커) 재조정, lease/claim 토큰은 Phase 4.
- **`linear_graphql` 권한 경계 가드레일** — 워커는 여전히 무제한 Linear GraphQL.
  watched(사람이 큐를 봄)라 첫 컷은 허용; unwatched dispatch 전 가드레일은 Phase 4
  (tech-debt tracker line 49).
- **멀티-프로세스 오케스트레이터** — 단일 프로세스 + 스레드. 크로스-프로세스 큐 강화
  (O_APPEND/flock) 범위 밖.
- **workspace 에 repo provisioning**(git clone/worktree) — 티켓/Phase 3 의 몫.
- **자율 taste-vs-handle escalation** — Director 응답 정책은 Phase 4.

## 수용 기준 (Acceptance)

- **R1–R7 단위/통합(mock, deterministic — hard gate):** fake board(ready 2건) +
  `_mock_app_server`(approval 시나리오) + 붙인 `auto_respond` 로 `run_once(N=2)` 실행 →
  두 티켓 모두 board 에서 Todo→In Progress→Done 으로 전이, 둘 다 결과 코멘트, 공유
  큐에 두 approval 이 손상 없이 기록·응답. 실패 시나리오 티켓은 1회 재시도 후 실패
  코멘트. concurrency 상한이 지켜짐(동시 살아있는 워커 ≤ N).
- **R4 동시성 회귀:** K개 스레드가 동시에 서로 다른 request 를 append → 정확히 K줄,
  파싱 가능, dedupe 정상(같은 id 재전달 1줄). 락 제거 시 실패하는 테스트.
- **라이브 contract pin(권장, ExecPlan 이 결정):** 실 `codex app-server` 워커 2개를 실
  Linear 의 Todo 티켓 2건에 동시 dispatch → board 상태가 Todo→In Progress→Done 으로
  실제 이동, 결과 코멘트가 실제로 달림(MCP 로 교차 검증). Phase 1·2 의 "mock-first +
  라이브 1회로 wire 고정" 패턴 답습.
- `python3 plugin/scripts/check.py` GREEN.

## Decision Log (부모 D-1..D-7 이어서)

- **D-8 첫 컷 = thin·watched.** (사람 결정, 2026-06-14.) 단일 poll→dispatch→reconcile
  패스, bounded concurrency, 단순 재-dispatch. 근거: core-beliefs "minimum code that
  solves the problem" + 가장 작은 진짜 multi-worker 루프로 dispatch 를 end-to-end 증명.
  연속 루프/backoff/crash-recovery/가드레일은 미룸.
- **D-9 board 가 claim ledger.** dispatch 직전 started 로 전이(mark-before-act, R9).
  in-memory 셋이 아니라 board 가 진실의 원천 — Symphony 충실(트래커가 상태 기계). 크래시
  시 티켓이 "In Progress" 로 보여(유실 아님) Director 가 인지.
- **D-10 concurrency = 스레드 + 큐 락.** `run_ticket` 이 블로킹이라 `ThreadPoolExecutor`.
  동시 append 는 tech-debt line 47 을 깨우므로 `append_request` 를 프로세스 내 락으로
  직렬화(단일 프로세스라 충분). asyncio 재작성은 과함(YAGNI) — 워커는 어차피 서브프로세스.
- **D-11 reconcile 는 Director 권한.** 워커가 죽어도 결과를 board 에 써야 하므로 reconcile
  은 워커의 `linear_graphql` 가 아니라 Director 쪽 `board/linear.py` 쓰기 메서드가 한다
  (full 키). 워커 write(Phase 2)와 Director write(이 spec)는 별개 표면.
- **D-12 watched failure 기본 = 코멘트+started 유지.** 전용 "Failed" 상태는 Linear 기본
  팀에 없음. 실패 티켓을 임의로 옮기지 않고 실패 코멘트만 달고 started 에 두어 사람이
  board 에서 보고 판단(watched 의 핵심). failed 상태는 설정 시에만 전이.

## 열린 질문 (Open Questions) — ExecPlan 이 확정

- team 식별: `--team` 에 Linear team **id** 만 받을지 key 도 해소할지(어댑터 한 줄 차이).
  기본 id, key 는 ExecPlan 판단.
- `run_once` 가 재시도를 같은 패스 내 풀 재제출로 할지(현 설계) vs 패스 끝 별도 라운드로
  할지 — 전자로 가되 풀 종료 타이밍(재제출이 풀을 다시 채움) 처리를 ExecPlan 에서 확정.
- 라이브 pin 을 이 ExecPlan 에 포함할지, 별도 smoke 로 뺄지(quota) — review budget 과 함께
  ExecPlan 결정.
