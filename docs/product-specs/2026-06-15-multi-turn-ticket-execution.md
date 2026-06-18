---
status: stable
last_verified: 2026-06-15
owner: harness
type: product-spec
tags: [worker, multi-turn, director, reconcile]
description: Corrects the one-turn-equals-done model so a ticket spans many turns, with workers proposing structured outcomes (continuing/done/blocked/needs_human) that the Director enforces when watched or trusts and auto-continues when un-watched.
---
# Multi-turn 티켓 실행 — Director-driven continuation + worker-proposed status

Phase 4 (자율 Director) 의 슬라이스. 부모 spec:
[Symphony 티켓 오케스트레이션 + 중앙 Director](2026-06-14-symphony-director-orchestration.md).
이건 Phase 2 의 [오케스트레이터 dispatch 루프](2026-06-14-orchestrator-dispatch-loop.md) 의
**reconcile 모델을 재설계**한다 — 그 spec 의 "turn-status → board-state 코드 매핑"이 틀렸음을
교정. board reporting/PR-merge 보다 **앞서는** 핵심 슬라이스(RV2 의 주력 케이스를 비로소 구현).

## Problem (오늘 무엇이 불만족인가 — observable)

현 오케스트레이터는 **티켓당 한 턴**만 돌린다: `dispatch` → `run.run_ticket` → `run_turn` **1회**
→ `reconcile` 가 turn-status 를 board-state 로 **코드로 1:1 매핑**(`completed → Done`,
`director/orchestrator.py`). 이게 만든 관찰 가능한 실패 셋:

1. **턴 종료 ≠ 티켓 완료인데 코드가 동일시한다.** 워커가 작업 도중 *"이제 ExecPlan 할까요?"*
   처럼 멈추면 그건 Codex 에서 `turn/completed` 다(에이전트가 더 할 게 없어 — 답 기다리느라 —
   턴을 닫음). 그런데 orchestrator 는 그걸 **Done 으로 찍고 멈춘다.** 작업은 영영 이어지지 않고,
   그 질문은 증발한다. retry 는 `failed` 에만 걸리므로 backstop 도 없다.
2. **코드가 워커의 LLM status 판단을 짓밟는다.** 워커는 이미 자기 티켓을 옮길 도구가 있다
   (T10 allowlist 의 `issueUpdate`/`issueCreate` — 상태 변경 + 자식 티켓 발행). 그래서 워커가
   *"이건 설계 필요 → 이 티켓 Blocked, DESIGN-2 발행"* 이라고 LLM 판단해도, `completed` 면
   orchestrator 가 **무조건 Done 으로 덮어쓴다.** LLM 판단 위에 코드가 올라타 있다.
3. **RV2 의 주력 케이스가 미구현.** 부모 RV2 = "워커는 안 멈추고, would-be-human 질문은 Director
   가 답(taste 만 사람에게)". 가장 흔한 would-be-human 순간은 mid-turn 구조화 요청이 아니라
   **턴-경계의 '계속할까요?'** 다(특히 auto_review 가 mid-turn 승인을 거의 다 흡수한 지금). 그
   경계를 우리는 받지 못한다.

핵심: **티켓 status 전환은 LLM 판단이지 코드 매핑이 아니다.** "완료/계속/추가 리서치·설계 필요해
자식 티켓 발행"은 코드가 분간할 수 없다. 워커가 한 턴 끝낸 사실(`turn/completed`)은 *이벤트*일
뿐, 그게 티켓에 무엇을 의미하는지는 판단이 필요하다.

## Verified facts (이 세션, 추측 아님)

- **Multi-turn continuation 작동.** 같은 thread 로 `run_turn` 2회 — turn 2 가 turn 1 의 코드워드
  (BANANA7)를 기억해 파일로 씀. 즉 **thread 가 턴을 넘어 맥락 유지**, 호스트가 다음 입력
  ("continue" 등)을 새 턴으로 먹여 워커를 이어갈 수 있다. 메커니즘은 `app_server.py` 에 이미
  있고(`thread_start` + 반복 `run_turn`), 단지 `run_ticket` 이 한 턴 후 멈출 뿐.
