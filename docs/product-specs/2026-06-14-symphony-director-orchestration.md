---
status: draft
last_verified: 2026-06-14
owner: harness
---
# Symphony 티켓 오케스트레이션 + 중앙 Director

이 하네스의 다음 능력: **여러 에이전트 워커로 실제 복잡한 소프트웨어 개발을
수행**하되, 조직 구조를 고정된 에이전트 role 이 아니라 **티켓 DAG** 에 둔다.
에이전트는 모두 같은 general 한 뇌라 role 기반 조직도가 불필요하다 — 작업 단위(티켓)
자체가 institutionalization 의 수단이다. 사람은 taste 만 댄다.

OpenAI 의 [Symphony](https://github.com/openai/symphony) 사양(이슈 트래커를 코딩
에이전트 control plane 으로 바꾸는 오케스트레이터)을 **Python 으로 재구현**하고,
그 위에 vanilla Symphony 에는 없는 **중앙 Director** 를 얹는 것이 핵심 기여다.

## 비전 / Big Picture

오늘 이 하네스는 한 세션이 ExecPlan 하나를 처리하고, 사람이 막힐 때마다 개입한다.
목표 상태: 사람은 Director(Claude Code) 한 명과만 대화하고, Director 가 티켓을
발행·관리하며, 티켓마다 Codex 워커가 붙어 자율 실행하고, 워커가 사람에게 물어볼
일이 생기면 멈추는 대신 Director 가 대신 답한다. 사람에게는 **taste 판단만**
올라온다. 사람 시간/주의가 유일한 희소 자원이라는 PRODUCT_SENSE.md 의 명제를
multi-agent 규모로 끌어올린 형태다.

## 아키텍처 (수렴된 형태)

```
        ┌──────────────────────────── HUMAN ────────────────────────────┐
        │   taste only: spec 승인 · 비가역 결정 · 방향                    │
        └─────────────▲─────────────────────────────────┬───────────────┘
                escalate(taste)                       steer │
        ┌─────────────┴─────────────────────────────────▼───────────────┐
        │   DIRECTOR  (Claude Code = 사람이 대화하는 세션)               │
        │   spec/design 확정 · 티켓 발행/관리 · board oversee ·          │
        │   report · 워커 질문에 답(taste 외 전부)                       │
        └───┬──────────────────────▲──────────────────────────┬─────────┘
   티켓     │           approval/input 요청 (Q)                │ board/status
   write    │           ▲ answer (resume)                      │ read
        ┌───▼────────────┴──────────────────────────────────────▼────────┐
        │        BOARD : 티켓 + DAG(blocked_by)  — Linear (adapter 뒤)   │
        └───▲────────────────────────────────────────────────▲──────────┘
   poll/    │                                                  │ state/comment/PR
   dispatch │                                                  │ (워커 tool 로)
        ┌───┴───────────────────────────────────────────────────────────┐
        │   ORCHESTRATOR (Python, Symphony 사양): poll→DAG-eligible→     │
        │   dispatch · per-ticket isolated workspace · concurrency/retry │
        └───┬───────────────────────────────────────────────────────────┘
            │ 티켓당 1개 spawn
        ┌───▼───────────────────────────────────────────────────────────┐
        │   WORKER = codex app-server (JSON-RPC/stdio)                   │
        │   approval/input 요청 → Director 로 라우팅, turn 살아있음,     │
        │   answer 오면 같은 turn 재개 (park-and-abandon 아님)           │
        └────────────────────────────────────────────────────────────────┘
```

구성요소 책임:
- **Director** — 사람-taste 인터페이스. 워커의 비-taste 질문을 흡수하고, taste 만
  사람에게 올린다. Phase 1 에서는 큐를 읽고 답을 쓰는 최소 responder.
- **Orchestrator** — Symphony 사양의 poll/dispatch/state machine. Phase 2+.
- **Worker** — `codex app-server` 서브프로세스 1개(티켓 1개), JSON-RPC/stdio.
- **Board** — 티켓·DAG. tracker adapter 뒤(Linear 1차).
- **Seam(핵심)** — 워커의 mid-turn approval/input 요청을 Director 로 보내고 답으로
  turn 을 재개시키는 경로.

## 문제 (Problem)

Codex app-server 는 mid-turn 에 위험 명령/사용자 입력이 필요하면 server→client
JSON-RPC **요청**(`item/commandExecution/requestApproval`,
`item/fileChange/requestApproval`, `tool/requestUserInput`,
`mcpServer/elicitation/request`)을 보내고, host 가 `{id, result}` 로 동기 응답하면
**같은 turn 이 그대로 재개**된다 — "워커가 안 멈추고 누가 답해주면 계속"이 프로토콜
차원에서 이미 가능하다.

