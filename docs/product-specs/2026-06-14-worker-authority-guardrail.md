---
status: stable
last_verified: 2026-06-14
owner: harness
---
# Worker authority guardrail — bounding `linear_graphql`

Phase 4 (자율 Director) 의 **첫 슬라이스 + 하드 선행조건**. 부모 spec:
[Symphony 티켓 오케스트레이션 + 중앙 Director](2026-06-14-symphony-director-orchestration.md)
(로드맵 Phase 4). tech-debt-tracker line 49 가 "autonomous(un-watched) dispatch
이전에 반드시" 라고 표시한 worker authority boundary 를 구현한다.

## Problem (오늘 무엇이 불만족인가 — observable)

워커(`codex app-server`)는 turn 중에 `linear_graphql` dynamic tool 로 **임의의
Linear GraphQL 문서**를 사람의 `.env` 키 권한으로 실행할 수 있다
(`director/worker/tools.py` `make_linear_tool_executor` → `execute` 가 query 문자열을
그대로 Linear endpoint 로 POST). 권한 경계가 **전혀 없다** — `issueDelete`,
`issueArchive`, `commentDelete`, bulk `issueBatchUpdate` 같은 **비가역/파괴적
mutation 도 그대로 통과**한다.

오늘은 dispatch 가 *watched*(사람이 오케스트레이터를 지켜봄)라 용인된다. 그러나
Phase 4 의 본질은 Director 를 *unwatched* 자율 운영으로 전환하는 것이고, 그 순간
버그가 있거나 transcript-injection(SECURITY.md T1 계열) 으로 오염된 워커가 사람의 키로
보드를 파괴할 수 있다. PRODUCT_SENSE.md 의 escalation rule — "irreversible/
outward-facing actions 는 경계가 필요" — 이 정확히 이 표면을 가리킨다. 관찰 가능한
불만족: **지금 워커가 `mutation { issueDelete(id:"…") }` 를 호출하면 보드의 이슈가
실제로 삭제된다. 이를 막는 코드가 repo 에 없다.**

## Requirements (R1..R8 — 각 항목 사람이 검증 가능)

- **R1 — 읽기는 항상 통과.** 모든 GraphQL `query` operation(익명 selection set 포함,
  introspection `__type`/`__schema` 포함)은 guardrail 을 변형 없이 통과해 Linear 로
  나간다. (검증: `query { issues { nodes { id } } }` tool call 이 여전히 data 를 반환.)
- **R2 — mutation 은 allowlist 로 게이트.** `mutation` operation 은 그 **top-level
  root field 가 전부** 설정된 allowlist 에 속할 때만 통과한다. (검증:
  `mutation { issueUpdate(…) }` 통과; `mutation { issueDelete(…) }` 거부.)
- **R3 — default-deny + 명확한 거부, 실제 호출 차단.** allowlist 밖 mutation root
  field(삭제/아카이브/미지)을 하나라도 가진 문서는 거부된다: executor 가
  `{success: False, output: "<막힌 field 를 명시한 사유>"}` 를 반환하고 **Linear 로 POST
  하지 않는다**. turn 은 죽지 않는다 — 워커가 거부를 보고 스스로 적응한다. (검증: 거부된
  호출이 success=False + field 이름을 담고, `http_post` 가 한 번도 불리지 않음.)
- **R4 — 견고한 분류(서버 parser 와 정렬).** 분류기는 alias(`x: issueDelete`),
  주석(`# mutation …`), 문자열 리터럴 안의 키워드/중괄호, 선행 공백, query 본문 안의
  `mutation` 단어에 속지 않는다 — comment/string 을 제거한 뒤(=GraphQL lexer 가 무시하는
  것과 동일) operation type 과 진짜 root field 이름을 뽑는다. (검증: evasion 배터리가
  전부 올바르게 분류·인가됨.)
- **R5 — subscription / 다중 operation / 파싱 불가 → 거부(fail-closed).** "read 거나
  allowlisted-mutation 문서"로 확신 있게 환원되지 않는 모든 입력은 거부한다. subscription
  거부. 한 문서에 여러 operation 이 있으면 root field 의 **합집합**으로 게이트(하나라도
  비-allowlist 면 거부). 파싱 불가 → 사유와 함께 거부. (검증: subscription·malformed 문서
  거부.)
