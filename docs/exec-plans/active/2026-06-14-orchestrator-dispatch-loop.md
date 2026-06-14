---
status: active
last_verified: 2026-06-14
owner: harness
base_commit: ef5c0e641abf4bd7fdcb9bbae6f4975aecfe31a4
review_level: standard
---
# Orchestrator — poll→dispatch→reconcile 루프 (thin, watched)

## Goal

`python -m director.orchestrator --mock --team <t>` 한 명령이, board 의 "ready" 티켓을
poll 해서 동시성 상한 N 으로 워커에 배치하고, 각 워커가 끝나는 대로 결과를 board 로
reconcile(성공→Done+코멘트, 실패→1회 재시도→실패 코멘트)하며, 그 사이 approval 요청은
공유 큐를 통해 Director(또는 테스트의 auto_respond)가 답해 turn 이 재개되도록 한다.
**관찰 가능한 done**: fake board(ready 2건) + `_mock_app_server`(approval) + 붙인
`auto_respond` 로 `run_once(N=2)` 를 돌리면 두 티켓이 board 에서 Todo→In Progress→Done
으로 전이하고 각각 결과 코멘트가 달리며, 공유 큐의 두 approval 이 손상 없이 기록·응답
되고, 동시 살아있는 워커가 N 을 넘지 않는다. `python3 plugin/scripts/check.py` GREEN.

## Context

- 부모 product-spec(이 plan 이 build 하는 design 의 소유자, 재유도 금지):
  `docs/product-specs/2026-06-14-orchestrator-dispatch-loop.md` — R1–R7, 컴포넌트/파일,
  상태 모델, `run_once` behavior, 에러 경계, D-8..D-12.
- 비전/로드맵 부모: `docs/product-specs/2026-06-14-symphony-director-orchestration.md`.
- 빌드 위에 얹는 기존 코드:
  - `director/run.py::run_ticket(ticket, *, command, queue_base, workspace_root,
    timeout_s, read_timeout_s, tools, tool_executor, install_skills) -> {status, turn_id}`
    — 블로킹, 워커 1개=티켓 1개, `_workspace_for` 가 `workspace_root/<id>` 격리.
  - `director/board/linear.py` — `read_issue`, `normalize_issue`, `load_api_key`,
    `urllib_post`(raw `Authorization` 키), `DEFAULT_ENDPOINT`. 여기에 **쓰기** 메서드 추가.
  - `director/queue/__init__.py::append_request` — read-before-append dedupe, **락 없음**
    (tech-debt-tracker line 47: "Phase 2 가 동시성 추가하면 강화"). 이 plan 이 그 순간.
  - `director/director_min.py::auto_respond(base, decide, stop)` / `pending`/`answer`
    — watched responder; `read_pending` 가 request_id 별로 모든 워커 미답을 한 번에 봄.
  - `director/worker/_mock_app_server.py` — scenarios `plain`/`approval`/`tool`/`turn_error`.
- 용어: **ready/started/done/failed** = 오케스트레이터의 4 논리 상태(spec 상태 모델);
  Linear workflow 상태명에 매핑(기본 Todo/In Progress/Done). **claim** = dispatch 직전
  started 로 전이(mark-before-act). **reconcile** = 워커 결과를 board 상태/코멘트로 반영.

## Approach (self-generated alternatives)

동시성 모델:
- A: **ThreadPoolExecutor + 프로세스 내 큐 락.** `run_ticket` 이 블로킹 read-loop 이라
  티켓당 스레드. 동시 append 는 모듈 `threading.Lock` 으로 직렬화. tradeoff: 스레드/락
  추론 필요하나 stdlib·최소 변경, 워커는 어차피 서브프로세스라 GIL 무관.
- B: asyncio 재작성(app_server 를 async 로). tradeoff: 더 큰 재작성, app_server 의 동기
  select read-loop 를 async 로 바꿔야 함 — YAGNI, 이득 없음(병목은 서브프로세스).
