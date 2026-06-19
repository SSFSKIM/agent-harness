---
status: completed
last_verified: 2026-06-14
owner: harness
type: exec-plan
tags: [worker, tooling, linear, codex, graphql]
description: Gave Codex workers working dynamicTools so a turn can call a client-advertised linear_graphql tool to read and write Linear, routing item/tool/call to a tool_executor that returns success/output/contentItems and resumes the turn, verified in mock and against a live codex app-server.
base_commit: 74bca60c889cc8b69d29512706bbbc68f0e55f59
review_level: standard
---
# Phase 2 — worker tooling: dynamicTools + linear_graphql tool_executor

## Goal

Codex 워커가 turn 도중 client 가 광고한 도구를 호출해 실제 일을 하게 만든다. 구체적으로
`linear_graphql` 도구로 Linear 를 read/write 한다. 끝 상태(observable): mock 백엔드에서
`item/tool/call` 이 tool_executor 로 라우팅돼 `{success,output,contentItems}` 로 응답되고
turn 이 이어짐(단위테스트); 그리고 실 `codex app-server` 에서 워커가 `linear_graphql` 로
실 Linear 이슈에 코멘트를 남기고 그 코멘트가 Director 의 Linear MCP 로 확인됨(live, gated).

## Context

- 설계 출처(재유도 금지): [`docs/product-specs/2026-06-14-symphony-director-orchestration.md`](docs/product-specs/2026-06-14-symphony-director-orchestration.md)
  의 **D-7**(worker→Linear write 메커니즘) + Phase 1 산출물(`director/` 패키지, seam).
- Phase 1 이 만든 server-initiated request 채널(method+id → 응답)을 재사용한다. tool-call 은
  approval 과 **같은 채널, 다른 method**다(novel 기계 아님).
- 정본 프로토콜(Symphony elixir + `codex app-server generate-json-schema` 로 확정):
  - 광고: `thread/start` params 에 `dynamicTools: [{name, description, inputSchema}]`
    (DynamicToolSpec; required name/description/inputSchema).
  - 호출: server→client request, method `item/tool/call`, params 에서 도구명 =
    `params["tool"]`(or `"name"`), 인자 = `params["arguments"]`(기본 {}).
  - 응답: `{id, result: {success: bool, output: <str>, contentItems:
    [{type:"inputText", text: output}]}}`.
  - `linear_graphql` 스펙: name `"linear_graphql"`, inputSchema =
    object{ query:string(required), variables:object|null(optional) }.
  - `linear_graphql` 실행: Linear GraphQL POST(Phase 1 `board/linear` 의 `_urllib_post`
    + `load_api_key` + raw `Authorization` 헤더 재사용). 응답 top-level `errors` 는
    tool 호출 성공이어도 실패로 취급(success=false).
- worker 스킬: Symphony `.codex/skills`(commit/push/pull/land+land_watch.py/linear/debug,
  Apache-2.0 — /tmp/symphony-research)를 워커 workspace 의 `.codex/skills/` 에 설치해야
  Codex 가 도구·git·PR 사용법을 안다.
- 용어: "tool_executor" = `(name, arguments) -> result dict` 콜백. "dynamicTool" =
  client 가 광고하고 client 가 실행하는 도구(앱서버가 아니라 우리 쪽에서 처리).

## Approach (self-generated alternatives)

- A: **기존 AppServerClient 확장** — `thread_start(tools=[...])` 로 dynamicTools 광고 +
  `tool_executor` 콜백 인자 추가; server-request 분기에서 `item/tool/call` 은 tool_executor
  로(정규화된 {success,output,contentItems} 응답), 그 외(approval/input)는 기존 seam 으로.
  트레이드오프: 단일 client, method 로 깔끔히 분기. mock-first.
- B: **별도 ToolDispatcher 래퍼** — client 위에 도구 레이어를 얹음. 트레이드오프: 레이어
  증가; server-request 채널이 이미 client 안에 있어 불필요.
- Chosen: **A**. Phase 1 채널을 그대로 재사용, 최소 표면. (live 컨트랙트는 Phase 1 처럼
  실 codex 로 1회 확인 — schema 로 이미 확정했지만 응답 shape 를 live 로 못박는다.)