- **워커는 in-sandbox 를 auto_review 로 self-govern**(슬라이스 3) → mid-turn 승인은 거의 안 옴.
  남는 진짜 "사람 순간"은 **턴-경계의 continue/결정/done 판단** — 대부분 Director가 사람 대신
  내용 있는 답을 주는 *비-taste 결정*("A 로 해라")이다.

## Requirements (R1..R8 — 각 항목 사람이 검증 가능)

- **R1 — 티켓 실행 = 한 thread 위의 multi-turn 루프.** 한 턴이 아니라, 워커가 *terminal* 이라
  판단할 때까지 턴을 이어 돌린다. (검증: 한 티켓이 ≥2 턴에 걸쳐 진행되고 같은 thread id 가 유지됨.)
- **R2 — 매 턴-종료는 둘 다 캡처된다: 워커 final message + (있으면) terminal 신호.** (a) 워커가
  작업을 끝내거나 막히면 **terminal 신호** `report_outcome`(done / blocked+children / 명시적
  needs_human)을 명시적으로 냄, (b) 그 외 흔한 경우는 신호 없이 **prose final message**로 끝남
  ("A 일 수도 B 일 수도"). **둘 다 캡처** — 특히 (b)의 final assistant message(현 `run_turn`은
  이걸 버림). `continuing`/`done`은 워커가 내는 고정 enum이 아니라, Director가 턴-종료를 읽고
  정하는 disposition이다. (검증: final message와 terminal 신호가 모두 Director로 캡처·라우팅됨.)
- **R3 — disposition은 Director가 턴-종료(final message + 있으면 report_outcome + 맥락)를 읽고
  셋 중 하나로 정한다:**
  - **terminal** (report_outcome done/blocked, 또는 메시지로 명백히 완료/막힘) → Director 집행/
    검수. **board 전환은 여기서만**(자식 티켓 + blocked_by 반영).
  - **non-terminal & 비-taste** → Director가 **free-form content-bearing directive**를 작성 →
    같은 thread 새 턴, board 불변. *고정 "continue"가 아니다*: "계속?"엔 "continue", **"A 냐 B 냐"엔
    "A 로 해라"**, "X 빠졌다"엔 "X 도 해라". **이게 RV2의 본질** — would-be-human 결정을 Director가
    사람 대신.
  - **taste** (product 방향·비가역) → 사람에게 escalate.
  핵심 구분: **비-taste → Director가 직접 답** vs **taste → 사람**(현 needs_human이 뭉갰던 둘을 분리;
  'A 냐 B 냐'는 대개 비-taste라 Director가 답한다). (검증: '계속?'→continue, 'A냐B냐'→"A로 해라",
  taste 포크→escalate; board는 terminal 에서만.)
- **R4 — 코드는 done-ness/continuation 을 일절 판단 안 함.** 코드는 plumbing 만: 턴 돌리고,
  outcome 라우팅하고, Director 결정(watched) 또는 워커 제안(un-watched)대로 전환 *집행*. 현
  `completed → Done` 코드 매핑은 **제거**. (검증: orchestrator 에 turn-status→board-state 직접
  매핑이 없음; 전환은 워커/Director 신호로만.)
- **R5 — watched vs un-watched.**
  - watched: Director(메인 세션, director-oversight 스킬)가 각 턴-종료를 읽어 — terminal 검수·집행,
    non-terminal 비-taste엔 **내용 있는 답**, taste는 escalate.
  - un-watched: bespoke 답을 낼 Director가 없으니, non-terminal 비-taste 디폴트 = **"네 best
    judgment 로 결정하고 계속하라"**(워커가 LLM이니 self-resolve — auto-continue의 일반화).
    terminal 제안 → 워커 신뢰·적용; taste(report_outcome needs_human 등) → park/안전 기본값 + 사람
    async. (자율 프롬프팅상 워커는 애초에 덜 멈추고 스스로 결정하는 경향.)
  (검증: un-watched 멀티-턴 런이 진행·전환되고, 'A냐B냐'엔 self-resolve 지시, 무한 안 돔.)
