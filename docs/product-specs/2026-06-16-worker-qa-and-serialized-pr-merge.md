---
status: draft
last_verified: 2026-06-16
owner: harness
type: product-spec
tags: [worker, qa, merger, pr-merge]
description: Has workers self-QA and open a PR, then routes done-and-QA'd PRs through a serialized merge queue where a single PR-merger rebases and squash-merges one at a time, escalating only conflicts, risk, or taste to the Director.
---
# 워커 self-QA + 직렬화된 PR-merge (Phase 4 꼬리)

Phase 4 (자율 Director) 의 마지막 슬라이스. 부모 spec:
[Symphony 티켓 오케스트레이션 + 중앙 Director](2026-06-14-symphony-director-orchestration.md)
(로드맵의 "board reporting → PR-merge 관리"). 직전 슬라이스
[Multi-turn 티켓 실행](2026-06-15-multi-turn-ticket-execution.md) 이 명시적 non-goal 로
미뤄둔 **"워커 작업-품질 검증(done-is-really-done)"** 과 visibility 슬라이스의 Open
Question **"un-watched terminal sanity-check"** 을 — *게이트가 아니라 절차+직렬 머지로* —
닫는다. 한 티켓의 작업이 끝난 뒤 그것을 main 으로 **랜딩**하는 단계가 지금은 아예 없다.

## Problem (오늘 무엇이 불만족인가 — observable)

1. **워커 QA 절차가 얕다.** impl taxonomy 템플릿(`director/taxonomy.py::_IMPL_TEMPLATE`)은
   "execplan 따르고 `check.py` GREEN 유지 + completion gate" 까지만 — **task-specific
   테스트(smoke/e2e/Playwright) 작성 단계가 없고**, 워커 vendored 스킬
   (`commit`/`debug`/`land`/`linear`/`pull`/`push`)에 **QA/testing 방법론 스킬이 없다**(전부
   git·PR 배관). spec-compliance/code-quality 리뷰는 execplan completion gate 로 *지시*되나
   self-host 경로 고정 + prose.
2. **PR-merge 단계가 없다.** 워커가 `report_outcome(done)` 해도 그 작업은 워크스페이스/브랜치에
   남고, **main 으로 랜딩되지 않는다.** `land`/`pull`/`push` 스킬은 머지 *메커닉*(squash-merge,
   rebase, 충돌 해소, gh PR)을 갖지만, 그걸 **여러 티켓에 걸쳐 조율(직렬화)하는 주체가 없다.**
3. **동시 머지가 안전하지 않다.** 워커가 각자 PR 을 직접 머지하면, N개 워커가 움직이는 공유 main
   위로 동시에 rebase → thrash, 순서 없음, "지금 main 이 머지받을 상태인가"의 전역 시야 없음.
   (merge queue 가 존재하는 이유.)

## Verified facts (이 세션 / repo, 추측 아님)

- **워커는 충분히 믿을만하다 + report_outcome 을 지시하면 신뢰성 있게 부른다**(M1 +
  `taxonomy.TERMINAL_CONTRACT`, ee5adf1). 그래서 **워커 self-QA 가 두터운 리뷰**이고, 머지 단계는
  얇은 통합 체크로 충분(사람 결정, 이 세션).
- **머지 메커닉은 이미 스킬로 존재** — `director/workspace_skills/land`(mergeability 확인 →
  충돌 시 `pull` → 체크 green 대기 → `gh pr merge --squash`), `pull`(rebase+충돌해소),
  `push`(PR 생성/갱신). 빠진 건 **직렬 조율**뿐.
- **Director 가 단일 인간 surface**(`docs/DIRECTOR.md`). PR-merger 는 그를 *경유*해 사람에게
  올린다(사람 결정, 이 세션).
- **multi-turn `drive` + Director decider 가 이미 "에이전트를 terminal 까지 몰고 turn-end 를
  Director 로 라우팅"하는 머신**을 제공 — 머지도 그 위에서 재사용 가능.
- **app-server 워커는 홈 `~/.codex/skills/*` 를 자동 발견한다**(라이브 확인) — 워커의 스킬 표면 =
  홈 스킬 ∪ 하네스가 까는 워크스페이스 `.codex/skills`. config 의 `[[skills.config]]` 는 *비활성
  오버라이드 목록*이라 playwright 류는 기본 활성. 워커가 `playwright`/`playwright-cli`/
  `frontend-design`/`code-reviewer` 를 본다.