그런데 Symphony 의 Elixir 레퍼런스 구현은 이 능력을 버린다: approval 요청이 오면
`{:error, :approval_required}` 를 반환해 **turn 을 죽이고**, 티켓을 휘발성 in-memory
`blocked` 맵에 넣고 Linear 상태만 폴링한다. resume 경로도, 외부로 라우팅할 확장점도
없다 — HTTP API 는 죽은 시체만 보여준다. 따라서 Director 는 Symphony 의 HTTP 층이
아니라 **approval 핸들러(app-server client)** 에 살아야 하고, 그 자리에선 turn 이
아직 살아있다(Elixir 구현에도 답하고 `receive_loop` 로 잇는 auto-approve 경로가 이미
있어, "static 승인 → Director 호출"로 바꾸는 작은 seam 이다).

오늘 이 하네스에는 이 워커-client 도, Director seam 도, 티켓 board 도 없다.

## 요구사항 (Requirements)

비전 레벨(전체 capability — Phase 별 spec 이 상세화):

- **RV1** — 오케스트레이션 구조 = 티켓 DAG. 사람이 보는 인터페이스 = Director 한 명.
- **RV2** — 워커는 사람 입력을 기다려 멈추지 않는다. 모든 would-be-human 질문은
  Director 로 가고, Director 가 taste 만 사람에게 올린다.
- **RV3** — 워커는 `codex app-server`, Director 는 Claude Code. heterogenous 가 기본.
- **RV4** — Symphony 사양은 Python 재구현. Elixir 구현 + SPEC.md 가 contract oracle.
- **RV5** — board 는 pluggable adapter 뒤. 1차 Linear, 이후 GitHub/local 교체 가능.

Phase 1 (이 spec 이 구현 가능 수준으로 책임지는 범위 — 각 항목 사람이 검증 가능):

- **R1** — Python worker-client 가 `codex app-server` 를 격리 workspace 디렉터리에서
  서브프로세스로 띄우고 `initialize → initialized → thread/start → turn/start` 핸드셰
  이크를 완료한다. thread/start 는 `model`, `cwd`(절대경로 = workspace), `approvalPolicy`,
  `sandbox` 를 보낸다. (검증: 핸드셰이크 후 thread id·turn id 가 로그에 찍힌다.)
- **R2** — worker-client 가 turn 스트림을 읽어 `turn/completed`(성공)/`turn/failed`·
  `turn/cancelled`·timeout(실패)까지 진행한다. (검증: 평범한 티켓이 turn/completed 로 끝남.)
- **R3 (핵심)** — server→client approval/input 요청(위 4종)이 오면 worker-client 는
  turn 을 죽이지 않고 그 요청을 Director 큐에 1건 기록한 뒤 answer 를 기다린다.
  answer 가 오면 codex 에 `{id, result}` 로 응답하고 **같은 turn 이 재개**된다.
  (검증: 위험 명령을 유도하는 티켓에서, 큐에 요청이 뜨고, Director 가 "accept" 를
  쓰면, approval 이전과 **동일한 turn id** 가 이어져 turn/completed 로 끝남.)
- **R4** — Director answer 채널은 하네스 기존 at-least-once JSONL 큐 패턴(RELIABILITY
  R1–R11) 위에 선다: append-only 요청 파일 + request_id 별 atomic answer 파일
  (mark-before-act, R9). (검증: 요청/응답 파일이 스키마대로 생기고, 중복 처리 안 됨.)
- **R5** — Phase 1 Director 는 큐를 읽어 답을 쓰는 최소 responder(Claude Code 세션 또는
  단순 응답기). taste-vs-handle 정책·자율 oversee 는 Phase 4. (검증: Director 가 answer
  를 써서 R3 가 성립.)
- **R6** — seam 은 tracker 와 직교한다. Phase 1 은 **stub 티켓**(프롬프트+workspace 로
  정의된 1건)으로 R1–R5 를 먼저 증명하고, 그 다음 Linear 어댑터로 같은 티켓을 읽어온다.
  (검증: Linear 없이 stub 으로 end-to-end 통과 → 이후 Linear 로 동일 통과.)
- **R7** — answer 미수신 timeout 시 안전 기본동작(decline)으로 turn 을 진행하고
  로그를 남긴다(무한 대기 금지). (검증: 답 없이 timeout 시 decline 후 turn 종료.)

## 설계 (Design) — Phase 1