- **R6 — allowlist 는 구성 가능, 기본값은 안전한 최소집합.** 기본 allowlist 는 워커의
  설치된 `.codex/skills` + 3b worker-driven 분해가 **실제로 쓰는** mutation 만 담은 named
  상수이고, executor 생성 시 override 가능하다. (검증: 기본 집합이 문서화된 집합과 일치;
  커스텀 집합을 넘기면 동작이 바뀐다.)
- **R7 — 두 dispatch 지점 모두에 기본 적용.** `make_linear_tool_executor` 가 guardrail 을
  **기본 on** 으로 적용하므로 `director/run.py` 와 `director/orchestrator.py` 가 추가 변경
  없이 guarded executor 를 받는다. caller 는 명시적으로만 opt-out 한다. (검증: run.py/
  orchestrator.py 가 만든 executor 가 delete 를 거부.)
- **R8 — 위협 모델에 기록.** SECURITY.md 가 worker-tool-authority 위협(T10)을 얻고, 이
  슬라이스의 완료 게이트가 review-security(live exec surface) 를 돈다. (검증: SECURITY.md
  에 T10 이 있고 live-surface 목록에 포함됨.)

## Design

### 경계의 위치와 형태

guardrail 은 **worker tool executor 안**에 산다 — 워커가 Linear 로 나가는 유일한
경로(`item/tool/call` → `_run_tool` → `tool_executor`)의 마지막 게이트. 새 채널·새 블로킹
경로를 만들지 않는다. 거부는 이미 존재하는 *failed-tool-call* 계약(빈 query·HTTP 에러
브랜치와 동일한 `{success: False, output}` shape)을 그대로 재사용하므로 turn 을 죽이지
않고 워커에게 피드백된다.

### 구성요소 / 파일

**신규 `director/worker/authority.py` — 순수 분류 + 인가(네트워크·상태 없음).**
- `classify_operation(query: str) -> Operation`
  `Operation = {"kind": "query"|"mutation"|"subscription"|"unknown", "root_fields": tuple[str, ...], "parse_ok": bool}`.
  최소 GraphQL lexer 로 구현: ① 라인 주석(`#`→EOL)과 문자열 리터럴(`"…"`, `"""…"""`)을
  공백으로 치환(중괄호·키워드가 그 안에 있어도 무시), ② 첫 유의 토큰으로 operation type
  결정(`query`/`mutation`/`subscription` 키워드, 또는 선행 `{` → 익명 query), ③ `mutation`
  이면 그 selection set 의 깊이-1 field 이름 수집(`alias:` 스킵, `(…)` 인자 스킵), ④ 문서에
  operation 이 여럿이면 mutation 들의 root field 합집합. 파싱이 확신 없으면 `parse_ok=False`.