- **Playwright/e2e 가 워커 샌드박스에서 실제로 된다 — 라이브 확인(추측 아님).** 하네스와 동일 launch
  (`-c approvals_reviewer=auto_review -c sandbox_workspace_write.network_access=true`)로 워커가
  **헤드리스 Chrome 을 in-sandbox 기동** → example.com 내비게이션 → DOM `<title>` 추출 성공,
  seam 트래픽 0. ⇒ e2e/Playwright 를 **워커 self-QA 에 둘 수 있다**(호스트-통합으로 뺄 필요 없음).
  단 self-host 머신 전제(playwright-cli + 브라우저 + 홈 스킬 존재) — 포팅 호스트는 미설치 가능 →
  R1/QA 스킬은 **graceful fallback**(미설치 시 smoke/unit 까지)을 명시.

## Requirements (R1..R9 — 각 항목 사람이 검증 가능)

- **R1 — 워커 self-QA 는 impl 개발 *절차*(게이트 아님).** impl taxonomy 템플릿이 워커에게
  terminal 전: (a) 호스트 게이트 green, (b) spec-compliance + code-quality self-review,
  (c) **티켓에 맞는 task-specific 테스트 작성·실행**(smoke/e2e/Playwright 중 적절히 — UI 변경이면
  `playwright`/`playwright-cli` 스킬로 e2e, 미설치 호스트면 smoke/unit 로 graceful fallback),
  (d) PR 생성을 *안내*한다. (검증: 한 impl 워커 런이 PR + 테스트를 산출하고, 절차 텍스트가 이
  단계들을 명시.)
- **R2 — 워커 PR 은 구조화된 자기명세를 담는다**(PR body, prose): 어떤 spec/기능을 구현했나, 무슨
  리뷰(spec/code)를 했나, 무슨 테스트를 쓰고 결과는 어땠나. (검증: 워커가 만든 PR body 에 이
  필드들이 있다 — merger/사람이 머지 때 참고.)
- **R3 — `done` 은 여전히 LLM 판단이지 코드 게이트가 아니다**(multi-turn R4 보존). QA 통과가
  `report_outcome(done)` 을 막지 않는다. 절차가 안내하고 워커/Director 가 판단. (검증:
  terminal 전환을 QA 결과로 막는 코드 경로가 없다 — AGENTS.md "minimal blocking gates" 와 정합.)
- **R4 — done+QA 된 티켓의 PR 은 *직렬화된 merge queue* 에 들어가고, 단일 PR-merger 가 하나씩
  비운다.** (검증: 동시에 ready 인 PR N개 → 머지가 순차로 일어남(매번 최신 main 으로 rebase),
  절대 동시 아님.)
- **R5 — PR-merger 는 머지 프로세스 + *얇은* 통합 리뷰만 한다:** 최신 main 으로 rebase(`pull`),
  깔끔한 충돌 해소, 병합 결과에 호스트 게이트(통합 체크), squash-merge(`land`). 워커의 두터운
  QA 를 **재실행하지 않음** — PR 자기명세를 참고한 가벼운 sanity 만. (검증: PR 은 rebase + green
  통합 게이트 뒤에만 main 으로 랜딩.)
- **R6 — merger 는 Director 로 escalate**(단일 인간 surface): 못 푸는 충돌 / 못 고치는 red 통합
  게이트 / taste·위험 머지. Director 가 taste 를 사람에게 올린다. (검증: 못 푸는 충돌 →
  escalation 이 Director 로 가고, 조용한 머지도 merger→사람 직통도 아님.)
- **R7 — PR-merger 는 Director 와 *별개* 컴포넌트/역할**(관심사: 통합 경계 vs 실행 감독), 단 인간
  통신은 Director 경유. (검증: merger 와 Director 가 구분된 컴포넌트; merger 에 사람 직통 경로 없음.)
- **R8 — 티켓 done = 작업 완료(multi-turn 불변); 머지는 *하류* PR 파이프라인.** 워커 done 이면 board
  는 done(작업 기준); PR 랜딩은 별도 단계. 머지 실패는 escalate + 티켓에 코멘트(드물게 reopen 판단).
  (검증: 워커 done 이 머지를 기다리지 않음; 머지 실패가 티켓에 surface.)
- **R9 — 직렬 lane 은 multi-turn `drive` + Director decider 를 재사용한다.** 머지는 `land` 스킬을
  쥔 Codex 에이전트가 *concurrency=1 레인*에서 terminal 까지 driven 되는 한 단위; 충돌/taste turn-end
  는 워커 turn-end 와 똑같이 Director 로 라우팅. (검증: merger 가 새 turn 머신을 만들지 않고 drive
  경로를 탄다 — diff 로 확인.)

## Design

### 두 단계 파이프라인

```
워커(impl): execplan 구현 → self-QA(spec/code/테스트) → PR 생성+자기명세 → report_outcome(done)
   │  (board done = 작업 완료; R3/R8 — 게이트 없음, LLM 판단)
   ▼
merge queue (직렬) ── PR-merger(단일 소비자) ── 하나씩: rebase(pull) → 통합 게이트 → squash-merge(land)
                                          └─ 충돌/red/taste → Director 로 escalate(단일 인간 surface)
```

