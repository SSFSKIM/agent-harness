---
status: completed
last_verified: 2026-06-14
owner: claude
base_commit: 8432a8b
review_level: targeted
---
# Product Design 단계 + entry decision

## Goal
작업 시작 전 에이전트가 진입 모드(throwaway / Product Design / ExecPlan)를 스스로
고르고, "무엇을 만들지"가 풍부하면 `docs/product-specs/` 에 별도 spec 을 쓴 뒤 그것을
참조하는 ExecPlan 으로 넘어가는 methodology 가 repo 에 인코딩된다. 검증 가능한 done:
`python3 plugin/scripts/check.py` GREEN + 새 `product-design` skill 이 Components 표에
등록되고 + AGENTS.md/PLANS.md 가 세 갈래 entry decision 을 soft heuristic 으로 담는다.

## Context
- spec(무엇·왜): `docs/product-specs/2026-06-14-product-design-phase.md` — 요구사항
  R1-R6, 비목표, 수용 기준. 이 ExecPlan 은 그 spec 의 "어떻게"만 소유한다.
- 배경: superpowers 와의 비교(이 repo 의 ExecPlan = implementation-plan 척추 + 얇은
  spec 층). 분리 가치 = 수명 · one-to-many · 검증 계약 · 사람-터치 표면.
- governance 는 이미 끝남(커밋 `8432a8b` "Govern product specs by default" —
  product-specs 를 MANAGED_ROOTS/HOST_MANAGED_ROOTS/HOST_INDEXED_DIRS 에 추가 +
  poisoning 테스트). 이 변경은 거기에 손대지 않는다.

## Approach (self-generated alternatives)
- A: PLANS.md 에 라우팅 규칙 한 줄만 — "요구사항이 오래 살면 product-specs 에 spec
  쓰고 참조". skill·단계 없음. tradeoff: 가장 가볍지만 사용자가 명시 거부("얇은 층
  넘어선 진짜 논의 단계가 필요"). spec 작성 절차가 무소유 → 비일관.
- B: execplan skill 에 spec sub-mode 추가. tradeoff: 한 skill 에 두 진입 모드가
  섞여 progressive-disclosure 위반, 트리거 모호.
- C: 새 `product-design` skill(절차 소유) + AGENTS.md/PLANS.md 의 entry decision(세
  갈래 triage). tradeoff: 파일 fan-out 크지만 두 모드가 깨끗이 분리되고 각 skill 이
  자기 절차만 로드. governance 는 8432a8b 가 이미 처리해 보안 표면 무변경.
- Chosen: **C** — 사용자가 "진짜 단계"를 원했고(R3·R5), 두 진입 모드 분리가 skill
  모델과 일치. (Decision log 반영.)

## Assumptions & open questions (self-interrogation)
- Assumption: product-specs governance 는 8432a8b 로 완결(테스트 포함) — 재구현하면
  중복/충돌. 깨지면: 보안 표면을 건드리게 되어 review_level 을 full 로 올려야 함.
- Assumption: Product Design 은 에이전트 자율 draft, 사람은 product-direction 분기
  에서만 개입(R4) — front-loading 이 "사람 대화 아님"이라던 사용자 원칙과 정합. 제품
  방향만 예외인 이유: PRODUCT_SENSE.md 가 그것을 사람에게 reserve.
- Open: entry decision 의 물리적 트리거 위치 → AGENTS.md step 2(매 세션 읽힘) +
  PLANS.md(상세)로 자율 해소. escalate 아님.
- Open: 이 변경 자체의 진입 모드 → R1 heuristic 적용 시 요구사항이 풍부·fan-out →
  **Product Design first** 로 자율 결정(그래서 spec 을 먼저 씀). escalate 아님.

## Milestones
- [x] M1 — PLANS.md entry decision 섹션 + Context 링크 규칙. harness-init **plans-md
  + agents-md** template 둘 다 mirror (agents-md 는 review 가 잡은 누락 — 사후 보강).
- [x] M2 — `product-design` skill 작성(spec→product-specs→index→execplan handoff,
  사람-터치 표면). agent-harness.md Components 표 등록 + inventory 재생성(coverage GREEN).
- [x] M3 — execplan skill Create 에 product-spec 링크 단계 추가.
- [x] M4 — AGENTS.md step 2 세 갈래화 + core-beliefs.md #12.
- [x] M5 — gate GREEN(92 tests), targeted review(codex review-arch), close.

## Progress log
- 2026-06-14: spec 작성 + index 등록. ExecPlan 생성(base_commit 8432a8b). 구현 시작.
- 2026-06-14: M1-M4 구현. inventory 재생성. gate GREEN. codex(gpt-5.5) review-arch
  dispatch → P1 1건(host AGENTS.md seed 에 entry decision 누락) 수정 + 재게이트 GREEN.

## Surprises & discoveries
- 2026-06-14: governance 변경(product-specs 재포함)이 세션 중 working-tree sketch →
  사용자가 커밋 `8432a8b` 로 확정 + origin push. 내 원래 governance milestone 은
  이미 완료 상태로 도착 → scope 가 methodology 층으로 축소됨.

## Decision log
- 2026-06-14: Approach C 채택 — 새 product-design skill + entry decision triage. A/B
  거부(라우팅만/execplan 혼합). governance 는 8432a8b 소유라 무변경.

## Feedback (from completion gate)
- codex(gpt-5.5, high) review-arch — Verdict: 수정 후 SATISFIED.
  - P1 (fixed): host AGENTS.md seed(`templates/agents-md.md`) step 2 가 옛
    throwaway/ExecPlan-only — entry decision 누락 → 신규 host R1 미충족. 실제 fan-out
    gap 확인 후 self-host 와 동일 문구로 mirror.
  - P1 (rejected): "gate not GREEN — unittest 실패". codex 샌드박스의 temp-dir 제약이
    원인(코드 결함 아님; codex 도 caveat 명시). 비샌드박스 환경에서 92 tests GREEN 2회
    확인 → ground-truth 로 기각.
  - P2 (no-action): plans-md template 의 "Quality rules" 헤딩이 instance 와 미세 drift.
    instance 만 adoption-date 를 다는 by-design 차이, 이 변경이 만든 게 아님.

## Outcomes & retrospective
- ExecPlan 의 정체성 정리: implementation-plan 척추 + 얇은 spec 층. 요구사항이 plan 보다
  오래 살거나 fan out 하면 spec 을 `product-specs/` 의 별도 artifact 로 승격 — review_level
  과 같은 risk-budgeting 을 spec layer 에 적용. superpowers 의 강제 2-문서/human-gate 는
  미채택, front-loading discipline 만 채택한 기존 노선의 자연스러운 연장.
- 사람-터치 표면을 깔끔히 배치: ExecPlan 은 완전 자율, Product Design 이 product-direction
  escalation 의 유일한 착지점. front-loading="사람 대화 아님" 원칙과 모순 없음.
- 교훈(fan-out): AGENTS.md 를 self-host 만 고치고 host **seed template** mirror 를
  빠뜨림 — PLANS.md 는 mirror 했으면서. "AGENTS.md/PLANS.md 를 고치면 harness-init
  template 짝도 같이"가 반복 패턴. review 가 정확히 이걸 잡음 → 다음에 promote 후보.
- dogfood 성립: 이 변경 자체가 entry decision(Product Design first)→spec→참조 ExecPlan
  경로를 한 번 돌렸다(R1 실증).