- `DEFAULT_MUTATION_ALLOWLIST: frozenset[str]` — 안전한 forward-only 집합(아래 D-27).
- `authorize(query: str, *, allow_mutations: frozenset[str]) -> Authorization`
  `Authorization = {"allowed": bool, "reason": str}`. 로직:
  - `classify_operation` 호출.
  - `parse_ok` False → deny("could not parse GraphQL operation").
  - kind == subscription → deny("subscriptions are not permitted").
  - kind in {query} (또는 익명 read) → allow.
  - kind == mutation: `root_fields` 비어있음 → deny(fail-closed, "no mutation field
    parsed"); 전부 `allow_mutations` 에 속함 → allow; 아니면 deny(위반 field 이름 명시).
  - kind == unknown → deny(fail-closed).

**수정 `director/worker/tools.py` — executor 에 guardrail 결선.**
- `make_linear_tool_executor(api_key=None, endpoint=…, http_post=…,
  allow_mutations: frozenset[str] | None = None, guard: bool = True)`.
  `execute` 안에서 query 문자열 검증 직후(아직 `http_post` 호출 전):
  `if guard: auth = authority.authorize(query, allow_mutations=allow_mutations or
  authority.DEFAULT_MUTATION_ALLOWLIST); if not auth["allowed"]: return {"success":
  False, "output": auth["reason"]}`. 그 외 경로는 불변.
- `guard=True` 가 기본(secure-by-default). `guard=False` 는 명시적 opt-out(예: 신뢰된
  관리 작업)만을 위한 escape hatch.

**수정 `docs/SECURITY.md` — 위협 T10 추가.**
- **T10 — Worker tool authority.** 워커는 `linear_graphql` 로 사람의 `.env` 키 권한의
  Linear 쓰기에 접근한다(live exec surface). 경계: mutation root-field allowlist
  (default-deny); reads 무제한(파괴적이지 않음, 그리고 query operation 은 서버에서 mutation
  field 를 실행하지 못함). un-watched dispatch 의 선행조건. status 노트의 live-surface
  목록(T3·T8·T9)에 T10 추가.

**테스트 `tests/test_director_authority.py`(신규) + `tests/test_director_tools.py`(보강).**
- authority: classify/authorize 단위표 + evasion 배터리(alias, 주석, 문자열, 익명-query-
  속-mutation-field, subscription, 다중 operation, 빈/malformed).
- tools: guarded executor 가 allowed mutation 은 POST 하고(주입된 fake `http_post` 가 불림),
  거부된 mutation 은 POST 하지 않음(fake 가 **불리지 않음**)을 증명. 기본 allowlist 회귀.

### 계약 (분류기 ↔ 서버의 정렬 — 보안 논거의 핵심)

Linear 는 operation 키워드가 문자 그대로 `mutation` 일 때만 mutation field 를 실행한다.
따라서 `query { issueDelete }` 처럼 mutation field 를 query 로 부르거나, `mutation` 을
주석/문자열 뒤에 숨긴 문서는 **서버가 read 로 파싱**하여 어떤 mutation 도 실행하지 않는다.
분류기는 서버와 **같은 문서**를 본다(comment/string 제거 = GraphQL lexer 가 무시하는 것).
그러므로 guardrail 은 "분류기가 mutation operation 을 정확히 식별하고 그 root field 를
정확히 뽑는다"만 보장하면 쓰기 경계로 충분하다 — 적을 outsmart 할 필요가 없고, 서버 parse
와의 정렬이 건전성을 준다.

### 에러 / 경계 케이스

- 빈/공백 query → 기존 검증("requires a non-empty 'query'")이 먼저 처리(guardrail 이전).
- 거부 시 `http_post` 절대 호출 안 함(R3) — 네트워크 부작용 없음, 순수 로컬 판정.
- guardrail 예외(분류기 버그)는 turn 을 죽이지 않는다: `_run_tool` 의 기존 try/except 가
  tool 예외를 failed-tool-call 로 흡수한다(app_server.py). 단 분류기는 fail-closed 원칙상
  내부적으로도 확신 없으면 deny 를 반환하도록 작성.
- argument 수준 파괴(예: 가상의 trashing-via-issueUpdate)는 **이 경계가 잡지 않는다**
  — 게이트 granularity 는 mutation root-field **이름**이다(아래 Non-goals).

## Non-goals (scope fence — YAGNI)

- **Argument-level policy.** mutation 인자 검사(허용된 mutation 이 파괴적 인자를 갖는
  경우)는 범위 밖. 경계는 root-field 이름 단위 — Linear 가 별도 mutation 으로 노출하는
  파괴 operation(delete/archive/batch)을 전부 덮는다.
- **Escalate-to-Director.** 거부된 mutation 을 Director 큐로 승인 요청하는 라우팅은 **하지
  않는다** — default-deny 로 standalone 안전. 그 라우팅은 다음 슬라이스(taste-vs-handle
  escalation policy)의 일이고, `authorize` 의 `reason` 이 그 seam 이다.
- **Raw `linear_graphql` 계약 교체.** per-mutation 구조화 tool 로 바꾸지 않는다(D-25).
  Symphony/D-7/RV4 충실 — 경계는 앞단 분류기지 계약 변경이 아니다.
- **Per-ticket / per-worker 동적 scope**(이 워커는 자기 이슈만), rate limit / quota,
  read-side field 제한 — 전부 후속 정제.
- **Director 자신의 Linear MCP / Director READ adapter(`board/linear.py`) 제한** — 그건
  사람/Director 권한이지 워커 권한이 아니다. scope 는 worker tool executor 한정.

## Acceptance criteria (spec 만족의 demonstrable 조건)

- `query { issues { nodes { id } } }` 가 guarded executor 를 통과해 fake `http_post` 가
  불리고 success=True (R1).
- `mutation { issueUpdate(id:"x", input:{stateId:"s"}) { success } }` 통과·POST 됨 (R2/R6).
- `mutation { issueDelete(id:"x") { success } }` 가 success=False + "issueDelete" 를 담아
  반환하고 fake `http_post` 가 **불리지 않음** (R3).
- evasion 배터리(alias·주석·문자열·익명-query-mutation-field·subscription·다중 operation·
  malformed) 가 전부 기대대로 분류·인가 (R4/R5).
- `make_linear_tool_executor()`(기본값)로 만든 executor 가 delete 를 거부; run.py·
  orchestrator.py 결선이 같은 executor 를 사용 (R7).
- 기본 allowlist == {issueCreate, issueUpdate, commentCreate, commentUpdate,
  issueRelationCreate, attachmentLinkURL, attachmentLinkGitHubPR, fileUpload} (R6/D-27).
- SECURITY.md 에 T10 존재 + live-surface 목록 포함 (R8).
- **Live wire-pin(최소 1회):** 실제 Linear 의 throwaway 티켓에 guarded executor 로
  `commentCreate`(allowlisted) 가 성공 → 경계가 정당한 작업을 깨지 않음을 증명. deny 경로는
  순수 로컬(네트워크 없음)이라 mock 으로 완전 커버 — 실데이터 삭제는 하지 않는다.
- `python3 plugin/scripts/check.py` GREEN.

## Decision Log (수렴 결정 + 근거)

- **D-23 경계 granularity = mutation root-field allowlist, default-deny; reads 항상 통과.**
  query operation 은 서버에서 mutation field 를 실행할 수 없으므로 mutation operation 의
  root field 게이트가 완전한 쓰기 경계다. 근거: 서버 parse 와 정렬되는 가장 단순한 경계,
  Linear 가 별도 mutation 으로 노출하는 모든 파괴 op 를 덮음.
- **D-24 default-deny, escalate-to-Director 아님(이 슬라이스).** guardrail 은 escalation
  policy 이전에 standalone 으로 출하되어야 안전 — 비-allowlist mutation 은 워커가 행동할 수
  있는 명확한 사유와 함께 거부. escalate-to-Director 는 다음 슬라이스로 연기(seam = reason).
  근거: 경계는 단독으로 안전해야; YAGNI.
- **D-25 raw `linear_graphql` 계약 유지.** 구조화 per-mutation tool 로 대체하지 않음 —
  Symphony/D-7/RV4 충실, 워커 설치 skill 이 이미 raw GraphQL 사용. 경계는 앞단 분류기.
- **D-26 분류기 = repo 내 최소 GraphQL lexer**(comment/string 제거 → operation type →
  root fields), 의존성·취약 regex 아님. alias/comment/string evasion 에 견고하고 서버
  parser 와 정렬. stdlib-only(boring-tech / T3 stdlib grain 일치).
- **D-27 기본 allowlist = 워커가 실제로 쓰는 mutation 집합.** issueCreate, issueUpdate,
  commentCreate, commentUpdate, issueRelationCreate, attachmentLinkURL,
  attachmentLinkGitHubPR, fileUpload. 출처: `director/workspace_skills/linear` SKILL +
  land/commit SKILL + 3b 분해 템플릿. executor 생성 시 override 가능. 근거: 실제 워커 행동에서
  도출 → 경계가 정당한 작업을 절대 깨지 않음; tight default.
- **D-28 guard 기본 on(`make_linear_tool_executor`).** run.py·orchestrator.py 가 변경 없이
  상속; caller 는 명시적으로만 opt-out. 근거: secure-by-default — opt-in 을 잊을 수 없게.
- **D-29 SECURITY.md T10 추가 + 완료 게이트 review-security.** worker authority 는 live exec
  surface(사람 키로 outward-facing mutation). 근거: live surface 만 security review(AGENTS.md
  §5 / SECURITY.md status 노트).

## Open Questions

- escalate-to-Director 경로의 정확한 형태(어떤 거부를 Director 승인으로 올리나)는 다음
  슬라이스(taste-vs-handle escalation policy)에서 확정. 이 spec 은 default-deny 로 닫는다.
- per-worker 동적 scope(워커가 자기 티켓 외 mutation 금지)는 Phase 4 후반 정제 후보 —
  지금은 전역 allowlist 로 충분(YAGNI).