## Assumptions & open questions (self-interrogation)

- Assumption: `item/tool/call` 응답 shape 는 위 정본대로. 틀리면 live 컨트랙트 테스트가
  Phase 1 처럼 잡는다(증거 기반 수정).
- Assumption: Linear 쓰기는 사용자 워크스페이스에 실제 변경 → W4 live write 는 **outward**.
  W1–W2 는 mock/injected-http 로 자율 완결, W4 실행만 사람 확인 후.
- Open: 워커에게 줄 도구 집합 → **해소(Phase 2)**: `linear_graphql` 하나로 시작(읽기·쓰기·
  introspection 다 가능, Symphony 와 동일). git/PR 은 `.codex/skills` + codex 기본 shell.
- Open: `.codex/skills` 설치 위치 → **해소**: 템플릿을 `director/workspace_skills/` 에 vendor,
  run_ticket 가 워크스페이스 `.codex/skills/` 로 복사(idempotent). Apache-2.0 attribution 보존.
- Open: Director 의 Linear MCP vs 워커의 linear_graphql → 둘 다 유지(D-7 의 ②/③). MCP 는
  Director 대화형, linear_graphql 은 워커 turn 내. 충돌 없음.

## Milestones

- **W1 — dynamicTools 광고 + item/tool/call 라우팅.** `director/worker/app_server.py`:
  `thread_start(..., tools=None)` 가 tools 를 `dynamicTools` 로 전송; `__init__` 에
  `tool_executor: (name,args)->dict` 추가; run_turn/_handle_server_initiated 의 server-request
  분기에서 `item/tool/call` → tool_executor → `_normalize_tool_result`({success,output,
  contentItems}) → `{id,result}`; 그 외 method → 기존 seam. mock 에 "tool" 시나리오(turn 중
  `item/tool/call` 1회 발행 후 응답 받으면 complete) 추가. run
  `python3 -m unittest discover -s tests -p 'test_director_app_server.py'`; expect: 새
  테스트에서 tool_executor 가 (name,args)로 호출되고 응답 shape 정규화·turn completed.
- **W2 — linear_graphql tool_executor.** `director/worker/tools.py`: `linear_graphql_spec()`
  (name/description/inputSchema) + `make_linear_tool_executor(api_key=None, http_post=...)`
  가 name=="linear_graphql" 시 `board/linear` 로 GraphQL 실행, top-level errors→success=false,
  결과를 output(JSON 문자열)로. run `python3 -m unittest discover -s tests -p
  'test_director_tools.py'`; expect: injected http 로 성공/에러 경로 각각 {success:true/false}.
- **W3 — `.codex/skills` vendor + workspace 설치.** Symphony 스킬을
  `director/workspace_skills/`(+ NOTICE/attribution)로 복사; `director/run.py` 의
  workspace 준비에서 `.codex/skills/` 로 idempotent 설치 + `--tools linear` 시 워커에 도구
  광고. run `python3 -m director.run --ticket … --mock --tools linear`; expect: 워크스페이스에
  `.codex/skills/linear/SKILL.md` 존재, mock tool-call 라운드트립 OK.
- **W4 — live(gated).** 실 codex 워커가 `linear_graphql` 로 실 Linear 이슈에 코멘트.
  Director 의 Linear MCP 로 테스트 이슈 생성→워커 실행→코멘트 확인. run: 실 codex + 실 Linear.
  expect: 워커 turn 안에서 linear_graphql 코멘트 mutation 성공, MCP 로 코멘트 조회됨. **사람
  확인 후 실행(outward — Linear 쓰기 + codex 쿼터).**

## Progress log

- [x] (2026-06-14) Plan created; base_commit 74bca60; 프로토콜 정본 확정(D-7).
- [x] (2026-06-14) W1 완료: app_server 에 tool_executor + thread_start(tools=)→dynamicTools +
  `item/tool/call`→tool_executor 라우팅(approval seam 과 분리) + normalize_tool_result
  ({success,output,contentItems}) + mock 'tool' 시나리오. 증거: 5 app_server tests OK
  (tool-call 이 tool_executor 로 (name,args) 전달·turn completed).
