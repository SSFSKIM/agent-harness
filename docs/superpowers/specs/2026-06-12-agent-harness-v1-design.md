# agent-harness v1 — Design Spec

> 2026-06-12. 로컬 Claude Code 위에서 OpenAI harness engineering 세팅을 재현하고,
> 그 foundation 위에 위키의 memory lifecycle (STORE→INJECT→IMPRINT→CONSOLIDATE) 을 얹는
> self-hosting AI-native harness.
>
> 설계 근거 위키: `~/Documents/Obsidian Vault/클라우드 에이전트/` —
> wiki/concepts/agent-native-software-engineering · wiki/synthesis/memory-lifecycle ·
> wiki/entities/symphony · sources-summary/openai-harness-engineering.

## 0. 목적과 전략

- **목적**: 클라우드 커스텀 하네스를 백지에서 Agent SDK 로 짓기 전에, 로컬 Claude Code 에서
  AI-native harness (minimum human-in-loop) 의 메모리 시스템 · 개발 방법론 · docs 활용을
  먼저 구현·검증한다.
- **전략**: foundation = **OpenAI harness engineering 블로그 세팅의 충실한 재현**.
  메모리 시스템 (feeder/imprint hooks, dreaming) 은 그 위에 얹는 layer 2.
- **testbed = self-hosting**: 이 repo 자체가 첫 agent-native repo 다. 하네스 개선 작업이
  하네스로 수행된다 (Q37 첫 target).
- **v1 제외 (명시적 defer)**: Symphony-style 오케스트레이션 (issue board control plane,
  병렬 dispatch) 전체 · observability stack (Vector/LogQL) · browser/CDP 검증 ·
  GitHub PR/CI 루프 (로컬 git commit 게이트로 치환; remote 는 요청 시) · `FRONTEND.md` (UI 없음).
  이것들은 v2 또는 두 번째 target repo (실제 앱) 이식 시 추가.

## 1. 전체 구조 — 두 레이어, 한 repo

물리적으로 **기계 (plugin/) 와 인스턴스 (repo 루트)** 를 분리한다.

```
agent-harness/
├── AGENTS.md                  # ~100줄 map: operating model + docs/ 포인터 (인스턴스)
├── ARCHITECTURE.md            # codemap + invariants (인스턴스)
├── docs/
│   ├── design-docs/
│   │   ├── index.md
│   │   ├── core-beliefs.md    # agent-first 운영 원칙 + golden rules
│   │   └── ...
│   ├── exec-plans/
│   │   ├── active/
│   │   ├── completed/
│   │   └── tech-debt-tracker.md
│   ├── generated/             # 스크립트 자동 생성 (component-inventory.md 등)
│   ├── product-specs/
│   │   └── index.md
│   ├── references/            # llms.txt 스타일 — Claude Code plugin/hooks API digest 등
│   ├── DESIGN.md              # 이 repo 의 taste: skill/hook 설계 규범
│   ├── PLANS.md               # ExecPlan 방법론 문서 (cookbook 내재화)
│   ├── PRODUCT_SENSE.md       # 하네스가 무엇을 최적화하는가 (minimum human-in-loop 철학)
│   ├── QUALITY_SCORE.md       # 도메인×레이어별 등급 + 시간에 따른 격차 추적
│   ├── RELIABILITY.md         # review-reliability persona 의 grounding 문서
│   ├── SECURITY.md            # review-security persona 의 grounding 문서
│   └── memory/                # ★ Layer 2: structured LTM (§3)
├── plugin/                    # ★ Claude Code 플러그인 (이식 가능한 기계)
│   ├── .claude-plugin/plugin.json
│   ├── skills/                # execplan, docs-tree, harness-lint, dream, ...
│   ├── agents/                # doc-gardener, review-arch, review-reliability,
│   │                          #   review-security, dreamer, feeder
│   ├── hooks/hooks.json       # SessionStart / UserPromptSubmit / PreCompact / SessionEnd
│   └── scripts/               # stdlib python3: lint 군, imprint queue, inventory 생성
└── tests/                     # 스크립트 단위 테스트 + doc invariant 테스트
```

- 로드: `claude --plugin-dir ./plugin` (self-hosting).
- **이식성 invariant**: plugin/ 은 인스턴스 경로를 하드코딩하지 않는다. 모든 경로는
  repo-root 상대 + 규약 기반. 다른 repo 에 이식할 땐 plugin/ 만 가져가고 docs tree 는
  그 repo 가 자기 것을 갖는다.