- C: 멀티프로세스(워커당 프로세스). tradeoff: 큐를 O_APPEND/flock 로 크로스-프로세스
  강화해야 함 — Phase 4 범위, 지금은 과함.
- **Chosen: A** — spec D-10. 가장 작은 진짜 multi-worker 루프, 단일 프로세스라 락으로 충분.

claim/dedup:
- A: **board-as-claim-ledger**(dispatch 직전 started 전이) + in-flight 셋. tradeoff: board
  쓰기 1회 추가; 크래시 시 티켓이 started 로 보여 유실 아님. spec D-9.
- B: in-flight 셋만. tradeoff: board 가시성 없음(watched 실패), 크래시 시 흔적 없음.
- **Chosen: A** — watched 의 핵심이 board 가시성.

reconcile 주체:
- A: **Director 쪽 `board/linear.py` 쓰기**(full 키). tradeoff: 워커 `linear_graphql` 와
  중복 표면이나, 워커가 죽어도 Director 가 결과를 써야 함. spec D-11.
- B: 워커가 self-reconcile. tradeoff: 크래시한 워커는 자기 실패를 못 알림 — 불가.
- **Chosen: A**.

## Assumptions & open questions (self-interrogation)

- Assumption: 한 오케스트레이터 프로세스만 돈다(단일 프로세스). 틀리면 큐 락이 부족
  (크로스-프로세스엔 O_APPEND/flock 필요) — 그 경우는 Phase 4 non-goal 로 명시됨.
- Assumption: Linear 기본 팀 상태명 Todo/In Progress/Done 이 존재. 없으면 startup 의
  `workflow_states` 해소가 명확한 에러로 차단(워커 안 띄움). 상태명은 CLI 로 override.
- Assumption: `run_ticket` 을 여러 스레드에서 동시 호출해도 안전 — 각 호출이 자기
  AppServerClient(자기 서브프로세스·stdin/stdout)+자기 seam(ticket_id namespaced
  request_id)을 만들고, 유일 공유 자원인 큐 append 만 R4 락으로 보호. (M3 에서 동시
  2워커로 실증.)
- Open: team 식별을 id 만 받을지 key 도 → **id 만**(가장 단순; key 해소는 YAGNI).
  CLI `--team` = Linear team id. 기록: Decision log.
- Open: 재시도를 같은 패스 내 풀 재제출로 → **그렇게**. `run_once` 가 완료 future 를
  소비하며 실패+예산 남으면 풀에 재제출, in-flight/pending future 셋이 빌 때까지 루프.
- Open: 라이브 pin(M5)을 이 plan 에 포함 → 포함하되 throwaway 티켓 2건 생성·검증·정리,
  quota 부담 시 1건으로 축소 가능(M5 가 자기 안에서 판단). mock(M1–M4)이 hard gate.

## Milestones

- **M1 — board 쓰기/조회 메서드 + fake board.** `director/board/linear.py` 에
  `workflow_states(team_id, *, api_key, endpoint, http_post) -> {name:{id,type}}`,
  `list_ready_issues(team_id, ready_state_id, *, ...) -> [ticket dict(+state_id)]`,
  `update_issue_state(issue_id, state_id, *, ...) -> bool`,
  `comment_issue(issue_id, body, *, ...) -> bool` 추가(모두 `urllib_post`+raw 키 재사용,
  http_post 주입 가능). 테스트용 `FakeBoard`(딕셔너리 상태/코멘트)를
  `tests/test_director_orchestrator.py` 에 둔다. **끝에 존재**: Director 가 board 상태를
  읽고/옮기고/코멘트하는 4 메서드 + 그 단위테스트. **run**: `python3 -m pytest -q
  tests/test_director_linear.py`(혹은 unittest). **acceptance**: 주입한 fake http_post
  로 각 메서드가 올바른 GraphQL(쿼리·변수)을 만들고 응답을 정규화함; top-level `errors`
  → False/raise 규약.
