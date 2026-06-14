---
status: active
last_verified: 2026-06-14
owner: harness
base_commit: fc8b3ea4adb67be74df13be941102d5bc9a9f22b
review_level: standard
---
# Director Phase 1 — worker + approval→Director→resume seam

## Goal

Phase 1 의 novel core 를 동작으로 증명한다: Python worker-client 가 codex app-server
(또는 동봉 mock)를 격리 workspace 에서 한 turn 돌리다가, 워커가 mid-turn approval/input
요청을 내면 그 요청이 Director 큐에 뜨고, main Claude 세션(Director)이 answer 를 쓰면
**같은 codex turn 이 죽지 않고 재개되어 turn/completed 로 끝난다**. "같은 turn 인가"는
approval 전후 **동일 turn id** 로 증명한다. queue·client·seam·Linear 티켓 read 가
`python3 plugin/scripts/check.py` GREEN 안의 테스트로 덮인다.

정의상 끝(observable): `python3 -m director.run --ticket <stub.json>` 가 mock 워커를
stub 티켓으로 구동 → 위험 명령 유도 지점에서 `.claude/harness/director-queue/` 에 요청
1건 → responder 가 "accept" answer → 동일 turn id 로 turn/completed. 그리고 같은 흐름이
Linear 에서 read 한 티켓으로도 통과(자격증명 있을 때).

## Context

- 설계 출처(재유도 금지, build 만): `docs/product-specs/2026-06-14-symphony-director-orchestration.md`.
  거기 Requirements R1–R7, Design(파일/contract/behavior), Decision Log(D-1..D-6),
  Acceptance 가 이 plan 의 *무엇/왜*. 이 plan 은 *어떻게* 만 소유한다.
- novel core(왜 어려운가): codex app-server 는 mid-turn 에 server→client JSON-RPC
  **요청**을 보낸다 — `item/commandExecution/requestApproval`,
  `item/fileChange/requestApproval`, `tool/requestUserInput`,
  `mcpServer/elicitation/request`. host 가 `{id, result: <decision|answers>}` 로 동기
  응답하면 server 가 `serverRequest/resolved` 알림을 내고 **같은 turn 이 이어진다**.
  Symphony Elixir 레퍼런스(/tmp/symphony-research)는 이걸 버리고 turn 을 죽인다 —
  우리는 그 자리에서 Director 로 라우팅해 재개시킨다.
- 핸드셰이크 순서(novice 가 알아야 할 사실): `initialize` → `initialized`(notif) →
  `thread/start`{model,cwd,approvalPolicy,sandbox} → `turn/start`{threadId,input[{type:
  "text",text}]} → 스트림(`turn/started`/`item/*`/`turn/completed|failed|cancelled`).
  thread id = thread/start result.thread.id, turn id = turn/start result.turn.id.
- 큐 패턴 근거: `docs/RELIABILITY.md` R1(idempotent), R4(at-least-once), R9(atomic
  mark-before-act). 경로 `.claude/harness/` 는 이미 gitignored.
- 용어: "stub 티켓" = 프롬프트+workspace 로 정의된 로컬 JSON 1건(Linear 불필요).
  "mock app-server" = SPEC §10 시퀀스를 stdout 으로 흉내내는 작은 스크립트(테스트 fixture).

## Approach (self-generated alternatives)

- A: **mock-first** — SPEC §10 + app-server 문서대로 JSON-RPC 를 내는 fake stdio
  서버를 만들어 client·seam 을 그 위에서 개발/테스트하고, 실제 `codex app-server`·
  Linear 검증은 마지막 sub-step 으로 둔다. 트레이드오프: deterministic·CI 친화적,
  단 mock 이 실제 프로토콜과 drift 가능 → thin contract-test 로 고정.
- B: **real-codex-first** — 처음부터 `codex app-server` 상대로 개발. 트레이드오프:
  최고 충실도지만 비결정적·codex CLI/auth 상시 필요·seam 을 신뢰성 있게 테스트하기 어려움.