**배치.** 장기 실행 서비스는 layer law(scripts→skills→agents→hooks) 의 plugin 기계가
아니라 ARCHITECTURE invariant 7 의 "host app-code" 에 가깝다. 따라서 Phase 1 코드는
신규 top-level Python 패키지 **`director/`** 에 둔다(plugin/ 아님). Director 의 사람-
facing 제어는 후속 Phase 에서 plugin/ 의 skill/agent 로 표면화한다. (배치는 열린 질문
— ExecPlan 이 확정.)

**구성요소/파일(Phase 1).**
- `director/worker/app_server.py` — codex app-server JSON-RPC/stdio client. 서브프로세스
  spawn, 핸드셰이크, turn 스트림 read loop, server-initiated 요청 디스패치.
- `director/worker/approval.py` — approval/input 요청 → 큐 기록 → answer 대기 → codex
  응답 구성. method↔kind 매핑과 decision↔result 매핑을 소유.
- `director/queue/` — JSONL 요청 파일 + answer 파일 I/O(하네스 `harness_lib` 의 atomic
  write/parse 패턴 재사용; 경로는 `.claude/harness/director-queue/`).
- `director/director_min.py` — Phase 1 최소 responder: 미답 요청을 읽어 answer 를 쓴다.
- 테스트는 `tests/` 또는 `.harness.json` test_cmd 로 게이트에 연결.

**Contract — codex app-server (oracle: /tmp/symphony-research, SPEC.md §10 + app-server 문서).**
요청→응답 매핑:
- `item/commandExecution/requestApproval` → `{id, result: "accept"|"decline"|"acceptForSession"|"cancel"}`
- `item/fileChange/requestApproval` → 동일 decision 집합
- `tool/requestUserInput` → `{id, result: <answers>}` (questions 에 대한 답)
- `mcpServer/elicitation/request` → elicitation 스키마대로 result
응답 후 `serverRequest/resolved` 알림 → `item/completed` → 최종 `turn/completed` 를 같은
포트/thread/turn 에서 계속 읽는다.

**Contract — Director 큐(스키마).**
- 요청(append-only JSONL): `{request_id, ticket_id, session_id("<thread>-<turn>"),
  kind, payload(command|changes|questions|elicitation), workspace_path, created_at}`
- answer(`answers/<request_id>.json`, atomic): `{request_id, decision|answers,
  answered_by("director"|"human"), answered_at}`

**핵심 behavior(R3).** read loop 가 server-initiated 요청 method 를 만나면: (1) kind 로
정규화해 큐에 1건 append, (2) `answers/<request_id>.json` 이 생길 때까지 poll(R7 timeout),
(3) decision/answers → codex result 로 변환해 `{id, result}` 송신, (4) 같은 turn 의 read
loop 지속. turn 은 절대 죽이지 않는다.

**에러/경계 케이스.** 서브프로세스 비정상 종료 → 실패로 turn 종료(park 아님, 로그).
answer timeout → decline(R7). 큐 중복 entry → request_id dedupe(R4). codex auth 실패 →
preflight 로 startup 차단(명확한 에러). app-server 필드명 버전차 → 논리적 동치 shape
허용(SPEC §10 의 compatibility profile).

## Phase 로드맵 (2–5; 각자 자기 spec→plan)

- **Phase 2 — Worker tooling(우선, D-7) → Orchestrator.** 먼저 워커가 티켓을 끝까지
  해내도록: client 가 `dynamicTools` 로 `linear_graphql` 광고 + `item/tool/call` →
  tool_executor 라우팅(worker→Linear write), Symphony `.codex/skills` 를 workspace 에 설치.
  그 다음 orchestrator(poll·dispatch·per-ticket workspace·concurrency·retry·reconciliation,
  다중 워커) — 자기 spec: [orchestrator-dispatch-loop](2026-06-14-orchestrator-dispatch-loop.md)
  (thin·watched 첫 컷).
- **Phase 3 — 티켓 DAG + dev-stage taxonomy.** `blocked_by`, 에이전트 self-created 티켓,
  그리고 planning→high/low design→research-needed→spec→impl 단계를 **티켓 type** 에
  매핑(각 type 이 docs/product-specs·docs/exec-plans 등 하네스 doc 를 산출).
- **Phase 4 — 자율 Director.** loop/scheduled oversee, board 리포팅, taste-vs-handle
  escalation 정책, PR 머지 관리.
- **Phase 5 (optional) — 공유 tracker.** GitHub Issues 어댑터 + observability surface.

## 비목표 (Non-goals)