- **M2 — 동시성 안전 큐 append.** `director/queue/__init__.py::append_request` 의
  read-dedupe+write 를 모듈 `threading.Lock` 으로 감싼다(`wait_for_answer`/`read_*` 는
  락 밖 — 데드락 없음). **끝에 존재**: K개 스레드 동시 append → 정확히 K줄·무손상·dedupe
  정상을 증명하는 회귀테스트(`tests/test_director_queue.py`). **run**: `python3 -m unittest
  -q tests.test_director_queue`. **acceptance**: 새 테스트가 락 없이는 실패(레이스),
  락으로 통과. tech-debt-tracker line 47 을 `fixed`(이 커밋 SHA)로 갱신.
- **M3 — 오케스트레이터 엔진.** 신규 `director/orchestrator.py`:
  `run_once(board, command, *, team, states, concurrency=3, queue_base, workspace_root,
  retry_budget=1, tools, tool_executor, install_skills) -> [result dict]`,
  `dispatch(ticket, *, command, ...) -> dict`(run_ticket 감싸기, 예외→{status:failed}),
  `reconcile(board, ticket, result, attempts, states, retry_budget) -> dict`. claim→
  ThreadPoolExecutor(N)→완료 future 소비·reconcile·재제출 로직. **끝에 존재**: mock
  end-to-end. **run**: `python3 -m unittest -q tests.test_director_orchestrator`.
  **acceptance**: FakeBoard(ready 2) + `_mock_app_server approval` + `auto_respond` 로
  `run_once(N=2)` → 두 티켓 Todo→In Progress→Done + 코멘트, 큐의 두 approval 무손상 기록·
  응답; 동시 워커 ≤ N(세마포어/풀로 관측); `turn_error` 시나리오 티켓은 1회 재시도 후
  실패 코멘트, started 유지.
- **M4 — CLI + 요약.** `director/orchestrator.py::main(argv)`: `--team`, `--ready-state`/
  `--started-state`/`--done-state`/`--failed-state`(기본 Todo/In Progress/Done/없음),
  `--concurrency`(기본 3), `--mock`, `--codex`, `--queue-dir`, `--tools`, `--install-skills`,
  `--workspace-root`. board 를 real `linear` 또는 `--mock` 시 FakeBoard 로 선택. 종료 시
  티켓별 `{ticket, status, final_state, attempts}` JSON 줄 출력, exit 0 = 전부 terminal.
  **run**: `python3 -m director.orchestrator --mock --team T --queue-dir <tmp>`(테스트가
  fake board 주입 경로를 검증). **acceptance**: 요약이 ready 티켓 수만큼 출력되고 exit 0.
- **M5 — 라이브 contract pin(quota 판단).** 실 `codex app-server` 워커 2개를 실 Linear 의
  throwaway Todo 티켓 2건에 `run_once(N=2)` 로 동시 dispatch. **끝에 존재**: board 상태가
  실제 Todo→In Progress→Done, 결과 코멘트 실재(MCP 로 교차검증), 그 뒤 티켓 정리(취소).
  **run**: 실 키(.env) + `python -m director.orchestrator --team <real>`(소수 티켓). 
  **acceptance**: 두 티켓 상태가 실제 이동·코멘트; transcript 로 동시 dispatch 증명. quota
  부담 시 1 티켓으로 축소. (Phase 1·2 의 mock-first + 라이브 1회 패턴.)

## Progress log
- [x] (2026-06-14) plan 작성 + 생성시 self-review.
- [x] (2026-06-14) M1 — board/linear.py 에 `_post` 헬퍼 + `workflow_states`/
  `list_ready_issues`/`update_issue_state`/`comment_issue` + `LinearBoard` 어댑터;
  read_issue 를 `_post` 로 리팩터. test_director_linear.py +6 테스트(11 통과).