- Chosen: **A**. seam 이 risky novel 부분이라 결정적 테스트가 필수이고, 프로토콜이
  잘 명세돼 mock 이 충실하다. 실제 codex/Linear 는 자격증명 있는 곳에서 additive 검증.
  하네스의 "internalize/boring/testable" grain 과 일치(D-1).

## Assumptions & open questions (self-interrogation)

- Assumption: `codex` CLI 는 이 환경에 있을 수도 없을 수도 있다 → M2/M4 의 real-codex
  검증은 gated, mock 경로가 1차 acceptance. 틀려도 깨지는 것 없음(mock 이 로직 커버).
- Assumption: app-server 필드 shape 는 app-server 문서 + SPEC §10 기준, 동치 shape 허용
  (SPEC compatibility profile). 틀리면 contract-test 가 잡는다.
- Assumption: Linear 워크스페이스/project 존재 + `.env` 의 `LINEAR_API_KEY` 유효 →
  M5 는 거기에 gated. 없으면 M5 는 코드+단위테스트까지 하고 live 검증만 보류(문서화).
- Open: `director/` 배치 → **해소: top-level host app-code 패키지**(ARCHITECTURE
  invariant 7 — 장기실행 서비스는 plugin 기계가 아님). 테스트는 flat
  `tests/test_director_*.py`(tests/ 는 패키지가 아니라 discover 가 수집 — dotted
  `tests.x` 호출 불가) 로 두고 check.py 의 unittest discover 로 게이트 연결.
- Open: mock 을 어디 두나 → **해소**: `director/worker/_mock_app_server.py`(테스트 fixture,
  실배포 경로 아님).
- Open: Phase 1 sandbox/approval policy 기본값 → **해소**: thread/start 는
  `approvalPolicy: "untrusted"`+`sandbox: workspaceWrite`(승인 이벤트가 실제로 나도록),
  seam 검증의 핵심이 approval 흐름이므로.

## Milestones

- **M1 — Director 큐 라이브러리.** `director/queue/` 에 append-request / read-pending /
  write-answer / read-answer 를 atomic·idempotent 로 구현(harness_lib 의 atomic write
  패턴 재사용). 끝나면 큐 스키마(spec Design 의 request/answer JSON)가 코드로 존재.
  run `python3 -m unittest discover -s tests -p 'test_director_queue.py'`; expect: 요청 1건 write→pending
  read→answer write→read 왕복 성공, 같은 request_id 중복 append 는 1건으로 dedupe.
- **M2 — codex app-server client + mock.** `director/worker/app_server.py`(spawn,
  핸드셰이크, turn 스트림 read loop) + `director/worker/_mock_app_server.py`(평범한
  turn 을 내는 fake). 끝나면 client 가 mock 을 핸드셰이크→turn/completed 까지 몰 수 있음.
  run `python3 -m unittest discover -s tests -p 'test_director_app_server.py'`; expect: thread id·turn id
  추출되고 평범한 turn 이 completed. (real-codex contract-test 는 codex 있으면 추가 실행.)
- **M3 — seam(novel core).** `director/worker/approval.py`: server-initiated 요청
  method→큐 kind 매핑, 큐에 1건 기록, answer poll(R7 timeout→decline), decision→codex
  result 변환, **같은 turn read loop 지속**. mock 이 mid-turn 에
  `item/commandExecution/requestApproval` 를 내도록 확장. 끝나면 seam 이 동작.
  run `python3 -m unittest discover -s tests -p 'test_director_seam.py'`; expect: 큐에 요청 1건 → 테스트
  responder 가 "accept" → mock 이 serverRequest/resolved+turn/completed →
  **approval 전후 turn id 동일**(assert). 이 milestone 이 Goal 의 핵심 증명.