- **R6 — runaway bound.** 티켓당 max-turns(예: `max_passes` 류) — auto-continue 가 영원히 못
  돌게. 초과 시 stuck 표시 + surface. (검증: 끝없이 continuing 하는 워커가 bound 에서 멈추고
  stuck 로 보고됨.)
- **R7 — 신호/응답 메커니즘(아래 Design 결정).** (a) 워커 **final assistant message 캡처**(현
  `run_turn`이 버리는 것 — Director 읽기의 1차 입력), (b) **terminal 신호용 `report_outcome` 툴**,
  (c) Director의 **free-form reply** 생성. 신호 없는 prose 턴-종료의 디폴트는 "continue"가 아니라
  **"Director가 읽고 답"**(un-watched면 self-resolve). (검증: final message 캡처 + Director가 그걸
  읽어 content-bearing directive; report_outcome은 terminal에만.)
- **R8 — 가시성 반영.** status 스냅샷이 티켓별 턴-수/continuation 을 보이고, board 전환은
  terminal 에서만 일어남(슬라이스 2 표면 확장). (검증: 스냅샷에서 멀티-턴 진행이 보임.)

## Design

### dispatch 단위의 변화

**오늘:** `dispatch(ticket)` = 한 턴 + 코드 reconcile.
**목표:** `dispatch(ticket)` = **한 thread 를 worker-terminal-outcome 까지 몰고 가는 multi-turn
드라이브.** 의사코드:

```
drive(ticket):
  thread = thread_start(...)            # 슬라이스 3 의 autonomous posture 그대로
  input  = compose_prompt(ticket)
  for turn in range(max_turns):         # R6 bound
    result = run_turn(thread, input)    # result = {status, turn_id, final_message, report_outcome?}
    disp = director_respond(ticket, result)  # LLM(watched)/디폴트(un-watched): 턴-종료를 읽고 판단
    if disp.kind == "terminal":         # done/blocked  → board 전환(여기서만)
       apply_terminal(ticket, disp); return
    if disp.kind == "escalate":         # taste  → 사람
       escalate(ticket, disp); return
    input = disp.reply                  # 비-taste: content-bearing directive ("continue"/"A로 해라"/…)
  mark_stuck(ticket, "max_turns")        # R6
```

코드(orchestrator)는 위 루프와 라우팅만 소유. **done-ness/continuation 판단·board 전환·워커에게
줄 답은 전부 `director_respond`(LLM, watched) 또는 un-watched 디폴트** 가 소유(R4). `director_respond`
는 final message + (있으면) report_outcome + 맥락을 읽어 terminal/reply/escalate 중 하나를 낸다.

### R7 결정 — 신호와 응답

**(1) terminal 신호 = `report_outcome` dynamicTool.** 워커가 작업을 *끝내거나*(done) *막혀서
분해*(blocked+children)할 때 `report_outcome({status, reason, spawned_ticket_ids?})`를 호출
(`thread/start` `dynamicTools`, D-7 재사용). terminal 전환의 신뢰 가능한 구조화 신호.

**(2) mid-work는 final-message 읽기 + Director의 free-form 답.** 워커가 "A 일 수도 B 일 수도"처럼
prose로 끝내고 `report_outcome`을 안 부르는 게 흔하다 — 그건 본질적으로 prose다. 그래서 **워커
final assistant message를 캡처**(현 `run_turn`은 버림)하고 **Director(LLM)가 읽어 content-bearing
directive를 작성**한다. 신호 없는 턴-종료의 디폴트는 "continue"가 **아니라** "Director가 읽고 답".

