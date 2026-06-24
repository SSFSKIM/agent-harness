---
status: stable
last_verified: 2026-06-14
owner: harness
phase: symphony/03-dev-stage-taxonomy
type: product-spec
tags: [taxonomy, ticket-type, methodology, orchestration]
description: Maps ticket types (planning/research/design/spec/impl) to harness doc-pipeline stages so each type routes to a methodology, output doc, and typed children, turning the agent org into a typed ticket DAG.
---
# Dev-stage taxonomy — 티켓 type → 하네스 워크플로 (Phase 3b)

부모 spec: [Symphony 티켓 오케스트레이션 + 중앙 Director](2026-06-14-symphony-director-orchestration.md)
(Phase 3 = 티켓 DAG + dev-stage taxonomy). 선행: [DAG-aware 연속 오케스트레이션](2026-06-14-dag-aware-orchestration.md)
(3a — blocked_by + 연속 wave 루프). 이 spec 은 Phase 3 의 **3b — dev-stage taxonomy**.

핵심: 에이전트 조직 구조는 고정 role 이 아니라 **typed 티켓 DAG**(RV1). 티켓의 **type**
이 개발 lifecycle 의 한 **stage** 에 매핑되고, 그 stage 는 **하네스 자신의 doc 파이프라인**
(AGENTS.md 운영 모델: product-design→spec, execplan→plan+code)의 한 단계다. `spec` 타입
티켓의 워커는 product-design 을 따라 product-spec 을 산출하고 `impl` 자식 티켓을 만든다;
`impl` 워커는 execplan 을 따라 exec-plan+코드를 산출한다. 자식은 부모에 `blocked_by` 로
달려 3a 의 DAG 가 자동 정렬한다. 결과: **하네스가 자기 자신을 돌리는 typed 티켓 DAG** 가
조직이 된다(사람 결정 2026-06-14: full taxonomy 먼저).

## 문제 (Problem)

- 3a 까지의 오케스트레이터는 티켓을 **무형(untyped)** 으로 본다 — 모든 티켓에 같은 raw
  prompt 로 워커를 띄운다. "이 티켓은 spec 단계라 product-design 을 따라야 한다" 같은
  stage 인식이 없다.
- 따라서 워크는 institutionalize 되지 않는다: 큰 목표가 planning→design→spec→impl 로
  분해되어 각 단계가 알맞은 하네스 doc(product-spec / exec-plan / design-doc / research
  digest)을 산출하는 파이프라인이 없다. 에이전트가 자식 티켓을 만들어도 그 자식이 "어떤
  단계"인지, 어떤 워크플로로 처리될지 정의돼 있지 않다.
- RV1("티켓 DAG 가 조직")의 핵심인 **typed 분해**가 빠져 있다.

관찰 가능한 부재: `spec` 라벨 티켓을 넣어도 워커가 product-design 방법론·산출물 경로·
`impl` 자식 생성 지시를 받지 못한다; planning→...→impl 타입 파이프라인이 DAG 로 정렬되어
각 단계가 제 워크플로로 라우팅되는 일이 없다.

## 요구사항 (Requirements)

- **R1 — 티켓 type 판별.** board 가 이슈 라벨을 읽고, taxonomy 가 type-라벨을 type 으로
  매핑한다(해당 라벨 없으면 untyped=None). (검증: `spec` 라벨 티켓 → type "spec"; 라벨
  없는 티켓 → None.)
- **R2 — taxonomy 레지스트리.** 5개 type(planning·research·design·spec·impl) 각각이
  `{label, stage, methodology_refs, output, child_types, template}` 을 갖고, child_types 가
  planning→{research,design}→spec→impl 파이프라인을 이룬다. (검증: 레지스트리에 5개 전부,
  각 child_types 가 다음 stage 를 가리킴.)
