---
status: active
last_verified: 2026-06-14
owner: harness
base_commit: 4f44b41aaca943e770f8726ee167cf46904e52d7
review_level: targeted
---
# Dev-stage taxonomy — 티켓 type → 하네스 워크플로 (Phase 3b)

## Goal

오케스트레이터가 티켓의 **type**(Linear 라벨)을 읽어 그 type 의 하네스 dev-stage 워크플로
prompt 로 워커를 띄운다. **관찰 가능한 done**: MockBoard 에 planning→design→spec→impl
(type 라벨 + blocked_by 체인)을 넣고 `run_until_drained` 를 돌리면, 의존순(planning→design→
spec→impl)으로 dispatch 되고, 각 dispatch 가 그 type 의 **합성 prompt**(spec 은 product-design
참조·docs/product-specs 경로·"impl 자식 생성" 지시; impl 은 execplan 참조)를 받는다.
untyped 티켓은 원본 prompt 그대로. `python3 plugin/scripts/check.py` GREEN.

## Context

- product-spec(이 plan 이 build 하는 design 소유자, 재유도 금지):
  `docs/product-specs/2026-06-14-dev-stage-taxonomy.md` — R1–R6, taxonomy 표(5 type),
  registry/routing/분해 설계, D-18..D-22, non-goals(실-codex 실행·provisioning 연기).
- 선행 build: `docs/exec-plans/completed/2026-06-14-dag-aware-orchestration.md` +
  `director/orchestrator.py`(`run_until_drained`/`_dispatch_wave`/`dispatch`/`eligible_tickets`/
  `MockBoard`), `director/board/linear.py`(`list_ready_issues` + blocker 읽기),
  `director/run.py`(`run_ticket(ticket,...)` 가 `ticket["prompt"]` 사용).
- Phase 2: 워커 `linear_graphql` 툴 + vendored `.codex/skills/linear`(자식 생성 수단).
- 용어: **type** = 개발 stage(planning/research/design/spec/impl). **합성 prompt** =
  type 템플릿 + 원본 ticket prompt. **worker-driven 분해** = 워커가 typed 자식을 만든다.

## Approach (self-generated alternatives)

type 표현:
- A: **Linear 라벨**(라벨명=type). tradeoff: 가장 가볍고 기존 board 에 즉시; 라벨 wire 만
  추가. **Chosen**(D-19).
- B: project/custom-field. tradeoff: 무겁고 board 스키마 의존. 불필요.

분해 주체:
- A: **worker-driven**(템플릿이 워커에 지시, linear 툴로 생성). tradeoff: RV1 결, 실 생성은
  라이브; 구조는 registry+pickup(3a)로 증명. **Chosen**(D-20).
- B: orchestrator-driven(완료 시 자식 생성). tradeoff: 더 결정적이나 에이전트 자율성↓, RV1 위배.

라우팅 위치:
- A: **dispatch 에서 합성**(run_ticket 직전 ticket.prompt 교체). tradeoff: 한 곳, 순수 함수
  재사용, untyped 통과. **Chosen**.
- B: run_ticket 안에서. tradeoff: run 계층이 taxonomy 의존 — 레이어 침범. 피함.

## Assumptions & open questions (self-interrogation)

- Assumption: 워커는 합성 prompt 를 ticket["prompt"] 로 받는다(run_ticket 이 그걸 run_turn
  text 로 보냄). dispatch 가 `{**ticket, "prompt": composed}` 로 교체. 틀리면 run_ticket 시그니처
  변경 필요하나 현 계약과 일치.
- Assumption: 실 worker 가 템플릿 지시대로 typed 자식을 실제로 만드는지는 **라이브**(codex)
  영역 — 이 phase 는 registry·라우팅·정렬을 mock 으로 증명(D-22). pickup 은 3a 가 이미 증명.
- Open: 다중 type 라벨 → 우선순위 impl→spec→design→research→planning(구체 우선). 기록.
- Open: untyped 기본 = raw(backward compat). 기록. 기존 orchestrator 테스트(라벨 없는 티켓)는
  raw 로 그대로 통과해야 함 — 회귀 확인.
- Open: 템플릿 정확 문구는 실런으로 다듬음(non-goal: perfect). 지금은 methodology_ref·산출물
  경로·자식 생성 지시가 들어있는지 구조만 못박는다.