- [x] (2026-06-14) W2 완료: `director/worker/tools.py` — linear_graphql_spec() +
  make_linear_tool_executor(board.linear 재사용, top-level errors→success=false, http_post
  주입) + `tests/test_director_tools.py`. 증거: 6 tests OK.
- [x] (2026-06-14) W3 완료: Symphony `.codex/skills`(commit/push/pull/land/linear/debug,
  Apache-2.0 + ATTRIBUTION)를 `director/workspace_skills/` 로 vendor + `run.py
  install_workspace_skills`(idempotent) + `--tools linear`/`--install-skills` 배선 + tests.
  증거: 5 run tests OK + CLI smoke 가 워크스페이스 `.codex/skills/` 6개 설치.
- [x] (2026-06-14) W4 LIVE PASS: ① board/linear READ live(.env 키로 LIN-5 읽음 → Phase 1
  의 gated live-Linear READ 항목도 해소, UUID 0d681179). ② 실 codex 워커가
  `linear_graphql`(commentCreate)로 LIN-5 에 코멘트 작성(tool success=true, comment id
  ade1e318) → Linear MCP 로 독립 확인(동일 코멘트) → 테스트 이슈 cancel. worker→linear_graphql
  →실 Linear write 전구간 증명. **Phase 2 = 코드 + mock + codex/Linear live 완료.**

## Surprises & discoveries

- W4 live 에서 contract 버그 0 — tool-call/dynamicTools 프로토콜을 `generate-json-schema`
  로 미리 확정한 덕(Phase 1 의 "정본 schema 먼저" 교훈 적용). 워커는 명시적 프롬프트로
  linear_graphql 1회 호출, .env 키와 OAuth Linear MCP 가 같은 lingual workspace 라 교차검증
  성립(워커가 쓴 코멘트를 MCP 가 동일 id 로 확인).

## Decision log

- 2026-06-14: tool-call 은 Phase 1 server-request 채널 재사용, method `item/tool/call` 로
  approval 과 분기(별도 tool_executor) — 새 기계 불필요.
- 2026-06-14: 도구는 `linear_graphql` 단일로 시작(Symphony 동치). git/PR 은 `.codex/skills`.

## Feedback (from completion gate)

completion gate 2026-06-14 (codex `/codex:rescue` gpt-5.5, review_level=standard):
초기 Verdict A=SATISFIED, B=NOT SATISFIED(P1) → P1 고침 후 B 충족.
- P1 run.py install_workspace_skills 가 pre-existing 심링크 target 를 따라가 워크스페이스
  밖 쓰기 가능 → **고침**: 심링크 parent 거부 + target remove-then-fresh-copy(심링크 미추종)
  + 회귀테스트 2개. 재게이트 GREEN.
- P2 normalize_tool_result 가 non-serializable output 에 raise → `json.dumps(default=str)` 고침.
- P2 `board.linear._urllib_post` → public `urllib_post` 승격(공유 Linear transport).
- P2 linear_graphql 가 .env 키로 무제한 Linear GraphQL → tech-debt-tracker 등록(권한 경계
  가드레일은 autonomous dispatch 전에).

## Outcomes & retrospective

Phase 2 달성: Codex 워커가 client-advertised 도구를 turn 중 호출해 실제 일을 한다 —
`linear_graphql` 로 실 Linear read/write. dynamicTools 광고 + `item/tool/call`→tool_executor
라우팅(approval seam 과 분리, 같은 채널) + linear_graphql executor + `.codex/skills` 설치.
mock(결정적) + live(실 codex 워커가 LIN-5 에 코멘트 작성→Linear MCP 로 교차확인) 양쪽 증명,
31 director tests, 게이트 GREEN. Phase 1 의 gated live-Linear READ 도 이 과정에서 해소.
남은 것: linear_graphql 권한 경계 가드레일(tracker), orchestrator(poll·dispatch·concurrency·
reconciliation), Phase 3+(티켓 DAG·dev-stage taxonomy·자율 Director). 교훈: 정본 schema
선확정으로 live contract 버그 0; 워크스페이스 재사용은 setup 단계 심링크 path-escape 를 부른다.
