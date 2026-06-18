---
status: completed
last_verified: 2026-06-14
owner: harness
type: exec-plan
tags: [worker, security, linear, guardrail]
description: Stopped the worker's linear_graphql tool from running arbitrary destructive Linear mutations by gating the default executor so issueDelete is rejected without any HTTP call while issueUpdate and queries still POST to Linear, recorded as threat T10 in SECURITY.md.
base_commit: 9464e4d3d47e2d0ed1ea3064cfbbc55f6844c209
review_level: targeted
---
# Worker authority guardrail — build

## Goal
워커의 `linear_graphql` tool 이 더 이상 임의 파괴적 Linear mutation 을 실행하지 못한다.
관찰 가능한 done: `make_linear_tool_executor()` 로 만든(기본) executor 에
`mutation { issueDelete(id:"x") { success } }` 를 주면 `{"success": false, "output":
"…issueDelete…"}` 를 반환하고 주입된 `http_post` 가 **한 번도 불리지 않으며**, 같은
executor 가 `mutation { issueUpdate(…) }` 와 `query { issues {…} }` 는 그대로 Linear 로
POST 한다. SECURITY.md 가 T10 을 갖고, 실제 Linear throwaway 티켓에 guarded executor 로
`commentCreate` 가 성공한다. `python3 plugin/scripts/check.py` GREEN.

## Context
- Spec(설계 소유, 재유도 금지): `docs/product-specs/2026-06-14-worker-authority-guardrail.md`
  — Problem, R1–R8, Design(구성요소·계약·에러), Non-goals, Acceptance, D-23..D-29.
- 부모: `docs/product-specs/2026-06-14-symphony-director-orchestration.md`(Phase 4).
- 선행조건 출처: `docs/exec-plans/tech-debt-tracker.md` line 49(un-watched 전 worker authority
  boundary 필요).
- 현 코드:
  - `director/worker/tools.py` — `linear_graphql_spec()` advertise + `make_linear_tool_executor`
    → `execute(name, arguments)` 가 query 를 그대로 POST(경계 없음). **여기에 guardrail 결선.**
  - `director/worker/app_server.py` — `_run_tool` 이 tool 예외를 failed-tool-call 로 흡수
    (turn 안 죽음); 거부도 같은 `{success, output}` shape 로 반환되어 워커에 피드백.
  - 결선 지점: `director/run.py:121`, `director/orchestrator.py:388` 둘 다
    `make_linear_tool_executor()` 호출(인자 없음) → guard 기본 on 이면 둘 다 자동 상속.
  - 워커가 실제 쓰는 mutation 출처: `director/workspace_skills/linear/SKILL.md`
    (commentCreate/commentUpdate/issueUpdate/attachmentLinkURL/attachmentLinkGitHubPR/
    fileUpload), 3b 분해 템플릿(issueCreate/issueRelationCreate).
- 용어: **root field** = mutation operation selection set 의 깊이-1 field(실제 호출되는
  mutation, 예 `issueDelete`); alias(`x: issueDelete`)의 `x` 가 아니라 `issueDelete`.
  **default-deny** = allowlist 에 없으면 거부. **fail-closed** = 확신 없으면 거부.

## Approach (self-generated alternatives)
- A: **앞단 분류기 + executor 결선**(spec 채택). 최소 GraphQL lexer 로 operation type·root
   field 를 뽑아 allowlist 게이트. raw `linear_graphql` 계약 유지. — 작고, Symphony 충실,
   서버 parse 와 정렬.
- B: raw GraphQL 폐기, per-mutation 구조화 tool(linear_create_issue 등) enum. — 경계가
   파싱 불요로 단순하나 D-7/RV4 위반, 워커 설치 skill 재교육 필요, 큰 변경.
- C: 워커에게 read-only 키 + 별도 write 경로. — Linear 단일 키 모델과 안 맞고 .env 운영 변경,
   범위 과대.
- **Chosen: A** — 최소 변경으로 완전한 쓰기 경계, 계약·oracle 충실, stdlib-only. (D-25/D-26.)

## Assumptions & open questions (self-interrogation)
- Assumption: Linear 는 operation 키워드가 `mutation` 일 때만 mutation field 를 실행한다
  (query operation 의 mutation field 는 서버 validation 에러) → 분류기가 서버 parse 와
  같은 문서를 보면 mutation operation 게이트로 충분. 틀리면(서버가 query 로 mutation 실행)
  read-pass 가 우회구멍이 됨 — M3 live 에서 `query { issueDelete }` 가 서버에서 거부됨을
  부수 확인(파괴 없이: 존재하지 않는 id 로). [GraphQL 사양상 참; 보강 확인만.]
- Assumption: 워커 mutation 수요 = D-27 의 8개로 충분(현재 설치 skill + 3b 분해 기준).
  새 수요는 allowlist 한 줄 추가로 fix-forward.
- Open: escalate-to-Director 라우팅 → 이 plan 범위 아님(default-deny 로 닫음, 다음 슬라이스).
  spec Non-goals 확정 — 재논의 없음.