### A. 워커 self-QA (절차 — 코드 게이트 0)

- **`director/taxonomy.py::_IMPL_TEMPLATE` 확장** — 구현 뒤 절차로: task-specific 테스트(아래 스킬)
  작성·실행 → PR 생성(`push`) + 자기명세 → 끝나면 `report_outcome(done)`. `TERMINAL_CONTRACT` 와
  짝(이미 done 신호를 안내).
- **신규 워커 스킬 `director/workspace_skills/qa/SKILL.md`** — 이게 *유일한 진짜 신규 내용*:
  task-specific 테스트 방법론(언제 smoke vs e2e vs Playwright, 워크스페이스에서 어떻게 작성·실행),
  spec-compliance + code-quality self-review 체크리스트, spec 의 acceptance criteria ↔ 테스트 연결.
- **PR 자기명세** — `push` 스킬이 PR body 에 채우는 템플릿(R2 필드). prose.

### B. 직렬화된 PR-merge

- **merge queue** — `director/queue` 에 `mergeRequest` kind 추가(또는 전용 채널): 워커가 done+PR 시
  `{ticket, pr_url, branch, self_description}` enqueue. (큐 atomic/idempotent 계약 재사용.)
- **`director/merger.py`(신규)** — 단일 소비자 drain 루프: queue 에서 PR 하나 pop → **`drive`
  로 머지-에이전트(`land` 스킬) 를 terminal 까지** (R9) → 다음. 단일 소비자라 **직렬화가 자동**
  (R4). 머지-에이전트의 turn-end(충돌·taste)는 Director decider 로 라우팅(R6) — watched=Director
  가 답, un-watched=park+사람 async. `land` 가 rebase·체크·squash-merge 를 수행(R5).
- **Director 통합** — `docs/DIRECTOR.md` 에 머지 escalation 처리 절(merger 가 올린 충돌/위험을
  Director 가 받아 사람에게 올리거나 직접 판단). merger 는 사람 직통 없음(R7).

### 구성요소 / 파일

- `director/taxonomy.py` — impl 템플릿에 QA+PR 절차.
- `director/workspace_skills/qa/SKILL.md` — 신규 testing/QA 방법론 스킬(+ 워크스페이스 설치 경로).
- `director/merger.py` — 직렬 merge queue + drive-기반 drain + escalate.
- `director/queue/__init__.py` — `mergeRequest` (+ 필요 시 `mergeReview`) kind.
- `docs/DIRECTOR.md` — 머지 escalation 처리 절.
- 재사용: `director/run.py::drive` + `director/decider.py`(레인 decider), `land`/`pull`/`push` 스킬.

### 에러 / 경계 케이스

- **못 푸는 충돌 / red 통합 게이트** → merger 가 Director 로 escalate(R6), PR 은 미머지 유지.
- **의존 PR 순서** — FIFO(ready 시각) + 매번 최신 main rebase; 아직 안 머지된 sibling 이 필요한 PR 은
  통합 게이트에서 실패 → 재큐/대기 또는 escalate(ExecPlan 에서 정제).
- **머지 후 main red**(통합 게이트가 못 잡은 경우) → 후속 fix 티켓 또는 revert 판단(escalate).
- **Playwright/e2e 미설치 호스트**(self-host 는 됨 — 라이브 확인; 포팅 호스트는 playwright-cli/
  브라우저 없을 수 있음) → 워커 QA 스킬이 graceful fallback(smoke/unit). e2e 를 호스트-통합으로
  뺄 필요는 없음(워커 샌드박스에서 실행됨).

## Non-goals (scope fence — YAGNI)

- **board done 하드 QA 게이트.** 명시적 기각(minimal blocking gates; 워커 신뢰; R3).
- **머지에서 워커 두터운 QA 재실행.** merger 는 얇은 통합만(R5).
- **두 번째 인간 surface.** merger 는 Director 경유(R7).
- **완전한 CI 인프라 / GitHub merge-queue 제품.** 최소 직렬 소비자만 만든다.
- **복잡한 의미적 충돌 자동 해소.** 그런 건 escalate.
- **board reporting**(Director 의 run 요약 리포팅) — 인접 Phase 4 항목이나 별도(여기 범위 밖).
- **Phase 5**(공유 tracker / GitHub Issues 어댑터 / cross-repo).

## Acceptance criteria

- impl 워커 런이 **코드 + task-specific 테스트 + 구조화 자기명세를 단 PR** 을 산출하고,
  `report_outcome(done)` 이 어떤 QA 게이트에도 막히지 않음(R1/R2/R3).
- **동시에 끝난 두 티켓 → 두 PR → merger 가 순차로 랜딩**(각각 최신 main rebase), 절대 동시 아님;
  둘 다 main green 으로 들어감(R4/R5).