- **M4 — main-session responder + e2e(stub).** `director/director_min.py`(미답 요청을
  읽어 answer 쓰는 최소 responder = main 세션 대행) + `director/run.py`(stub 티켓 →
  격리 workspace → worker 구동). 끝나면 stub 티켓으로 end-to-end seam 성립.
  run `python3 -m director.run --ticket tests/fixtures_director/stub.json`(mock 백엔드);
  expect: 워커 멈춤 없이 요청→answer→resume→completed, 종료코드 0, transcript 에 동일
  turn id. `python3 plugin/scripts/check.py` GREEN.
- **M5 — Linear adapter(read).** `director/board/linear.py`: `.env`(LINEAR_API_KEY)로
  GraphQL 티켓 1건 read → worker 프롬프트로 공급(adapter 인터페이스 뒤, spec RV5).
  끝나면 같은 e2e 가 Linear 티켓으로 구동(자격증명 있을 때). run `python3 -m director.run
  --linear <ISSUE-ID>`; expect: 티켓 read 되고 stub 과 동일한 seam 흐름. 자격증명 없으면
  단위테스트(모의 GraphQL 응답)까지만 + live 보류 문서화.

## Progress log

- [x] (2026-06-14) Plan created from product-spec; base_commit fc8b3ea.
- [x] (2026-06-14) M1 완료: `director/queue/`(append/read_pending/write_answer/read_answer/
  wait_for_answer — idempotent dedupe + temp→rename atomic) + `tests/test_director_queue.py`.
  증거: 5 tests OK, `check.py` GREEN(100 tests).
- [x] (2026-06-14) M2 완료: `director/worker/app_server.py`(JSON-RPC/stdio client) +
  `_mock_app_server.py`(plain+approval 시나리오) + `tests/test_director_app_server.py`.
  증거: 2 tests OK, plain turn 이 thread/turn id 추출 후 turn/completed.
- [x] (2026-06-14) M3 완료(novel core): `director/worker/approval.py` seam(method→kind,
  큐 기록, answer 대기, decision→result; R7 timeout→decline) + mock approval 시나리오 +
  `tests/test_director_seam.py`. 증거: 2 tests OK — 워커가 approval 에서 큐로 라우팅·블록,
  Director 가 accept 쓰면 **동일 turn id(turn_mock_1)** 로 resume·completed; 무응답 시
  decline 후에도 turn 완료. stop() 의 stdout ResourceWarning 도 수정. M4–M5 미착수.

## Surprises & discoveries

- mock stdin: `for line in sys.stdin` 는 pipe read-ahead 로 turn/start 를 늦게 yield →
  라이브 구동 시 교착. `sys.stdin.readline()` 루프로 교체.
- client stdout: `select` + 버퍼드 `readline` 혼용 시 readline 이 다음 줄까지 파이썬
  버퍼로 당겨와 select 가 빈 fd 로 보고 → turn/completed 누락·timeout. raw fd 를
  binary/unbuffered(os.read)로 직접 framing 해 해결. 증거: M2 2 tests 0.14s OK.

## Decision log

- 2026-06-14: mock-first(Approach A) — seam 은 결정적 테스트 필수, 프로토콜이 명세돼
  mock 충실, real codex/Linear 는 additive 검증.
- 2026-06-14: `director/` = top-level host app-code 패키지(plugin/ 아님) — invariant 7,
  장기실행 서비스는 하네스 기계가 아니라 host 앱. 테스트는 tests/director/.
- 2026-06-14: thread/start approvalPolicy=untrusted + sandbox=workspaceWrite — approval
  이벤트가 실제로 발생해야 seam 을 검증 가능.
- 2026-06-14: 테스트는 flat `tests/test_director_*.py`(tests/ 패키지 아님 → discover 수집,
  dotted 호출 불가). director/ 는 테스트에서 repo-root 를 sys.path 에 넣어 import(기존 패턴).

## Feedback (from completion gate)

## Outcomes & retrospective