- Open: argument-level 파괴(trashing-via-update) → 범위 밖(spec Non-goals); root-field 단위.

## Milestones

- **M1 — 분류기 + 인가(순수, 단위 검증).** `director/worker/authority.py` 신규:
  `classify_operation`, `DEFAULT_MUTATION_ALLOWLIST`, `authorize`. 최소 lexer 가 주석/문자열
  제거 → operation type → mutation root fields(alias·인자 스킵, 다중 operation 합집합) 추출.
  `authorize` 가 read→allow, allowlisted-mutation→allow, 그 외/subscription/parse-fail/
  unknown→deny(fail-closed, 사유에 위반 field). 끝에 존재: `tests/test_director_authority.py`
  — classify/authorize 단위표 + evasion 배터리(alias, `# mutation` 주석, 문자열 안
  `"mutation"`/`}`, 익명 `{ issueDelete }`(=query→allow, 서버가 막음), subscription, 다중
  operation, 빈/malformed). run: `python3 -m pytest tests/test_director_authority.py -q`
  (또는 `python3 plugin/scripts/check.py`). expect: 전부 PASS, delete-mutation→deny,
  issueUpdate-mutation→allow.
- **M2 — executor 결선 + 위협 모델.** `director/worker/tools.py` `make_linear_tool_executor`
  에 `allow_mutations: frozenset[str] | None = None, guard: bool = True` 추가; `execute`
  안 query 검증 직후·`http_post` 전에 `authority.authorize` 호출, deny 면 `{success: False,
  output: reason}` 즉시 반환(POST 없음). `docs/SECURITY.md` 에 **T10 — Worker tool authority**
  추가 + status 노트 live-surface 목록(T3·T8·T9)에 T10. 끝에 존재: guarded executor 가
  delete 를 POST 없이 거부, allowed mutation·read 는 POST. `tests/test_director_tools.py`
  보강 — fake `http_post` 가 deny 시 **불리지 않음**, allow 시 불림; 기본 allowlist 회귀;
  `guard=False` opt-out; run.py/orchestrator.py 결선이 delete 거부(import 해 executor 생성).
  run: `python3 plugin/scripts/check.py`. expect: GREEN, 신규 tools 테스트 PASS.
- **M3 — live wire-pin + 게이트.** 실제 Linear(.env 키)에서 guarded `make_linear_tool_executor()`
  로 throwaway 티켓에 `commentCreate`(allowlisted) 1회 성공 → 경계가 정당한 작업을 깨지
  않음 증명. 같은 executor 로 `mutation { issueDelete(id:"<nonexistent>") }` 가 **로컬 거부**
  (네트워크 안 감)임을 확인하고, 부수로 `query { issueDelete }`(익명 query) 를 보내 서버가
  거부(mutation field on Query)함을 확인(파괴 없음 — 존재하지 않는 id). throwaway comment/
  티켓 정리. run: 일회성 스크립트(커밋 안 함) + `python3 plugin/scripts/check.py`.
  expect: commentCreate success=True, delete 로컬 거부, 서버가 query-mutation 거부, GREEN.

## Progress log
- [x] (2026-06-14) plan created; base_commit 9464e4d; review_level targeted (review-security,
      live exec surface).
- [x] (2026-06-14) M1 done. `director/worker/authority.py`: `_strip`(주석/문자열 blank) +
      `classify_operation`(paren-0 에서만 brace 깊이 셈 → object-value 중괄호가 selection
      set 으로 오인되지 않음; alias/directive/spread 처리; 다중 op 합집합) + `authorize`
      (read→allow, allowlisted-mutation→allow, 그 외/subscription/parse-fail→deny). 8-mutation
      기본 allowlist. `tests/test_director_authority.py` 27 PASS(classify·evasion 배터리·
      authorize·기본 allowlist). 커밋 23e0c70.
- [x] (2026-06-14) M2 done. `make_linear_tool_executor` 에 `allow_mutations=None, guard=True`
      추가; query 검증 직후·POST 전에 `authority.authorize` → deny 면 "blocked by authority
      guardrail: …" 반환(네트워크 안 감). `docs/SECURITY.md` T10 추가 + status 노트 live-surface
      목록에 T10. `tests/test_director_tools.py` 보강(6 신규): destructive→POST 없이 거부,
      allowed/read→POST, default-guard-on(run.py/orchestrator.py 경로), guard=False opt-out,
      custom allowlist tighten. 기존 errors-test 는 allowlisted mutation 으로 수정(guard 통과 후
      서버 errors 도달). 커밋 a369e07.