- 못 푸는 충돌(또는 red 통합 게이트)인 PR → merger 가 **Director 큐로 escalate**, 조용히 머지 안 함(R6).
- merger 와 Director 가 구분된 컴포넌트이고 merger 에 사람 직통 경로가 없음(R7, diff 로 확인).
- **Live wire-pin:** 실제 워커가 self-QA + PR 생성 → merger 가 rebase + green 통합 체크 + squash-merge
  로 main 에 랜딩 1회. (Playwright-in-sandbox PoC 는 **이미 통과** — 이 세션 라이브 확인; ExecPlan 은
  e2e 작성·실행을 워커 절차에 엮는 것까지.)
- merger 가 turn 머신을 새로 안 만들고 `drive`/decider 를 재사용(R9, diff 로 확인).
- `python3 plugin/scripts/check.py` GREEN.

## Decision Log (수렴 결정 + 근거)

- **D-46 워커 self-QA = 절차-가이드, 하드 게이트 아님.** 워커가 충분히 믿을만하고, board done 게이트는
  AGENTS.md "minimal blocking gates" 법칙 위반 + multi-turn R4(LLM 판단) 충돌. 이빨은 self-QA(두터움)에,
  머지는 얇은 통합. (사람, 이 세션.)
- **D-47 PR-merge = 별도 *직렬화된* merger, 워커-self-merge 아님.** 동시성이 결정적 근거: 단일 소비자
  큐가 동시 main rebase thrash 를 구조적으로 제거(merge-queue 합리). (사람, 이 세션.)
- **D-48 merger 인간 surface = Director 경유(단일 surface).** merger 는 깨끗한 건 자율 머지, 충돌/위험/
  taste 만 Director 로 → Director 가 사람. 사람 창구 하나 유지. (사람, 이 세션.)
- **D-49 티켓 done = 작업 완료(multi-turn 불변); 머지는 하류 PR 파이프라인.** 머지가 board done 을
  지연시키지 않음; 머지 실패는 escalate+코멘트. (자율 결정 — R4/multi-turn 정합.)
- **D-50 merger 는 `drive` + Director decider 재사용.** 머지 = `land` 스킬 쥔 에이전트를 concurrency=1
  레인에서 terminal 까지 driven; turn-end 라우팅 동일. 새 turn 머신 안 만듦(surface 최소). (자율 결정.)
- **D-51 한 스펙(QA + PR-merge), ExecPlan 은 linked plan 으로 분할 가능.** self-QA→PR→직렬머지가 한
  파이프라인이라 응집도 높음; build 는 QA-절차 / merger 로 나눠도 됨. (사람, 이 세션.)
- **D-52 e2e/Playwright 는 워커 self-QA 에 둔다(호스트-통합 아님) — 라이브 확인.** app-server 워커가
  홈 `~/.codex/skills` 를 자동 발견하고 in-sandbox 헤드리스 Chrome 을 실제로 띄움(이 세션). 포팅
  호스트 미설치 시 graceful fallback(smoke/unit). 이로써 스펙의 핵심 PoC 가 선제 통과. (자율 검증.)
- **D-53 v1: PR-merger 가 *모든* 머지를 `drive`(land 에이전트)로 처리(D-50). "mechanical
  happy-path" 는 deferred 최적화.** clean+green 머지를 에이전트 없이 코드로(rebase→게이트→squash)
  떨구고 충돌/red/taste 만 에이전트로 보내는 정제는 — 직렬 큐(D-47)는 유지한 채 — merger 부하가
  실제로 문제될 때 도입. (워커가 clean 이라고 직접 unserialized 머지하는 안은 기각: "clean against
  *stale* main" 이라 individually-clean-together-broken main 을 못 막음 — merge-queue 존재 이유.)
  v1 은 단순·균일 우선. (사람, 이 세션 — defer.)

## Open Questions

- ~~Playwright/e2e 샌드박스 실행 가능성~~ → **해소(라이브 확인, 이 세션):** 워커가 in-sandbox 헤드리스
  Chrome 기동·내비게이션 성공(seam 0). e2e 는 워커 self-QA 에 둔다. 남은 건 포팅 호스트 미설치
  graceful fallback(R1)뿐.
- **board 에 "merging" 상태가 필요한가**, 아니면 done(작업)+하류 머지로 충분한가 — 1차는 충분으로 보고
  (D-49), reporting 에서 merged-vs-done 구분이 필요해지면 재검토.
- **의존 PR 머지 순서** — FIFO+rebase+게이트(+sibling 미머지면 escalate)로 시작, ExecPlan 에서 정제.
- **merger 가 상시 프로세스인가 이벤트-구동인가** — Director 의 `watch` 처럼 mergeRequest 큐를 tail 해
  이벤트로 깨우는 형태가 자연스러움(ExecPlan).