- **R3 — prompt 라우팅.** `compose_worker_prompt(ticket)` = type 템플릿(methodology refs +
  산출물 경로 + typed 자식 생성 지시) + 원본 ticket prompt; untyped → 원본 그대로.
  (검증: spec 티켓의 합성 prompt 에 product-design 참조·docs/product-specs 경로·"impl 자식
  생성"이 들어있고, untyped 티켓 prompt 는 불변.)
- **R4 — 오케스트레이터 type 라우팅.** dispatch 가 합성 prompt 로 워커를 띄운다.
  (검증: spec 티켓에 배치된 워커가 합성된 spec prompt 를 받음 — run_ticket 이 합성 prompt
  로 호출됨.)
- **R5 — typed DAG 정렬.** typed 파이프라인(planning→design→spec→impl, type 라벨 + blocked_by)
  을 `run_until_drained` 가 의존순으로 정렬해 각 티켓을 제 type 의 합성 prompt 로 dispatch.
  (검증: mock 파이프라인이 planning→design→spec→impl 순으로, 각자 올바른 템플릿으로 dispatch.)
- **R6 — worker-driven 분해(메커니즘).** type 템플릿이 워커에게 typed 자식(라벨 + blocked_by)
  을 linear 툴로 만들라 지시; 오케스트레이터가 그 자식을 집어(3a) 라우팅(R4)한다.
  (검증: 레지스트리가 type 별 child_types·child 라벨을 인코딩하고 템플릿이 생성 지시를 포함;
  pickup 은 3a 가 증명. 실 worker-driven 생성은 라이브, codex 가용 시.)

## 설계 (Design)

### Taxonomy (5 stages)

| type | label | stage 역할 | 워커가 따르는 방법론 | 산출 doc | typed 자식(blocked_by self) |
|---|---|---|---|---|---|
| **planning** | `planning` | 목표를 typed DAG 로 분해 | AGENTS.md 운영 모델 · docs/PLANS.md entry decision | 분해 노트(throwaway plan/티켓 본문) | research / design / spec |
| **research** | `research` | 미지 조사 | docs/references/index.md 관례 | research digest(docs/references/) | (leaf; design/spec 을 unblock) |
| **design** | `design` | 아키텍처 high/low 설계 | docs/design-docs/core-beliefs.md · ARCHITECTURE.md | design doc(docs/design-docs/) | spec |
| **spec** | `spec` | product design(the what) | plugin/skills/product-design/SKILL.md · docs/PLANS.md | product-spec(docs/product-specs/) | impl |
| **impl** | `impl` | implementation(the build) | plugin/skills/execplan/SKILL.md · docs/PLANS.md · docs/DESIGN.md | exec-plan(docs/exec-plans/) + 코드 | (leaf; 큰 일은 impl 추가) |

파이프라인: `planning → {research, design, spec} → spec → impl` — planning 은 다음 적절한
단계를 고른다(간단한 목표면 곧장 spec, 복잡하면 design 경유). 각 단계가 자기 자식을 만들어
DAG 를 키우고, 3a 가 blocker 가 풀릴 때마다 다음 단계를 dispatch 한다.

### 구성요소 / 파일

- **신규 `director/taxonomy.py`** — institution-as-data:
  - `TAXONOMY: dict[str, dict]` — 위 표를 그대로. 각 엔트리 `{label, stage,
    methodology_refs:[...], output, child_types:[...], template}`. (D-19 로 라벨명=type 이라
    자식의 라벨 = `child_types` 그대로 — 별도 `child_label` 필드는 중복이라 두지 않는다.)
  - `ticket_type(ticket) -> str | None` — ticket["labels"] 중 TAXONOMY 라벨 하나를 type 으로
    (없으면 None).
  - `compose_worker_prompt(ticket) -> str` — type 있으면 `template.format(...) + "\n\nTASK:\n"
    + ticket["prompt"]`; 없으면 ticket["prompt"] 그대로. 템플릿은 stage 역할·methodology_refs
    (repo 내 경로)·산출물 경로·"각 sub-piece 마다 `{child_label}` 라벨 + blocked_by
    {identifier} 자식을 linear 툴로 생성" 지시를 담는다.
- **수정 `director/board/linear.py`** — `list_ready_issues` 쿼리에 `labels { nodes { name } }`
  추가, 정규화 결과 각 ticket 에 `labels: [name,...]`. (라벨 wire 는 라이브 pin.)
- **수정 `director/orchestrator.py`** — `dispatch` 가 run_ticket 전에 ticket 의 prompt 를
  `taxonomy.compose_worker_prompt(ticket)` 로 교체(`{**ticket, "prompt": composed}`).
  `MockBoard` 가 issue 의 `labels` 를 받아 list_ready_issues 에서 반환.
- **신규 `tests/test_director_taxonomy.py`** + linear/orchestrator 보강.

### 핵심 behavior

- **라우팅은 순수 함수.** type 판별·prompt 합성은 board/네트워크와 무관한 순수 로직 →
  단위테스트로 각 type 템플릿 내용을 못박는다.
- **분해는 worker-driven(RV1).** 오케스트레이터는 자식을 만들지 않는다 — 템플릿이 워커에게
  지시하고, 워커가 linear_graphql(Phase 2) + linear 스킬로 typed 자식을 만든다. 오케스트레이터는
  라우팅 + 3a 정렬만. (실 생성은 라이브; 이 phase 는 레지스트리·템플릿·pickup 으로 구조 증명.)
- **self-hosting 참조.** 템플릿은 repo 자신의 방법론을 **경로로** 가리킨다(plugin/skills/
  product-design/SKILL.md, docs/PLANS.md…). 워커가 repo 안에서 그 방법론을 읽는다 — 하네스가
  자신을 돌린다.

### 에러 / 경계

- **알 수 없는/없는 라벨** → untyped → raw prompt(3a 까지 동작과 동일, backward compat).
- **다중 type 라벨** → 레지스트리 우선순위(impl→spec→design→research→planning, 가장 구체적
  먼저) 중 첫 매치. (드문 경우; 기록.)
- **라벨 읽기 실패**(쿼리) → labels 없음으로 간주 → untyped(보수적, 라우팅 안 함).

## 비목표 (Non-goals) — YAGNI

- **실-codex 방법론 실행**(워커가 실제로 spec/코드를 씀) — 연기(codex auth 다운; 지금은
  레지스트리·라우팅·정렬을 mock 으로 구조 증명). 실행은 provisioning + codex 가용 후.
- **git-worktree repo provisioning** — 연기(사람이 taxonomy 를 provisioning 보다 먼저 선택).
  워커가 실제 repo 에서 doc/코드를 쓰는 substrate 는 후속.
- **템플릿 완성도** — 첫 템플릿은 충분히 구체적이되 실런으로 다듬는다. perfect 아님.
- **Linear type 라벨 자동 생성** — 라벨은 존재 가정(또는 선택적 setup 헬퍼). 자동 생성은 후속.
- **Director-driven 분해** — 분해는 worker-driven(RV1).
- **stage별 리뷰 예산/품질 게이트 차등** — 후속(Phase 4 자율 정책과 함께).

## 수용 기준 (Acceptance)

- **mock(deterministic, hard gate):**
  - 레지스트리: 5 type 전부, 각 child_types 가 파이프라인을 이룸; `compose_worker_prompt`
    가 각 type 마다 올바른 methodology_ref·산출물 경로·자식-생성 지시를 담고, untyped 는 원본.
  - `ticket_type`: 라벨→type 매핑, 없으면 None, 다중 라벨 우선순위.
  - typed 파이프라인 정렬: MockBoard 에 planning→design→spec→impl(type 라벨 + blocked_by 체인)
    → `run_until_drained` 가 의존순 dispatch, 각 dispatch 가 그 type 의 합성 prompt 를 받음
    (dispatch 를 캡처해 prompt 내용 검증).
- **라이브 pin(cheap, no codex):** 실 Linear 에 라벨 단 throwaway 티켓 → `list_ready_issues`
  가 labels 를 정확히 읽고 `ticket_type` 이 맞는지 확인(MCP 교차검증), 정리. 라벨 wire 고정.
- `python3 plugin/scripts/check.py` GREEN.

## Decision Log (부모 D-1..D-7, 오케스트레이터 D-8..D-12, 3a D-13..D-17 이어서)

> **Revised by [ADR 0004 — ticket = purpose unit](../adr/0004-ticket-purpose-unit.md)
> (2026-06-25).** D-18/D-20 stand as the *type registry*, but inter-stage
> decomposition is no longer the routine per-stage hand-off — a ticket carries the
> whole pipeline within it, and a worker spawns a child ticket only on a genuine size
> split or surfaced deferred work, each child self-contained. See the ADR.
>
> **Further superseded by [ADR 0005 — no stage prompt templates](../adr/0005-no-stage-prompt-templates.md)
> (2026-06-25).** The per-stage prompt **templates** (R3's `compose_worker_prompt` template
> wrapping, the `template` field, the methodology_refs/output pointers) are **removed** — the
> worker's methodology surface is `WORKER_PROTOCOL` + the host's auto-loaded AGENTS.md +
> invocable skills. `compose_worker_prompt` returns the raw ticket. The **label / `ticket_type`
> registry stands** as dispatch + DAG metadata (R1/R2 type-resolution intact); only the
> prompt-shaping templates (R3) are retired.

- **D-18 full taxonomy 먼저.** (사람, 2026-06-14.) 5 stage 전부 type 으로 — 최소(spec→impl)
  대신 완전한 institutional 모델.
- **D-19 type = Linear 라벨**(라벨명 = type, 레지스트리가 라벨→type). 가장 단순; 라벨명은
  설정 가능. project/custom-field 대신 라벨(가장 가볍고 Symphony 결).
- **D-20 worker-driven 분해(RV1).** 템플릿이 워커에게 typed 자식 생성을 지시; 오케스트레이터는
  안 만든다. 에이전트 self-created 티켓 = 조직이 스스로 자란다.
- **D-21 템플릿은 repo 방법론을 경로로 참조(self-hosting).** 워커가 repo 안에서 product-design/
  execplan/PLANS.md 를 읽는다 — 하네스가 자신을 돌린다.
- **D-22 실-codex 실행 + provisioning 연기.** mock 으로 라우팅·taxonomy·정렬 구조 증명(codex
  auth 다운). 실 방법론 실행은 worktree provisioning + codex 가용 후.

## 열린 질문 (Open Questions) — ExecPlan 이 확정

- 라벨 네이밍(plain `spec` vs `stage:spec` 그룹) → plain, 설정 가능. 충돌 시 ExecPlan 재단.
- planning 산출물(전용 doc vs 자식만 + 짧은 노트) → 자식 위주 + 노트; 경로 ExecPlan 확정.
- untyped 기본 = raw(backward compat) vs impl 취급 → raw. (기록.)
- 다중 type 라벨 우선순위 순서 → impl→spec→design→research→planning(구체 우선); ExecPlan 확정.