- [x] (2026-06-14) M3 done. 실제 Linear(LIN/Lingu team) live wire-pin 5/5 PASS: guarded
      executor 로 ① issueCreate(LIN-10 생성) ② commentCreate 성공(allowlisted mutation 이
      실데이터에서 동작 — 경계가 정당한 작업 안 깸), ③ issueDelete 는 guard 가 로컬 거부
      ("blocked by authority guardrail"), ④ `query { issueDelete }` 는 서버가 400 으로 거부
      (mutation field 가 query 로 실행 안 됨 — D-23 가정 live 확인; cleanup 이 같은 id 를
      삭제할 수 있었던 것 자체가 query 가 삭제 안 했다는 증거), ⑤ unguarded 로 LIN-10 정리.
      일회성 스크립트 미커밋·삭제. 게이트 GREEN. 모든 milestone 완료 → 완료 게이트로.
- [x] (2026-06-14) 완료 게이트: self-review(diff vs Goal) + review-security(Claude fallback,
      codex companion auth 여전히 실패) → SATISFIED, P1 없음. P2-A(inline-fragment 테스트),
      P2-B(`_strip` 미종료 문자열 explicit fail-closed) fix-forward + 테스트 추가(GREEN, 216).
      spec stable, plan → completed/.

## Surprises & discoveries

## Decision log
- 2026-06-14: review_level = targeted(review-security) — diff 가 worker→Linear write 권한
  (사람 키, outward-facing)을 다루는 live exec surface. reliability 영향 적음(순수 분류 +
  로컬 거부, 새 블로킹/동시성 없음)이라 review-reliability 생략. (spec D-29.)
- 2026-06-14: M3 live 는 allow 경로만 실데이터로 친다(commentCreate). deny 경로는 순수 로컬
  이라 mock 으로 완전 커버 — 실 삭제 금지.

## Feedback (from completion gate)
review-security(targeted). codex(`/codex:rescue --model gpt-5.5 --effort high`) 재시도
했으나 companion access token refresh 실패(여전히 logged-out/다른 계정) → CLAUDE.md fallback
대로 Claude reviewer(`feature-dev:code-reviewer`)에 review-security 프레이밍으로 위임.
**Verdict: SATISFIED, P1 없음.** 적대적 bypass 헌트(alias·chained alias·주석/문자열 은닉
키워드·block-string 이스케이프·fragment spread·다중 op 합집합·object-value 중괄호·
mutation-under-query·BOM·양쪽 결선)에서 우회 없음 — 분류기-서버 정렬 논거 유효.
- **P2-A (fixed-forward)** — inline fragment(`... on T { issueDelete }`) at mutation root 에
  대한 명시적 테스트 부재(코드는 `...` 브랜치로 이미 deny). → `test_inline_fragment_at_
  mutation_root_is_unresolved` 추가.
- **P2-B (fixed-forward)** — `_strip` 가 미종료 문자열을 silent truncate; deny 가 우연한
  brace 불균형에 의존(no bypass 확인됨, but 보안 경계가 coincidence 에 기대면 안 됨). →
  `_strip` 가 `(stripped, ok)` 반환, 미종료 문자열이면 `ok=False` → `parse_ok=False` 직접
  deny. discriminating 테스트(`query { issues } "dangling`, 중괄호 균형) 추가 — 이 신호가
  없으면 allowed-read 로 오분류됨을 증명. tech-debt-tracker 에 남길 잔여 debt 없음.

## Outcomes & retrospective
**달성.** 워커 `linear_graphql` 가 mutation root-field allowlist(default-deny)로 묶임:
reads 무제한, allowlisted forward-only mutation 만 통과, 파괴적/미지 mutation 은 Linear POST
전에 로컬 거부. 서버 parser 와 정렬된 최소 GraphQL 분류기(주석/문자열 strip → operation type
→ root fields, paren-0 에서만 brace 셈). guard 기본 on → run.py·orchestrator.py 자동 상속.
SECURITY.md T10. 실 Linear live-pin 5/5(allowlisted mutation 실동작 + 로컬 deny + 서버가
query-mutation 거부). gate GREEN(216 tests), 적대적 security review SATISFIED.

**핵심 통찰.** 보안 논거의 단순화: Linear 는 operation 키워드가 문자 그대로 `mutation` 일
때만 mutation field 를 실행한다 → 분류기는 적을 outsmart 할 필요 없이 "서버와 같은 문서를
본다"만 보장하면 됨(strip = GraphQL lexer 가 무시하는 것). bypass 헌트가 이 정렬을
재확인했다. P2-B 가 그 원칙의 작은 누수(우연한 brace 불균형 의존)를 explicit 신호로 메움.

**남은 것(Phase 4 다음 슬라이스).** 이 가드레일은 un-watched dispatch 의 하드 선행조건을
해소 — 이제 자율 Director 본체로: ① **taste-vs-handle escalation policy**(Director 가
워커 질문을 분류해 비-taste 는 직접 답, taste 만 사람에게 — 이 슬라이스의 default-deny 를
escalate-to-Director 로 승급하는 seam 도 여기), ② loop/scheduled oversee + board reporting,
③ PR-merge 관리. D-24 의 escalate-to-Director, argument-level policy, per-worker dynamic
scope 는 후속 정제(spec Open Questions/Non-goals).