## Milestones

- **M1 — taxonomy 레지스트리 + 순수 함수.** 신규 `director/taxonomy.py`: `TAXONOMY`(5 type,
  각 `{label, stage, methodology_refs, output, child_types, child_label, template}`),
  `ticket_type(ticket)`(라벨→type, 우선순위, 없으면 None), `compose_worker_prompt(ticket)`
  (type 면 템플릿+원본, 아니면 원본). **끝에 존재**: institution-as-data 레지스트리 + 순수
  라우팅. **run**: `python3 tests/test_director_taxonomy.py`. **acceptance**: 5 type 전부·
  child_types 가 파이프라인을 이룸; 각 type 합성 prompt 가 제 methodology_ref·산출물 경로·
  자식 라벨 지시를 포함; untyped→원본; 다중 라벨 우선순위.
- **M2 — board 라벨 읽기.** `director/board/linear.py` `list_ready_issues` 쿼리에
  `labels { nodes { name } }` 추가 → 각 ticket `labels:[name,...]`. `MockBoard` 가 issue 의
  `labels` 를 받아 반환. **끝에 존재**: board 가 type 라벨을 노출. **run**: `python3
  tests/test_director_linear.py`. **acceptance**: 주입 응답에서 labels 정규화; MockBoard 가
  labels 반환; `ticket_type` 이 그 labels 로 type 판별.
- **M3 — 오케스트레이터 type 라우팅 + 파이프라인 정렬.** `dispatch` 가 run_ticket 직전
  `compose_worker_prompt` 로 prompt 교체. **끝에 존재**: 타입 티켓이 제 워크플로 prompt 로
  dispatch. **run**: `python3 tests/test_director_orchestrator.py`. **acceptance**: (a) spec
  티켓 dispatch 시 run_ticket 이 받은 prompt 에 product-design 참조 포함(run_ticket 패치로
  캡처); (b) MockBoard planning→design→spec→impl(라벨+blocked_by) → `run_until_drained` 가
  planning→design→spec→impl 순으로 dispatch, 각 prompt 가 그 type 템플릿; (c) untyped 티켓은
  원본 prompt(회귀).
- **M4 — 라이브 라벨 pin(cheap, no codex).** 실 Linear 에 라벨(예: 새 `spec` 라벨) 단
  throwaway 티켓 → 내 `list_ready_issues` 가 labels 를 정확히 읽고 `ticket_type` 이 맞는지
  확인(MCP 교차검증), 정리. **끝에 존재**: 라벨 wire 고정. **run**: `.env` 키 + 검증 스크립트.
  **acceptance**: 티켓 labels 가 읽히고 ticket_type 이 라벨대로.

## Progress log
- [x] (2026-06-14) plan 작성 + 생성시 self-review.
- [x] (2026-06-14) M1 — `director/taxonomy.py`: `TAXONOMY`(5 type, institution-as-data),
  `ticket_type`(라벨→type, 우선순위), `compose_worker_prompt`(템플릿+원본/untyped raw).
  test_director_taxonomy +10.
- [x] (2026-06-14) M2 — `list_ready_issues` 쿼리에 `labels{nodes{name}}` + `_parse_labels`
  → ticket["labels"]; MockBoard 가 labels 반환. test +1.
- [x] (2026-06-14) M3 — `dispatch` 가 run_ticket 직전 `compose_worker_prompt` 로 prompt
  교체. test +3: spec 티켓→product-design 템플릿, untyped→raw, planning→design→spec→impl
  파이프라인이 의존순 dispatch + 각자 제 type 템플릿. 180 테스트 GREEN.
- [ ] M4 — 라이브 라벨 pin(실 Linear labels wire). (다음.)

## Surprises & discoveries

## Decision log
- 2026-06-14: type=Linear 라벨, dispatch 에서 prompt 합성, worker-driven 분해(RV1).
- 2026-06-14: 다중 라벨 우선순위 impl→spec→design→research→planning(구체 우선).
- 2026-06-14: untyped→raw(backward compat); 실-codex 실행·provisioning 연기(D-22).

## Feedback (from completion gate)

## Outcomes & retrospective