## 2. Layer 1 — OpenAI harness engineering 재현 (foundation)

### 2.1 지식 시스템 (repo = 기록 시스템)

- `AGENTS.md` 는 백과사전이 아니라 **목차/map** (~100줄, lint 가 120줄 초과 시 FAIL).
  operating model (3-5단계: docs 숙지 → plan → implement → validate → review) + docs/ 포인터.
- `ARCHITECTURE.md` = codemap + architectural invariant + boundary (matklad 스타일).
- `docs/` progressive disclosure. **카테고리별 `index.md` 필수** — lint 가 존재 + 등록
  누락 검사.
- **계획 = 1급 아티팩트**: 비자명한 작업은 `exec-plans/active/` 에 living ExecPlan
  (Progress / Surprises & Discoveries / Decision Log / Outcomes & Retrospective 갱신 의무),
  완료 시 `completed/` 이동. `docs/PLANS.md` 가 방법론 소유, `execplan` skill 이 절차 소유.
- `references/` 에 의존 도구 문서를 llms.txt 스타일로 체크인 (Claude Code plugin API,
  hooks API digest 등).
- `generated/` 는 스크립트가 생성 (예: `component-inventory.md` — plugin 의
  skills/agents/hooks 자동 목록). 손 편집 금지 (lint 강제).

### 2.2 아키텍처 및 취향의 기계 강제

- **레이어드 아키텍처의 plugin 번역**: 의존 방향 고정
  `scripts (순수 stdlib, 의존 없음) → skills (절차) → agents (persona) → hooks (wiring)`.
  cross-cutting (경로/설정 해석) 은 단일 `harness_lib` 모듈로만 (Providers analog).
  `lint_structure.py` 가 기계 강제.
- **taste lints** (`lint_docs.py` 등): cross-link 유효성, frontmatter 필수 필드,
  stale 검사 (`last_verified`), 파일 크기 제한, kebab-case 명명, index 등록.