- 고정 role 기반 에이전트 조직(HIERARCHY.md/AGENT_REGISTRY.md 식 self-institutionalization).
  조직 구조는 티켓 DAG 가 소유한다(RV1).
- OpenAI Elixir Symphony 를 그대로 실행/포크(Python 재구현으로 결정 — RV4).
- Phase 1 에서 concurrency/DAG/orchestrator 루프(전부 Phase 2+).
- Phase 1 에서 자율 Director 정책·taste 분류(Phase 4).
- Director seam 을 Symphony HTTP API 위에 얹기(죽은 blocked 만 보여 resume 불가).

## 수용 기준 (Acceptance) — Phase 1

- worker-client 가 stub 티켓에서 codex app-server 핸드셰이크→turn/completed 통과(R1·R2).
- 위험 명령 유도 티켓에서: 큐에 approval 요청 1건 출현 → Director responder 가 "accept"
  answer 기록 → **approval 전후 동일 turn id** 가 이어져 turn/completed. 즉 워커가
  멈춰 죽지 않고 답으로 재개됨이 transcript 로 증명(R3 — 이 capability 의 novel core).
- answer 채널이 스키마대로 동작하고 중복/timeout 이 R4·R7 대로 처리됨.
- 같은 시나리오가 stub 티켓으로, 그 다음 Linear 에서 읽어온 티켓으로 동일하게 통과(R6).
- `python3 plugin/scripts/check.py` GREEN.

## Decision Log (수렴 결정 + 근거)

- **D-1 Python 재구현.** Elixir 포크 대신 사양을 Python 으로. 하네스 stack 일치 +
  "의존 내장/boring tech"(core-beliefs) + Director seam 을 처음부터 native 설계. 근거:
  Elixir 런타임/수정 역량 부담, app-server contract 는 plain JSON-RPC 라 Python 용이.
- **D-2 Director seam = approval 핸들러.** Symphony HTTP 층 불가(resume 불가). codex
  프로토콜이 동기 응답으로 turn 재개를 이미 지원.
- **D-3 board = Linear, adapter 뒤.** Symphony 레퍼런스에 최근접. 단 외부 SaaS/API 키
  의존은 "의존 내장" grain 의 **의도적 예외**(문서화). seam 은 tracker 와 직교라 Phase 1
  은 stub 우선(R6).
- **D-4 Director=Claude / worker=Codex.** thread/start `model` + apiKey/ChatGPT 로그인 +
  workspaceWrite sandbox 로 heterogenous 가 first-class.
- **D-5 Director invocation = main 세션.** Director 는 별도 daemon/loop 가 아니라 사람이
  대화하는 그 Claude Code 세션 자체다. Phase 1 의 큐 responder = 이 main 세션이 미답
  요청을 읽어 answer 를 쓴다(taste 만 사람에게). (사람 결정, 2026-06-14.)
- **D-6 LINEAR_API_KEY = `.env`.** 키는 repo 루트 `.env`(gitignored)에서 읽는다. 커밋
  금지 — `.gitignore` 에 `.env` 추가로 누출 차단. (사람 결정, 2026-06-14.)
- **D-7 worker→Linear write 경로(Symphony 소스로 확정).** 세 Linear 표면: ① Director READ
  (Phase 1 `board/linear.py`), ② Director=Claude 세션의 Linear MCP(대화형 board 관리),
  ③ **worker WRITE** — client 가 `thread/start` 에 `dynamicTools:[{name,description,
  inputSchema}]` 로 `linear_graphql` 광고하고, Codex 의 `item/tool/call`(params `tool`/
  `arguments`)을 **tool_executor** 로 라우팅해 `{success,output,contentItems:[{type:
  "inputText",text}]}` 반환(approval seam 과 같은 server-request 메커니즘, 다른 채널). 워커는
  Symphony `.codex/skills`(commit/push/pull/land/linear/debug, Apache-2.0)로 git·PR·Linear
  사용법을 안다 — workspace 에 설치. reprioritization(사람, 2026-06-14): 이 worker tooling 을
  orchestrator 보다 먼저(단일 워커가 티켓을 read→work→write→commit/PR 끝까지 증명).

## 열린 질문 (Open Questions)

- ~~Director invocation 모델~~ → **해소: main 세션**(D-5).
- ~~`LINEAR_API_KEY` secret 취급~~ → **해소: `.env`(gitignored)**(D-6).
- taste-vs-handle 경계의 구체적 정책(무엇을 사람에게 올리나). (Phase 4.)
- `director/` 배치 확정: host app-code 로 top-level 이 맞는지, 게이트/테스트 연결 방식.
  (Phase 1 ExecPlan 에서 확정.)