- [x] (2026-06-14) M2 — queue `append_request` 를 모듈 `_APPEND_LOCK` 으로 직렬화;
  동시성 회귀테스트 2건(distinct 40→무손상, same-id 40→1). 락 무력화 시 60 동시 same-id
  가 4줄로 깨짐을 확인해 테스트 유효성 입증. tech-debt line 47 → fixed.
- [x] (2026-06-14) M3 — `director/orchestrator.py`: `resolve_states`, `dispatch`,
  `reconcile`, `run_once`(claim→ThreadPoolExecutor(N)→FIRST_COMPLETED 소비→retry-once),
  + in-memory `MockBoard`. test_director_orchestrator.py 11 테스트: e2e(실 mock 워커 2 +
  watched auto_respond → Todo→In Progress→Done, 큐 2 approval 무손상 응답), concurrency
  cap(≤N), retry-once, failed-state, claim_failed, reconcile_error.
- [x] (2026-06-14) M4 — `main(argv, board=None)` CLI(--team/--*-state/--concurrency/
  --mock/--codex/--queue-dir/--workspace-root/--tools/--install-skills) + 요약 출력.
  `python -m director.orchestrator --mock` 가 데모 보드 2 티켓을 end-to-end 처리, exit 0.
- [x] (2026-06-14) M5a — board GraphQL 라이브 pin. 실 Linear(team "Lingu")에서 내 board
  메서드 4종 검증: `workflow_states` 가 MCP `list_issue_statuses` 와 7개 상태·id·type
  정확히 일치; throwaway LIN-6(Todo) 생성 → `list_ready_issues` 가 LIN-6 을 올바른
  state_id 로 반환 → `update_issue_state`(Todo→In Progress) success → `comment_issue`
  success. MCP get_issue/list_comments 로 독립 교차검증(stateHistory Todo→In Progress,
  코멘트 실재). 첫 시도에 wire 정확(라이브 버그 0). LIN-6 정리(Canceled).
- [~] M5b — 실 codex 2-워커 동시 dispatch 라이브 런: **옵션/연기**. 핵심 리스크(루프·
  concurrency·reconcile)는 실 mock 워커 e2e 로 이미 증명, board wire 는 M5a 로 고정.
  순수 codex-app-server 계약은 Phase 1·2 라이브에서 이미 고정. 남은 미검증분은 "실
  codex 가 dynamicTools/approval 을 물고 board 로 reconcile 되는 다중 동시" 통합뿐 —
  quota 대비 한계효용이 낮아 사용자 요청 시 실행. (사람 판단 대상.)

## Surprises & discoveries
- (2026-06-14) M2 락 검증: `_APPEND_LOCK` 을 `nullcontext` 로 무력화하면 60 동시
  same-id append 가 4줄(중복)로 남음 → read-before-append race 가 실재하고 락이 정확히
  그걸 닫음. 음성 테스트를 flaky 하게 박제하는 대신 양성 테스트 + 이 1회 수동 확인으로 남김.
- (2026-06-14) M5a 발견: team "Lingu" 의 Todo 에 실제 티켓 5건 존재 → 만약 `--team` 으로
  실 codex 런을 돌리면 ready=5 를 전부 dispatch 한다. 첫 실런은 반드시 소수/큐레이션된
  ready 셋으로 해야 함(watched). orchestrator 가 ready 전체를 집는다는 점이 실 데이터에서
  체감됨 — DAG/필터 큐레이션(Phase 3) 전까지 "ready 진입은 사람이 관리"가 안전판.

## Decision log
- 2026-06-14: 동시성=ThreadPoolExecutor+큐 락(A) — run_ticket 블로킹, 단일 프로세스.
- 2026-06-14: `--team` = Linear team id 만(key 해소 YAGNI).
- 2026-06-14: 재시도 = 같은 패스 내 풀 재제출(별도 라운드 아님).
- 2026-06-14: reconcile 는 Director 쪽 board 쓰기(워커 죽어도 결과 기록) — spec D-11.

## Feedback (from completion gate)

## Outcomes & retrospective