**(3) `director_respond` = 통합 판단자(free-form).** turn-종료(final message + 선택적
report_outcome + 맥락 + status)를 읽고 → terminal 집행 / **free-form reply**(continue거나 "A로
해라"거나) / taste escalate. report_outcome이 있으면 terminal/blocked가 *확실*해지고, 없으면
Director가 메시지로 terminal-여부까지 추론. 비-taste면 직접 답, taste면 사람(needs_human이 뭉갠 둘
분리). watched=메인 세션(director-oversight 스킬); un-watched=비-taste 디폴트 "self-resolve and
continue" 코드 경로.

**ExecPlan 에서 검증(추측 금지):** ① `run_turn` 스트림에서 final assistant message 캡처가 깔끔히
되는지, ② 워커가 terminal에 `report_outcome`을 얼마나 부르는지(안 불러도 Director-읽기가 terminal도
분간해야 = 안전망). multi-turn continuation 자체는 이미 live 검증.

### 구성요소 / 파일

- **`director/run.py`** — `run_ticket`(한 턴)을 **multi-turn `drive`**(thread 유지, terminal 까지
  반복)로. 한 턴 단위는 내부 helper. **`run_turn`이 final assistant message 를 캡처·반환**(현재
  `{status, turn_id}`만 — Director 읽기의 1차 입력).
- **`director/orchestrator.py`** — `reconcile` 의 `completed → Done` 코드 매핑 **제거**; dispatch 가
  `drive` 를 호출하고 terminal disposition 을 board 로 집행(Director 결정/워커 제안 경유). DAG/
  concurrency/wave 루프는 유지.
- **`report_outcome` 툴** — `director/worker/tools.py`(또는 신규)에 spec + executor; **terminal
  신호**(done/blocked/needs_human)를 큐/Director 로 라우팅.
- **`director_respond`(free-form 판단자)** — watched: `.claude/skills/director-oversight/`(턴-종료
  읽기 → terminal검수 / 내용있는답 / taste escalate 가이드; 슬라이스 2 스킬이 본래 목적을 되찾음);
  un-watched: 비-taste 디폴트 "self-resolve and continue" 코드 경로.
- **status 표면** — `director/status.py` 에 턴-수/continuation 반영(R8).

### 에러 / 경계 케이스

- 워커가 `report_outcome` 안 부르고 prose 로 turn 종료 → **Director 가 final message 를 읽고 답**
  (continue 거나 "A로 해라" 거나 escalate); 디폴트가 "계속"이 *아니라* "읽고 답". R6 bound 가 무한 방지.
- `turn/failed` mid-ticket → 기존 retry-once 유지(단일 턴 실패), 그 다음도 실패면 stuck.
- un-watched 에서 `needs_human` → seam/park 안전 기본값 + 사람 async(슬라이스 3 의 timeout 결).
- 워커가 자식 티켓을 issueCreate 로 발행 → blocked outcome 의 `spawned_ticket_ids` 로 보고,
  DAG(Phase 3a)가 픽업.

## Non-goals (scope fence — YAGNI)

- **헤드리스 un-watched Director.** un-watched continuation 은 코드 auto-continue + 워커 제안
  신뢰지, LLM Director spawn 이 아님(기각 유지).
- **워커 작업 품질 검증/리뷰.** "done 이 진짜 done 인가"의 코드 sanity-check 이상은 범위 밖
  (검증/리뷰는 별도).
- **board reporting / PR-merge.** 후속.
- **report_outcome 스키마의 과한 일반화.** terminal 3개(done/blocked/needs_human)로 시작(YAGNI);
  mid-work 답은 free-form 이라 스키마 없음.

## Acceptance criteria

- 한 티켓이 ≥2 턴에 걸쳐 같은 thread 로 진행되고, non-terminal 답에서 board 가 안 바뀌며,
  terminal 에서만 board 전환(R1/R3/R4).
- 워커가 prose 로 "A 냐 B 냐" 하고 끝내면(report_outcome 없이) → Director 가 **"A 로 해라" 같은
  content-bearing 답**으로 다음 턴(고정 "continue" 아님); `report_outcome(done)` 이면 terminal;
  max-turns 초과면 stuck(R2/R3/R6/R7).
- `blocked`+spawned children 가 보고되면 board 가 Blocked + 자식 티켓 픽업(R3).
- orchestrator 에 turn-status→board-state 직접 매핑이 없음(R4 — diff 로 확인).
- un-watched 멀티-턴 런이 진행·전환, 'A냐B냐'엔 self-resolve 지시, 무한 안 돔(R5/R6).
- **Live wire-pin:** 실제 codex 워커가 2+ 턴짜리 작업을 진행 — 중간 'A냐B냐'에 Director 가
  content-bearing 답으로 잇고, terminal 에서 마치는 1회.
- `python3 plugin/scripts/check.py` GREEN.

## Decision Log (수렴 결정 + 근거)

- **D-39 티켓 실행 = multi-turn 루프; status 전환은 워커가 terminal 판단할 때만; 코드는 done-ness
  판단 0.** `turn/completed` 는 이벤트지 티켓 완료가 아니다. (사람, 2026-06-15.)
- **D-40 worker proposes / Director executes(option C).** 워커가 structured outcome 제안, Director
  가 집행·검수. un-watched = 워커 제안 신뢰·적용 + auto-continue + 사람 async 검토. (사람.)
- **D-41 턴-경계 'continue?' → Director 가 "continue"(비-taste) → 새 턴.** RV2 의 주력 케이스; 가장
  흔한 would-be-human 순간. (사람.)
- **D-42 multi-turn continuation feasibility = live 검증.** 2턴/1thread, 맥락 유지(BANANA7).
- **D-43 orchestrator `completed → Done` 코드 매핑 제거.** LLM 판단이 board 전환을 소유(R4).
- **D-44 terminal 신호 = `report_outcome` 툴(좁힘).** done/blocked/명시적 needs_human 의 구조화
  신호 전용. mid-work 의 continue/decide 는 이 툴이 아니라 **final-message 읽기 + Director-답**
  경로. (사람 피드백으로 교정, 이 세션.)
- **D-45 Director 턴 응답 = free-form content-bearing, 고정 "continue" 아님.** 워커가 prose 로
  "A 일 수도 B 일 수도" 끝내면 Director 가 사람 대신 **내용 있는 답("A 로 해라")** — RV2 의 본질.
  **비-taste → Director 가 직접 답** vs **taste → 사람** 분리(needs_human 이 뭉갰던 둘). 워커 final
  message 캡처가 필수 입력; `director_respond` 가 통합 판단자. un-watched 비-taste 디폴트 =
  "self-resolve and continue". 근거: structured-outcome-only 였던 초안이 가장 흔한 케이스(prose
  '이럴 수도 저럴 수도')를 못 받았음 — 사람 피드백 교정. (사람, 이 세션.)

## Open Questions

- final-message 읽기 + Director-답이 mid-work 의 **1차 경로**(옵션 아님); `report_outcome` 은
  terminal 신호용. 워커가 terminal 에 그 툴을 얼마나 부르는지 + `run_turn` 스트림에서 final
  message 가 깔끔히 잡히는지 — ExecPlan live 검증(안 불러도 Director-읽기가 terminal 도 추론해야).
- un-watched terminal 제안을 **무검증 적용** vs **가벼운 코드 sanity-check**(예: done 인데 PR 없음
  → flag). 1차는 신뢰+적용 + bound backstop(사람 결정), 필요 시 정제.
- max-turns 기본값 — oversee 부하/티켓 크기에 맞춰 ExecPlan 에서.
