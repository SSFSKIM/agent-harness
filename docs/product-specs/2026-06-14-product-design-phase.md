---
status: stable
last_verified: 2026-06-14
owner: harness
---
# Product Design 단계 + entry decision

methodology spec. ExecPlan 앞단에 **무엇을 만들지(spec)** 를 정하는 별도 단계를
두고, 작업 시작 전 에이전트가 진입 모드를 스스로 고르게 한다. 이 문서가 그 단계의
요구사항(이 spec 자체가 첫 산출물 — dogfood)이고, 구현은
`exec-plans/completed/2026-06-14-product-design-phase.md` 가 닫는다.

## 문제

ExecPlan 은 implementation plan(어떻게 빌드하나)을 척추로 갖고, 최근 추가한
front-loading 섹션(Approach·Assumptions)으로 spec(무엇·왜)을 **얇은 층**으로 흡수했다.
그런데 요구사항이 단일 plan 보다 오래 살거나 여러 linked plan 에 퍼지면, 얇은 층은
부족하다 — durable 한 "무엇"이 volatile 한 "어떻게" 안에 갇혀 plan 이 `completed/` 로
가는 순간 같이 죽고, linked plan 들이 가리킬 공유 spec 의 집이 없다. superpowers 의
brainstorming→spec 분리가 사 주던 가치(수명 분리 · one-to-many 재사용 · 독립 검증
계약 · 깨끗한 사람-터치 표면)를 우리는 일부만 취했다.

단, superpowers 식 **모든 작업 2-문서 강제**는 여전히 틀렸다(throughput beats
ceremony — PRODUCT_SENSE.md). 작은 작업은 spec 이 필요 없다.

## 요구사항

- **R1 — entry decision.** 작업 시작 전, 에이전트가 복잡도를 보고 진입 모드를 고른다:
  throwaway · **Product Design(spec)** · ExecPlan. 이 판단은 `review_level` 처럼
  risk-budgeted 이며, AGENTS.md 운영 모델(매 세션 읽힘)과 PLANS.md(상세)에 산다.
- **R2 — soft heuristic, not gate.** 모드 선택은 strict/deterministic 체크리스트가
  아니라 에이전트 판단이다. 가이드 신호(요구사항이 단일 plan 보다 오래 사는가 /
  여러 plan 에 퍼지는가 / 따로 검증할 만큼 풍부·다툼있는가)는 *질문*이지 통과조건이
  아니다.
- **R3 — Product Design = 별도 durable artifact.** spec 은 ExecPlan 안의 섹션이 아니라
  `docs/product-specs/` 의 독립 문서다. ExecPlan 은 그것을 Context 에서 *참조*하고
  요구사항을 재유도하지 않는다.
- **R4 — 사람-터치 표면.** ExecPlan 은 완전 자율(사람 게이트 0). 제품 방향/taste 는
  PRODUCT_SENSE.md 가 사람에게 reserve 한 영역 → Product Design 문서가 그 드문 개입이
  착지하는 자연스러운 escalation 표면이다. spec 은 에이전트가 자율 draft 하되, 진짜
  product-direction 분기에서만 사람에게 올린다. ("what next?" 는 여전히 금지.)
- **R5 — 절차는 skill 이 소유.** Product Design 단계의 step-by-step 은 새
  `product-design` skill 이 소유한다(execplan 과 구분 — 두 진입 모드 = 두 skill,
  progressive disclosure). 둘 다 PLANS.md 의 entry decision 으로 수렴한다.
- **R6 — governance 무변경.** spec 의 집(`product-specs/`)은 이미 governed(커밋
  `8432a8b`, poisoning-protected, 테스트 포함). 이 변경은 거기에 손대지 않는다.

## 설계 (design)

정책 문서라 design 은 경량 (template 의 "scale down for a policy doc" 적용 — 구성요소
와 경계만, 코드/태스크 없음):
- **entry decision** — PLANS.md 신규 섹션(상세 heuristic) + AGENTS.md step 2(매 세션
  읽히는 포인터). soft heuristic 서술이지 strict gate 아님.
- **product-design skill** — 절차 소유: explore → scope check → draft(Problem/
  Requirements/Design/Non-goals/Acceptance) → 사람-터치 → self-review → write →
  execplan handoff.
- **spec↔ExecPlan 경계** — spec = design(what/why + shape: 구성요소·contract·behavior),
  ExecPlan = build(execution). ExecPlan Context 가 spec 을 링크하고 design 에서
  build 하며 재유도하지 않는다.
- **에러/경계 케이스** — 미로드 세션: skill 절차가 파일로 보존돼 `.../SKILL.md` 직접
  read 가능(기존 하네스 패턴). coverage lint: 신규 skill 은 docs 에 mention 필요.

## 비목표 (non-goals)

- superpowers 식 phase 별 human approval gate. (자율 thesis 위반.)
- 모든 작업에 spec 강제. (작은 작업은 throwaway.)
- spec↔plan 을 2-문서로 *항상* 쪼개기. 분리는 R1 heuristic 이 부를 때만.
- product-specs governance/보안 표면 변경 (8432a8b 가 소유).

## 수용 기준

- AGENTS.md step 2 와 PLANS.md 가 세 갈래 entry decision 을 담고, 둘 다 soft heuristic
  으로 서술한다(strict 체크리스트 아님 — R1·R2).
- `product-design` skill 이 존재하고, spec 을 `product-specs/` 에 쓰고 index 등록 후
  execplan 으로 handoff 하는 절차를 담는다(R3·R5). agent-harness.md Components 표에
  등록(coverage lint GREEN).
- execplan skill Create 가 "product-spec 이 있으면 Context 에 링크, 요구사항 재유도
  금지"를 담는다(R3).
- core-beliefs.md 에 entry decision / spec-as-separable-artifact belief 1개 추가.
- `python3 plugin/scripts/check.py` GREEN.
- 이 변경 자체가 R1 을 dogfood: spec(이 문서) → 참조하는 ExecPlan → 구현.