- **모든 lint 에러 메시지에 수정 지침 포함** — agent context 에 직접 주입되는 교정 신호.
- **golden rules** 는 `design-docs/core-beliefs.md` 에 인코딩 (공유 util 선호, 경계에서
  parse-don't-validate, 내재화 선호 — 외부 의존 최소화 + 작은 helper 직접 구현).

### 2.3 리뷰 — CI review jobs 의 로컬 치환

- 트리거 = **ExecPlan 완료 게이트** (OpenAI 의 "PR 생성" 경계의 로컬 등가물).
  plan 완료 선언 시 review persona subagent 3개가 diff 를 병렬 리뷰:
  - `review-arch` ← `ARCHITECTURE.md` + `DESIGN.md` grounding
  - `review-reliability` ← `RELIABILITY.md` grounding (idempotency, dedupe, hook 실패 모드)
  - `review-security` ← `SECURITY.md` grounding (hook 안전, prompt injection, memory poisoning)
- **persona ↔ 문서 1:1 연결이 핵심 메커니즘**: 인간 피드백은 해당 문서에 기록되고,
  다음 리뷰부터 자동 반영된다. 같은 피드백을 두 번 주지 않는다.
- P2 finding 은 ExecPlan 에 feedback 으로 기록 → 구현 세션이 수정 → 게이트 재실행.

### 2.4 Entropy GC

- `doc-gardener` agent (주기 실행 또는 `/garden`): ① 코드↔문서 drift 탐지·수정
  ② golden-rule 편차 검사 ③ `QUALITY_SCORE.md` 등급 갱신 (도메인×레이어 grading +
  격차 추적) ④ 대상 리팩토링 수행. `tech-debt-tracker.md` 운영.
- 원칙: 기술 부채는 고금리 대출 — 매일 조금씩 GC.

### 2.5 피드백 원칙 (AGENTS.md 에 명문화)

agent 가 어려움을 겪으면 그것은 **harness 누락 신호** 다: 도구/가드레일/문서 중 무엇이
빠졌는지 진단 → repo 에 인코딩 → 재시도. 인간 취향 피드백은 1-2회 받으면 문서 또는
lint 로 승격해 영구 반영.

## 3. Layer 2 — 메모리 루프

**핵심 결정: repo docs tree 가 곧 structured memory 다.** 별도 저장소를 두면 source of
truth 가 둘이 되어 drift 를 재생산한다 (위키 C6 교훈의 일반화).

### 3.1 STORE

```
docs/memory/
├── MEMORY.md          # bootloader (~50줄): navigate 지시 + loading protocol 만.
│                      #   지식 dump 금지 (lint 강제)
├── progress/current.md
├── adr/  knowledge/  openq/  limitations/
└── archive/sessions/  # session digest (dreaming 의 입력)
```

모든 페이지에 `status / last_verified` frontmatter (lint 강제).

### 3.2 INJECT — 2단 feeder (Sonnet 1M agent)

- **SessionStart hook**: Sonnet 1M context agent 를 헤드리스로 스폰. progress/current +
  active ExecPlan + openq digest + 최근 session digest 를 넓게 읽고, role 과 최근 작업
  흐름을 고려해 **context pack 을 컴파일** → additionalContext 로 주입.
  ("주입은 검색이 아니라 컴파일".)
- **UserPromptSubmit hook (세션 첫 프롬프트에만 발동)**: SessionStart 시점엔 세션 목적이
  없으므로, 실제 task 를 보고 목적-특화 context (관련 knowledge/ADR/limitations) 를 추가
  주입. 이 2단 구조가 "세션 목적 고려"를 실제로 가능하게 하는 배치다.

### 3.3 IMPRINT — 동기 write-back

- **PreCompact hook**: 컴팩 직전 세션에 write-back 지시 주입 (progress 갱신 + 재사용
  지식 / 한계 / 미결 / 결정 시 ADR).
- **SessionEnd hook**: transcript 경로를 imprint queue 에 적재 → 헤드리스 `claude -p`
  imprint job 이 write-back 수행.
- **idempotent**: `session_id + event` dedupe key 를 `imprint_guard.py` 가 검사.
  (hook 중복 실행 대비 — RELIABILITY.md 의 1번 항목.)

### 3.4 CONSOLIDATE — Dreaming

- `dreamer` agent (`/dream` 수동 + cron 선택): 최근 session digest 들을 분석 → 잘된/실패/
  cross-sectional 패턴 추출 → **`docs/memory/` central store 에 직접 write**.
  (로컬 신뢰 환경이므로 proposal/인간 merge 승인 없음 — 위키 champion 의 MemoryManager
  사전 승인을 "사후 기계 검증"으로 대체.)
- **종료 조건**: write 직후 dreamer 가 harness-lint 를 실행해 green 확인.
- handoff 문서는 만들지 않는다 — feeder 가 매 세션 generated view 로 컴파일 (C6).
- feeder 는 raw transcript 를 직접 읽지 않고 dreaming 이 정제한 structured memory +
  session digest 만 읽는다 (context 폭발 방지).

## 4. 인간 개입 지점 (minimum human-in-loop)

**① 세션을 열고 task 를 준다 ② (선택) ExecPlan milestone 방향 확인.** 끝.
계획·구현·lint·persona review·doc gardening·메모리 각인·dreaming 은 전부 하네스가 돈다.

## 5. 테스트 전략

- `plugin/scripts/*.py` 는 stdlib python3 + 단위 테스트 (`tests/`).
- doc invariant 자체도 테스트 (taste test): AGENTS.md 줄 수, index 등록, frontmatter,
  generated/ 손편집 금지 등 — lint suite green = 커밋 게이트.
- hook 통합은 실제 세션 기동으로 검증 (self-hosting 이므로 일상 사용이 곧 통합 테스트).

## 6. 빌드 순서 (각 phase 가 이전 phase 를 dogfood)

0. repo + plugin manifest 스캐폴드, git init ✓
1. **Foundation docs**: AGENTS.md / ARCHITECTURE.md / docs tree 전체 + lint 스크립트 +
   tests — *이 시점부터 모든 후속 작업은 ExecPlan 으로 수행*
2. execplan / docs-tree skills + review personas + doc-gardener
3. 메모리 STORE + feeder 2단 (INJECT)
4. IMPRINT hooks (PreCompact / SessionEnd + queue)
5. Dreaming (+ cron 선택)
6. 회고: 위키에 결과 file-back (Q37 / Q2 / Q36② 갱신 재료)

## 7. 성공 기준

- self-hosting 루프 성립: 하네스 개선 task 를 하네스 위에서 (feeder 주입 → ExecPlan →
  구현 → lint/review 게이트 → imprint) 수행할 수 있다.
- 세션을 새로 열었을 때 feeder 가 주입한 context 만으로 이전 작업의 연속성이 유지된다
  (수동 catch-up 설명 불필요).
- dreaming 실행 후 memory 가 lint green 상태로 정제·압축된다.
- 인간 개입이 §4 의 두 지점으로 수렴한다.
